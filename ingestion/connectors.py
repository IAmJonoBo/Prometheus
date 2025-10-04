"""Source connectors for ingestion."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.contracts import EvidenceReference

from .models import IngestionPayload


class SourceConnector:
    """Interface implemented by ingestion source connectors."""

    def collect(self) -> Iterable[IngestionPayload]:
        """Yield payloads fetched from the connector."""

        raise NotImplementedError

    async def collect_async(self) -> list[IngestionPayload]:
        """Asynchronously gather payloads from the connector."""

        return await asyncio.to_thread(self._collect_to_list)

    def _collect_to_list(self) -> list[IngestionPayload]:
        return list(self.collect())


@dataclass(slots=True)
class MemoryConnector(SourceConnector):
    """Simple connector used for tests and bootstrap flows."""

    uri: str
    content: str | None = None

    def collect(self) -> Iterable[IngestionPayload]:
        description = f"Synthetic payload for {self.uri}"
        reference = EvidenceReference(
            source_id="memory",
            uri=self.uri,
            description=description,
        )
        body = self.content or f"Seed content emitted by {self.uri}."
        yield IngestionPayload(reference=reference, content=body, metadata={})


@dataclass(slots=True)
class FileSystemConnector(SourceConnector):
    """Connector that reads files from the local filesystem."""

    root: Path
    patterns: Sequence[str] = ("**/*",)
    encoding: str = "utf-8"

    def collect(self) -> Iterable[IngestionPayload]:
        try:
            from unstructured.partition.auto import partition  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency
            partition = None

        if not self.root.exists():
            return

        for pattern in self.patterns:
            for path in sorted(self.root.glob(pattern)):
                if not path.is_file():
                    continue
                text = self._read_text(path, partition)
                reference = EvidenceReference(
                    source_id="filesystem",
                    uri=path.resolve().as_uri(),
                    description=path.name,
                )
                metadata = {
                    "path": str(path.resolve()),
                    "checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
                yield IngestionPayload(
                    reference=reference, content=text, metadata=metadata
                )

    def _read_text(self, path: Path, partition: Any | None) -> str:
        if partition is not None:
            try:
                elements = partition(filename=str(path))
            except Exception:  # pragma: no cover - library failure path
                elements = None
            if elements:
                parts = [
                    getattr(element, "text", "")
                    for element in elements
                    if getattr(element, "text", "").strip()
                ]
                if parts:
                    return "\n\n".join(part.strip() for part in parts)
        try:
            return path.read_text(encoding=self.encoding)
        except UnicodeDecodeError:  # pragma: no cover - binary guard
            return path.read_bytes().decode(self.encoding, errors="ignore")


@dataclass(slots=True)
class WebConnector(SourceConnector):
    """Connector that extracts text from HTTP endpoints using Trafilatura."""

    urls: Sequence[str]
    timeout: float = 20.0
    user_agent: str = "Prometheus-Ingestion/1.0"

    def collect(self) -> Iterable[IngestionPayload]:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "requests is required for web ingestion; install the optional"
                " 'requests' dependency"
            ) from exc

        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent})
        try:
            import trafilatura  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "trafilatura is required for web ingestion; install the optional"
                " 'trafilatura' dependency"
            ) from exc
        for url in self.urls:
            try:
                response = session.get(url, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:  # pragma: no cover - network failure
                continue
            extracted = trafilatura.extract(response.text, include_comments=False)
            text = extracted or response.text
            reference = EvidenceReference(
                source_id="web",
                uri=url,
                description=response.headers.get("title", url),
            )
            metadata = {"status_code": str(response.status_code)}
            yield IngestionPayload(
                reference=reference, content=text.strip(), metadata=metadata
            )

    async def collect_async(self) -> list[IngestionPayload]:
        try:
            import httpx  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency
            return await super().collect_async()

        async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
            tasks = [self._fetch(client, url) for url in self.urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        payloads: list[IngestionPayload] = []
        for result in results:
            if isinstance(result, BaseException):  # pragma: no cover - network failure
                continue
            if result is not None:
                payloads.append(result)
        return payloads

    async def _fetch(self, client: Any, url: str) -> IngestionPayload | None:
        try:
            response = await client.get(url, timeout=self.timeout)
            response.raise_for_status()
        except Exception:  # pragma: no cover - network failure
            return None
        try:
            import trafilatura  # type: ignore
        except ImportError:
            trafilatura = None
        extracted: str | None = None
        if trafilatura is not None:
            try:
                extracted = trafilatura.extract(response.text, include_comments=False)
            except Exception:  # pragma: no cover - extraction failure
                extracted = None
        text = (extracted or response.text).strip()
        reference = EvidenceReference(
            source_id="web",
            uri=url,
            description=response.headers.get("title", url),
        )
        metadata = {"status_code": str(response.status_code)}
        return IngestionPayload(reference=reference, content=text, metadata=metadata)


def build_connector(config: dict[str, Any]) -> SourceConnector:
    """Build a connector from configuration."""

    connector_type = config.get("type", "memory")
    if connector_type == "memory":
        return MemoryConnector(
            uri=config.get("uri", "memory://default"),
            content=config.get("content"),
        )
    if connector_type == "filesystem":
        root = Path(config["root"]).expanduser().resolve()
        patterns = tuple(config.get("patterns") or config.get("globs") or ("**/*",))
        return FileSystemConnector(
            root=root, patterns=patterns, encoding=config.get("encoding", "utf-8")
        )
    if connector_type == "web":
        urls: Sequence[str] = tuple(config.get("urls", []))
        if not urls:
            raise ValueError("Web connector requires at least one URL")
        return WebConnector(
            urls=urls,
            timeout=float(config.get("timeout", 20.0)),
            user_agent=config.get("user_agent", "Prometheus-Ingestion/1.0"),
        )
    raise ValueError(f"Unsupported connector type: {connector_type}")
