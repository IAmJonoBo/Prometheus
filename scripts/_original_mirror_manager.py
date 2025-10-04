#!/usr/bin/env python3
"""Manage dependency and model mirrors for offline environments."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MIRROR_ROOT = Path("vendor") / "wheelhouse"
ARTIFACT_SUFFIXES = (".whl", ".tar.gz", ".tgz", ".zip", ".tar", ".bin", ".pt", ".onnx")
SIGNATURE_SUFFIXES = (".sha256", ".sig", ".asc")


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_signature_candidates(path: Path) -> list[Path]:
    base = path.name
    candidates: list[Path] = []
    for suffix in SIGNATURE_SUFFIXES:
        candidates.append(path.with_name(base + suffix))
    return candidates


@dataclass(slots=True)
class SignatureResult:
    status: str
    reason: str | None = None
    signature_path: Path | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"


@dataclass(slots=True)
class MirrorArtifact:
    name: str
    path: Path
    signature: SignatureResult
    size_bytes: int
    modified_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MirrorStatus:
    root: Path
    generated_at: datetime
    artifacts: list[MirrorArtifact]

    @property
    def verified(self) -> bool:
        return all(artifact.signature.verified for artifact in self.artifacts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "generated_at": self.generated_at.isoformat(),
            "artifacts": [
                {
                    "name": artifact.name,
                    "path": str(artifact.path),
                    "size_bytes": artifact.size_bytes,
                    "modified_at": artifact.modified_at.isoformat(),
                    "signature": {
                        "status": artifact.signature.status,
                        "reason": artifact.signature.reason,
                        "path": (
                            str(artifact.signature.signature_path)
                            if artifact.signature.signature_path
                            else None
                        ),
                    },
                    "extra": artifact.extra,
                }
                for artifact in self.artifacts
            ],
            "summary": {
                "total": len(self.artifacts),
                "verified": sum(
                    1 for artifact in self.artifacts if artifact.signature.verified
                ),
                "missing": sum(
                    1
                    for artifact in self.artifacts
                    if artifact.signature.status == "missing"
                ),
                "failed": sum(
                    1
                    for artifact in self.artifacts
                    if artifact.signature.status == "failed"
                ),
            },
        }


@dataclass(slots=True)
class MirrorUpdateResult:
    mirror_root: Path
    copied: list[str]
    skipped: list[str]
    pruned: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mirror_root": str(self.mirror_root),
            "copied": sorted(self.copied),
            "skipped": sorted(self.skipped),
            "pruned": sorted(self.pruned),
        }


def _match_artifact(path: Path) -> bool:
    lowered = path.name.lower()
    return any(lowered.endswith(suffix) for suffix in ARTIFACT_SUFFIXES)


def _find_signature(path: Path) -> Path | None:
    for candidate in _iter_signature_candidates(path):
        if candidate.exists():
            return candidate
    return None


def _validate_signature(path: Path, *, require_signature: bool) -> SignatureResult:
    signature_path = _find_signature(path)
    if signature_path is None:
        if require_signature:
            return SignatureResult(
                status="missing", reason="signature required but not present"
            )
        return SignatureResult(status="missing", reason="signature not provided")

    if signature_path.suffix == ".sha256" or signature_path.name.endswith(".sha256"):
        expected = signature_path.read_text(encoding="utf-8").strip().split()[0]
        actual = _compute_sha256(path)
        if expected == actual:
            return SignatureResult(status="verified", signature_path=signature_path)
        return SignatureResult(
            status="failed", reason="sha256 mismatch", signature_path=signature_path
        )

    return SignatureResult(
        status="verified", signature_path=signature_path, reason="signature present"
    )


def discover_mirror(root: Path, *, require_signature: bool = True) -> MirrorStatus:
    resolved = root.resolve()
    if not resolved.exists():
        return MirrorStatus(root=resolved, generated_at=datetime.now(UTC), artifacts=[])

    artifacts: list[MirrorArtifact] = []
    for path in sorted(resolved.rglob("*")):
        if not path.is_file() or not _match_artifact(path):
            continue
        stat = path.stat()
        signature = _validate_signature(path, require_signature=require_signature)
        artifacts.append(
            MirrorArtifact(
                name=path.name,
                path=path,
                signature=signature,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )
    return MirrorStatus(
        root=resolved, generated_at=datetime.now(UTC), artifacts=artifacts
    )


def _load_manifest(manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        return {}
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    text = manifest_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid manifest JSON: {manifest_path}") from exc
    return data if isinstance(data, dict) else {}


def _manifest_entry(manifest: dict[str, Any], relative: Path) -> dict[str, Any] | None:
    key_variants = {
        relative.name,
        str(relative).replace("\\", "/"),
        str(relative),
    }
    for key in key_variants:
        entry = manifest.get(key)
        if isinstance(entry, dict):
            return entry
    return None


def _should_copy(
    source: Path,
    target: Path,
    manifest_entry: dict[str, Any] | None,
) -> bool:
    if not target.exists():
        return True
    expected_hash = (
        manifest_entry.get("sha256") if isinstance(manifest_entry, dict) else None
    )
    if expected_hash:
        return _compute_sha256(target) != expected_hash
    return int(source.stat().st_mtime) > int(target.stat().st_mtime)


def _sync_signatures(source: Path, destination: Path) -> None:
    for suffix in SIGNATURE_SUFFIXES:
        candidate = source.with_name(source.name + suffix)
        if not candidate.exists():
            continue
        target = destination.with_name(destination.name + suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)


def _ensure_manifest_signature(
    destination: Path, manifest_entry: dict[str, Any] | None
) -> None:
    if not isinstance(manifest_entry, dict):
        return
    expected_hash = manifest_entry.get("sha256")
    if not expected_hash:
        return
    sha_path = destination.with_name(destination.name + ".sha256")
    if sha_path.exists():
        return
    sha_path.write_text(f"{expected_hash}  {destination.name}\n", encoding="utf-8")


def update_mirror(
    *,
    source: Path,
    mirror_root: Path,
    manifest: Path | None = None,
    prune: bool = False,
) -> MirrorUpdateResult:
    manifest_data = _load_manifest(manifest)
    mirror_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    seen_targets: set[Path] = set()

    for candidate in sorted(source.rglob("*")):
        if not candidate.is_file() or not _match_artifact(candidate):
            continue
        relative = candidate.relative_to(source)
        destination = mirror_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        entry = _manifest_entry(manifest_data, relative)
        if _should_copy(candidate, destination, entry):
            shutil.copy2(candidate, destination)
            copied.append(str(relative))
            _sync_signatures(candidate, destination)
            _ensure_manifest_signature(destination, entry)
        else:
            skipped.append(str(relative))
        seen_targets.add(destination)

    pruned: list[str] = []
    if prune:
        for existing in sorted(mirror_root.rglob("*")):
            if not existing.is_file() or not _match_artifact(existing):
                continue
            if existing not in seen_targets:
                pruned.append(str(existing.relative_to(mirror_root)))
                existing.unlink(missing_ok=True)
                for suffix in SIGNATURE_SUFFIXES:
                    sig_path = existing.with_name(existing.name + suffix)
                    if sig_path.exists():
                        sig_path.unlink(missing_ok=True)

    return MirrorUpdateResult(
        mirror_root=mirror_root, copied=copied, skipped=skipped, pruned=pruned
    )


def render_status(status: MirrorStatus, *, verbose: bool = True) -> str:
    summary = status.to_dict()["summary"]
    lines = [
        "Mirror status",
        f"Root: {status.root}",
        f"Generated: {status.generated_at.isoformat()}",
        "Summary: total={total} verified={verified} missing={missing} failed={failed}".format(
            **summary
        ),
    ]
    if verbose:
        for artifact in status.artifacts:
            detail = f"  - {artifact.name}: {artifact.signature.status}"
            if artifact.signature.reason:
                detail += f" ({artifact.signature.reason})"
            lines.append(detail)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for mirror management."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Manage dependency and model mirrors for offline environments."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display mirror status report",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update mirror from source directory",
    )
    parser.add_argument(
        "--mirror-root",
        type=Path,
        default=DEFAULT_MIRROR_ROOT,
        help="Mirror root directory (default: vendor/wheelhouse)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Source directory for update operation",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Manifest JSON file for update operation",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove artifacts not present in source during update",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        default=False,
        help="Require signature files for all artifacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed artifact list",
    )

    args = parser.parse_args(argv)

    if args.status:
        status = discover_mirror(
            args.mirror_root, require_signature=args.require_signature
        )
        if args.json:
            print(json.dumps(status.to_dict(), indent=2))
        else:
            print(render_status(status, verbose=args.verbose))
        return 0 if status.verified or not args.require_signature else 1

    if args.update:
        if not args.source:
            print("Error: --source is required for update operation", file=sys.stderr)
            return 1
        if not args.source.exists():
            print(f"Error: Source directory not found: {args.source}", file=sys.stderr)
            return 1

        try:
            result = update_mirror(
                source=args.source,
                mirror_root=args.mirror_root,
                manifest=args.manifest,
                prune=args.prune,
            )
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"Mirror updated: {result.mirror_root}")
                print(f"Copied: {len(result.copied)}")
                print(f"Skipped: {len(result.skipped)}")
                print(f"Pruned: {len(result.pruned)}")
                if args.verbose and result.copied:
                    print("\nCopied artifacts:")
                    for name in result.copied:
                        print(f"  - {name}")
            return 0
        except Exception as exc:
            print(f"Error updating mirror: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    import sys

    sys.exit(main())
