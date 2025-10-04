"""Runtime remediation helpers for pipeline execution failures."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_MODULE_NOT_FOUND_RE = re.compile(
    r"ModuleNotFoundError: No module named ['\"](?P<module>[A-Za-z0-9_.]+)['\"]"
)
_IMPORT_ERROR_NO_MODULE_RE = re.compile(
    r"ImportError: No module named ['\"](?P<module>[A-Za-z0-9_.]+)['\"]"
)
_IMPORT_ERROR_FROM_RE = re.compile(
    r"ImportError: cannot import name ['\"][^'\"]+['\"] from ['\"](?P<module>[A-Za-z0-9_.]+)['\"]"
)


@dataclass(slots=True)
class RuntimeSuggestion:
    """A remediation suggestion for a missing import."""

    message: str
    extras: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"message": self.message}
        if self.extras:
            payload["extras"] = list(self.extras)
        if self.packages:
            payload["packages"] = list(self.packages)
        return payload


@dataclass(slots=True)
class SuggestionRule:
    """Rule mapping module name prefixes to remediation suggestions."""

    patterns: tuple[str, ...]
    suggestion: RuntimeSuggestion

    def matches(self, module: str) -> bool:
        for pattern in self.patterns:
            if module == pattern:
                return True
            if module.startswith(pattern + "."):
                return True
        return False


@dataclass(slots=True)
class RuntimeFinding:
    """Represents a missing import discovered in runtime logs."""

    module: str
    exception: str
    message: str
    evidence: list[str] = field(default_factory=list)
    occurrences: int = 0
    suggestions: list[RuntimeSuggestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "exception": self.exception,
            "message": self.message,
            "occurrences": self.occurrences,
            "evidence": list(self.evidence),
            "recommendations": [
                suggestion.to_dict() for suggestion in self.suggestions
            ],
        }


_DEFAULT_SUGGESTIONS: tuple[SuggestionRule, ...] = (
    SuggestionRule(
        patterns=("opentelemetry.exporter", "opentelemetry.sdk"),
        suggestion=RuntimeSuggestion(
            message=(
                "Install prometheus[observability] to satisfy OpenTelemetry exporters"
                " and ensure tracing spans are captured."
            ),
            extras=("observability",),
            packages=("prometheus[observability]",),
        ),
    ),
)


def _iter_lines(text: str) -> Iterable[str]:
    for line in text.splitlines():
        yield line.rstrip()


def _extract_module(line: str) -> tuple[str | None, str | None]:
    match = _MODULE_NOT_FOUND_RE.search(line)
    if match:
        return match.group("module"), "ModuleNotFoundError"
    match = _IMPORT_ERROR_NO_MODULE_RE.search(line)
    if match:
        return match.group("module"), "ImportError"
    match = _IMPORT_ERROR_FROM_RE.search(line)
    if match:
        return match.group("module"), "ImportError"
    return None, None


def _default_suggestion(module: str) -> RuntimeSuggestion:
    root = module.split(".")[0]
    message = (
        f"Install the '{root}' package (e.g. `pip install {root}`) or add the related "
        f"Prometheus extra to satisfy the import."
    )
    return RuntimeSuggestion(message=message, packages=(root,))


class RuntimeRemediator:
    """Analyse runtime logs and suggest dependency remediation steps."""

    def __init__(
        self,
        *,
        rules: Sequence[SuggestionRule] | None = None,
    ) -> None:
        self._rules: tuple[SuggestionRule, ...] = (
            tuple(rules) if rules is not None else _DEFAULT_SUGGESTIONS
        )

    def analyse(self, log_text: str) -> dict[str, object] | None:
        findings = self._parse_log(log_text)
        if not findings:
            return None
        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "findings": [finding.to_dict() for finding in findings],
            "totals": {
                "missing_imports": sum(finding.occurrences for finding in findings),
                "unique_modules": len(findings),
            },
        }
        return summary

    def write_summary(
        self,
        log_path: Path,
        output_path: Path,
    ) -> dict[str, object] | None:
        text = log_path.read_text(encoding="utf-8")
        summary = self.analyse(text)
        if summary is None:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary

    def _parse_log(self, log_text: str) -> list[RuntimeFinding]:
        findings: dict[str, RuntimeFinding] = {}
        for line in _iter_lines(log_text):
            module, exception = _extract_module(line)
            if not module or not exception:
                continue
            entry = findings.get(module)
            if entry is None:
                entry = RuntimeFinding(module=module, exception=exception, message=line)
                findings[module] = entry
            entry.occurrences += 1
            if line not in entry.evidence:
                entry.evidence.append(line)
        for finding in findings.values():
            suggestions = list(self._suggestions_for(finding.module))
            if not suggestions:
                suggestions.append(_default_suggestion(finding.module))
            finding.suggestions = suggestions
        return sorted(findings.values(), key=lambda item: item.module)

    def _suggestions_for(self, module: str) -> Iterable[RuntimeSuggestion]:
        for rule in self._rules:
            if rule.matches(module):
                yield rule.suggestion


__all__ = [
    "RuntimeFinding",
    "RuntimeRemediator",
    "RuntimeSuggestion",
    "SuggestionRule",
]
