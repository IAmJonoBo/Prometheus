"""PII detection and redaction helpers for ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class RedactionFinding:
    """Finding returned by the PII redactor."""

    entity_type: str
    start: int
    end: int
    score: float | None = None


@dataclass(slots=True)
class RedactionResult:
    """Result of applying PII redaction to text."""

    text: str
    findings: list[RedactionFinding] = field(default_factory=list)

    @property
    def entities(self) -> list[str]:
        """Return the unique entity types detected in the text."""

        return sorted({finding.entity_type for finding in self.findings})


@dataclass(slots=True)
class PIIRedactor:
    """Wrap Microsoft Presidio for local PII detection and masking."""

    enabled: bool = True
    language: str = "en"
    placeholder: str = "[REDACTED]"
    _analyzer: Any | None = field(init=False, default=None, repr=False)
    _anonymizer: Any | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore
            from presidio_anonymizer import AnonymizerEngine  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency
            object.__setattr__(self, "enabled", False)
            return
        object.__setattr__(self, "_analyzer", AnalyzerEngine())
        object.__setattr__(self, "_anonymizer", AnonymizerEngine())

    def redact(self, text: str) -> RedactionResult:
        """Detect and mask PII occurrences in ``text``."""

        if not self.enabled or not text.strip():
            return RedactionResult(text=text)
        analyzer = self._analyzer
        anonymizer = self._anonymizer
        if analyzer is None or anonymizer is None:  # pragma: no cover - disabled at runtime
            return RedactionResult(text=text)
        results = analyzer.analyze(text=text, language=self.language)
        if not results:
            return RedactionResult(text=text)
        operators = {
            result.entity_type: {"type": "replace", "new_value": self.placeholder}
            for result in results
        }
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        findings = [
            RedactionFinding(
                entity_type=result.entity_type,
                start=result.start,
                end=result.end,
                score=getattr(result, "score", None),
            )
            for result in results
        ]
        return RedactionResult(text=anonymized.text, findings=findings)

