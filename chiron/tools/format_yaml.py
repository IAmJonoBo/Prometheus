"""Utility for formatting YAML files consistently across the repository.

This script wraps the ``yamlfmt`` CLI with a few conveniences:

* Removes macOS resource fork files (``._foo.yml``) that frequently trip lint
  checks when the repository is edited on macOS hosts.
* Runs ``yamlfmt`` with doublestar glob semantics so that nested directories
  are handled without needing to specify every path manually.
* Supports a ``--check`` mode that only reports formatting diffs without
  modifying files, mirroring ``yamlfmt -lint``.
* Provides Git-aware discovery flags (``--changed``, ``--staged``) so that only
    recently modified YAML files are processed, making it easy to autorun the
    formatter in CI or pre-commit hooks.
* Understands repository-wide scanning (``--all-tracked``) with optional include
    and exclude globs, plus a TOML configuration file to centralize defaults.
* Performs post-format validations to highlight literal block indentation
    issues and YAML parse errors before they land in CI.

Example usage::

    poetry run python scripts/format_yaml.py .github/workflows
    poetry run python scripts/format_yaml.py --check configs
        poetry run python scripts/format_yaml.py --changed --check
        poetry run python scripts/format_yaml.py --staged
        poetry run python scripts/format_yaml.py --all-tracked --include "infra/**"

If no paths are provided, the current working directory is used.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RESOURCE_FORK_PREFIX = "._"
YAML_SUFFIXES = {".yml", ".yaml"}
DEFAULT_PATHS = (Path(".github/workflows"), Path("configs"))
DEFAULT_BASE_REF = "origin/main"
DEFAULT_CHUNK_SIZE = 64
DEFAULT_CONFIG_PATH = Path("scripts/format_yaml.toml")
PARSE_ERROR_PATTERN = re.compile(
    r"^(?P<path>.+\.ya?ml): yaml: line (?P<line>\d+): (?P<message>.*)$"
)

MULTILINE_QUOTED_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<key>[^:#]+):\s*\"(?P<value>(?:[^\"\\]|\\.)*)\"\s*$"
)

YAMLFMT_CONFIG_PATH = Path(".yamlfmt")
YAMLLINT_CONFIG_PATH = Path(".yamllint.yaml")
CACHE_PATH = Path(".cache/format_yaml_helper.json")
CACHE_VERSION = 2
TEMPLATE_FILENAME_MARKERS = (".template.", ".tmpl.", ".skeleton.", ".example.")
TEMPLATE_DIRECTORY_HINTS = {"templates", "template", "skeleton"}
CHECK_JSONSCHEMA_CMD = "check-jsonschema"
CHECK_JSONSCHEMA_BUILTIN = "vendor.github-workflows"
CHECK_JSONSCHEMA_LEGACY_SCHEMA = "github-workflows"
REPO_ROOT = Path.cwd().resolve()


@dataclass
class ValidationIssue:
    category: str
    message: str
    path: Path | None = None
    line: int | None = None
    severity: str = "error"

    def format_console(self) -> str:
        location = str(self.path) if self.path else "(repository)"
        if self.line is not None:
            location += f":{self.line}"
        prefix = "[warning]" if self.severity == "warning" else "[error]"
        message = (self.message or "").strip()
        if message:
            message = re.sub(r"\s+", " ", message)
        else:
            message = "No additional details provided."
        return f"{prefix} {self.category}: {location}: {message}"


def _has_errors(issues: Sequence[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _has_warnings(issues: Sequence[ValidationIssue]) -> bool:
    return any(issue.severity == "warning" for issue in issues)


def _should_fail(issues: Sequence[ValidationIssue], *, fail_on_warnings: bool) -> bool:
    if _has_errors(issues):
        return True
    if fail_on_warnings and _has_warnings(issues):
        return True
    return False


def _issues_exit_code(
    issues: Sequence[ValidationIssue], *, fail_on_warnings: bool
) -> int:
    return int(_should_fail(issues, fail_on_warnings=fail_on_warnings))


def _is_template_like(path: Path) -> bool:
    name = path.name.lower()
    if any(marker in name for marker in TEMPLATE_FILENAME_MARKERS):
        return True
    dir_names = {part.lower() for part in path.parts[:-1]}
    return bool(dir_names.intersection(TEMPLATE_DIRECTORY_HINTS))


def _should_process_yaml(candidate: Path) -> bool:
    return (
        candidate.suffix in YAML_SUFFIXES
        and candidate.is_file()
        and not _is_template_like(candidate)
    )


def _is_workflow_file(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts):
        if (
            part == ".github"
            and index + 1 < len(parts)
            and parts[index + 1] == "workflows"
        ):
            return True
    return False


def _load_yaml_document(path: Path) -> tuple[Any | None, list[ValidationIssue]]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return None, [
            ValidationIssue(
                "config",
                "PyYAML is required to parse configuration files; install the"
                " 'pyyaml' package to enable contract checks.",
                path=None,
                severity="warning",
            )
        ]

    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        return None, [
            ValidationIssue(
                "config",
                "Required configuration file is missing.",
                path=path,
            )
        ]
    except OSError as exc:
        return None, [
            ValidationIssue(
                "config",
                f"Unable to read configuration file ({exc}).",
                path=path,
            )
        ]
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        return None, [
            ValidationIssue(
                "config",
                f"Failed to parse configuration: {exc}.",
                path=path,
            )
        ]

    return data or {}, []


def _check_yamlfmt_contract() -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    data, load_issues = _load_yaml_document(YAMLFMT_CONFIG_PATH)
    issues.extend(load_issues)
    if data is None:
        return issues

    if not isinstance(data, Mapping):
        issues.append(
            ValidationIssue(
                "yamlfmt",
                "Expected a mapping at the top level of .yamlfmt.",
                path=YAMLFMT_CONFIG_PATH,
            )
        )
        return issues

    formatter = data.get("formatter") if isinstance(data, Mapping) else None
    if not isinstance(formatter, Mapping):
        issues.append(
            ValidationIssue(
                "yamlfmt",
                "Missing 'formatter' section in .yamlfmt.",
                path=YAMLFMT_CONFIG_PATH,
            )
        )
        return issues

    expected_settings = {
        "type": "basic",
        "retain_line_breaks": True,
        "trim_trailing_whitespace": True,
        "insert_final_newline": True,
    }
    for key, expected in expected_settings.items():
        actual = formatter.get(key)
        if actual != expected:
            issues.append(
                ValidationIssue(
                    "yamlfmt",
                    f"Expected formatter.{key} to be {expected!r} (found {actual!r}).",
                    path=YAMLFMT_CONFIG_PATH,
                )
            )

    max_line_length = formatter.get("max_line_length")
    if max_line_length not in (0, None):
        issues.append(
            ValidationIssue(
                "yamlfmt",
                "formatter.max_line_length must be 0 to preserve literal wrapping.",
                path=YAMLFMT_CONFIG_PATH,
            )
        )

    return issues


def _normalise_yamllint_extends(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
        return {str(item) for item in value if item}
    return set()


def _validate_yamllint_rules(rules: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    comments_rule = rules.get("comments")
    if (
        not isinstance(comments_rule, Mapping)
        or comments_rule.get("min-spaces-from-content") != 2
    ):
        issues.append(
            ValidationIssue(
                "yamllint",
                "comments.min-spaces-from-content must be set to 2 to enforce"
                " inline comment spacing.",
                path=YAMLLINT_CONFIG_PATH,
            )
        )

    line_length_rule = rules.get("line-length")
    if not isinstance(line_length_rule, Mapping):
        issues.append(
            ValidationIssue(
                "yamllint",
                "line-length rule must be configured to allow long command" " strings.",
                path=YAMLLINT_CONFIG_PATH,
            )
        )
    else:
        allow_long = line_length_rule.get("allow-non-breakable-words")
        if allow_long is not True:
            issues.append(
                ValidationIssue(
                    "yamllint",
                    "line-length.allow-non-breakable-words must be true to"
                    " support long shell commands.",
                    path=YAMLLINT_CONFIG_PATH,
                )
            )
        max_length = line_length_rule.get("max")
        if not isinstance(max_length, int) or max_length < 140:
            issues.append(
                ValidationIssue(
                    "yamllint",
                    "line-length.max must be at least 140 characters.",
                    path=YAMLLINT_CONFIG_PATH,
                )
            )

    return issues


def _check_yamllint_contract() -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    data, load_issues = _load_yaml_document(YAMLLINT_CONFIG_PATH)
    issues.extend(load_issues)
    if data is None:
        return issues

    if not isinstance(data, Mapping):
        issues.append(
            ValidationIssue(
                "yamllint",
                "Expected a mapping at the top level of .yamllint.yaml.",
                path=YAMLLINT_CONFIG_PATH,
            )
        )
        return issues

    extends = _normalise_yamllint_extends(data.get("extends"))
    if "default" not in extends:
        issues.append(
            ValidationIssue(
                "yamllint",
                "Configuration must extend the 'default' rule set.",
                path=YAMLLINT_CONFIG_PATH,
            )
        )

    rules = data.get("rules")
    if not isinstance(rules, Mapping):
        issues.append(
            ValidationIssue(
                "yamllint",
                "Missing 'rules' section in .yamllint.yaml.",
                path=YAMLLINT_CONFIG_PATH,
            )
        )
        return issues

    issues.extend(_validate_yamllint_rules(rules))

    return issues


def collect_config_contract_issues() -> list[ValidationIssue]:
    issues = _check_yamlfmt_contract()
    issues.extend(_check_yamllint_contract())
    return issues


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "Directories or files to process. Default includes .github/workflows "
            "and configs."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=("Run yamlfmt in lint mode and exit with non-zero status on diffs."),
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip removal of macOS resource fork files before formatting.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Include YAML files changed relative to --base-ref (default origin/main).",
    )
    parser.add_argument(
        "--base-ref",
        default=DEFAULT_BASE_REF,
        help=(
            "Git reference to diff against when using --changed (default: origin/main)."
        ),
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Include YAML files staged in the Git index.",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked YAML files detected by Git.",
    )
    parser.add_argument(
        "--all-tracked",
        action="store_true",
        help="Include all tracked YAML files reported by git ls-files.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help=(
            "Glob pattern to include (can be specified multiple times). Patterns "
            "are matched against the POSIX-style path; defaults to everything."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Glob pattern to exclude (can be specified multiple times). Patterns "
            "are matched against the POSIX-style path."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Number of files to pass to yamlfmt per invocation (default: 64).",
    )
    parser.add_argument(
        "--yamlfmt",
        default="yamlfmt",
        help="Path to the yamlfmt executable (defaults to looking on PATH).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "Path to a TOML configuration file (defaults to scripts/format_yaml.toml "
            "when present)."
        ),
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        help=(
            "Optional path to write a Markdown summary. Defaults to the value"
            " of GITHUB_STEP_SUMMARY when unset."
        ),
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Treat warnings emitted by helper validations as failures.",
    )
    args = parser.parse_args(argv)
    paths_provided = bool(args.paths)
    if not args.paths:
        args.paths = list(DEFAULT_PATHS)
    args.paths_provided = paths_provided
    return args


def iter_yaml_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if _should_process_yaml(path):
                yield path
            continue
        for candidate in path.rglob("*"):
            if _should_process_yaml(candidate):
                yield candidate


def remove_resource_forks(paths: Iterable[Path]) -> list[Path]:
    removed: list[Path] = []
    for candidate in paths:
        if candidate.name.startswith(RESOURCE_FORK_PREFIX) and candidate.is_file():
            candidate.unlink(missing_ok=True)
            removed.append(candidate)
    return removed


def prepare_command(executable: str, *args: str) -> list[str]:
    resolved = shutil.which(executable) if not os.path.isabs(executable) else executable
    if resolved is None:
        raise FileNotFoundError(f"Unable to locate executable: {executable}")
    return [resolved, *args]


def _resolve_git() -> str | None:
    return shutil.which("git")


def _run_git_command(*git_args: str) -> list[str]:
    git_executable = _resolve_git()
    if git_executable is None:
        print(
            "Git is not available on PATH; skipping git-assisted discovery.",
            file=sys.stderr,
        )
        return []

    completed = subprocess.run(  # noqa: S603
        [git_executable, *git_args],
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        message = completed.stderr.strip() or "(no error output)"
        print(
            "Git command `git {} ` failed (exit code {}): {}".format(
                " ".join(git_args), completed.returncode, message
            ),
            file=sys.stderr,
        )
        return []

    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _filter_yaml_paths(paths: Iterable[str | Path]) -> set[Path]:
    filtered: set[Path] = set()
    for raw in paths:
        candidate = Path(raw)
        if _should_process_yaml(candidate):
            filtered.add(Path(os.path.abspath(candidate)))
    return filtered


def _collect_git_tracked() -> set[Path]:
    return _filter_yaml_paths(_run_git_command("ls-files", "*.yml", "*.yaml"))


def _collect_git_changed(base_ref: str) -> set[Path]:
    diff_targets = [f"{base_ref}...HEAD", base_ref]
    paths: list[str] = []
    for target in diff_targets:
        paths = _run_git_command("diff", "--name-only", target)
        if paths:
            break

    if not paths:
        fallback = _resolve_git_fallback_ref()
        if fallback:
            print(
                f"Base ref '{base_ref}' not found; falling back to '{fallback}'.",
                file=sys.stderr,
            )
            paths = _run_git_command("diff", "--name-only", fallback)
    return _filter_yaml_paths(paths)


def _collect_git_staged() -> set[Path]:
    return _filter_yaml_paths(_run_git_command("diff", "--name-only", "--cached"))


def _collect_git_untracked() -> set[Path]:
    return _filter_yaml_paths(
        _run_git_command("ls-files", "--others", "--exclude-standard")
    )


def _resolve_git_fallback_ref() -> str | None:
    head_minus_one = _run_git_command("rev-parse", "HEAD~1")
    if head_minus_one:
        return "HEAD~1"
    head = _run_git_command("rev-parse", "HEAD")
    if head:
        return "HEAD"
    return None


def load_config(config_path: Path | None) -> dict[str, Any]:
    target = config_path or DEFAULT_CONFIG_PATH
    if not target or not target.exists():
        return {}
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"Failed to read config {target}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(
            f"Config {target} did not contain a TOML table at the top level.",
            file=sys.stderr,
        )
        return {}
    print(f"Loaded YAML helper config from {target}")
    return data


def _normalise_pattern_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values]
    patterns: list[str] = []
    for value in values:
        if isinstance(value, str):
            patterns.append(value)
    return patterns


def apply_glob_filters(
    paths: Sequence[Path], include: Sequence[str], exclude: Sequence[str]
) -> list[Path]:
    if include:
        paths = [
            path
            for path in paths
            if any(fnmatch.fnmatch(path.as_posix(), pattern) for pattern in include)
        ]
    if exclude:
        paths = [
            path
            for path in paths
            if not any(fnmatch.fnmatch(path.as_posix(), pattern) for pattern in exclude)
        ]
    return list(paths)


def _decode_quoted_value(raw: str) -> str | None:
    try:
        return ast.literal_eval(f'"{raw}"')
    except (SyntaxError, ValueError):
        return None


def _convert_multiline_quoted_scalars(content: str) -> tuple[str, bool]:
    if "\\n" not in content:
        return content, False

    trailing_newline = content.endswith("\n")
    lines = content.splitlines()
    converted: list[str] = []
    changed = False

    for line in lines:
        match = MULTILINE_QUOTED_PATTERN.match(line)
        if not match:
            converted.append(line)
            continue

        raw_value = match.group("value")
        if "\\n" not in raw_value:
            converted.append(line)
            continue

        decoded = _decode_quoted_value(raw_value)
        if decoded is None:
            converted.append(line)
            continue

        indent = match.group("indent")
        key = match.group("key").rstrip()
        block_lines = [f"{indent}{key}: |"]
        for segment in decoded.split("\n"):
            if segment:
                block_lines.append(f"{indent}  {segment}")
            else:
                block_lines.append(f"{indent}  ")
        converted.extend(block_lines)
        changed = True

    result = "\n".join(converted)
    if trailing_newline:
        result += "\n"
    return result, changed


def _is_char_escaped(text: str, index: int) -> bool:
    escapes = 0
    position = index - 1
    while position >= 0 and text[position] == "\\":
        escapes += 1
        position -= 1
    return escapes % 2 == 1


def _locate_comment_index(line: str) -> int | None:
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#"):
        return None

    in_single = False
    in_double = False

    for index, char in enumerate(line):
        if char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return index
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single and not _is_char_escaped(line, index):
            in_double = not in_double
    return None


def _ensure_comment_spacing(content: str) -> tuple[str, bool]:
    trailing_newline = content.endswith("\n")
    lines = content.splitlines()
    adjusted: list[str] = []
    changed = False

    for line in lines:
        comment_index = _locate_comment_index(line)
        if comment_index is None:
            adjusted.append(line)
            continue

        before = line[:comment_index]
        after = line[comment_index:]
        stripped_before = before.rstrip()
        whitespace_count = len(before) - len(stripped_before)
        if whitespace_count >= 2:
            adjusted.append(line)
            continue

        new_line = f"{stripped_before}  {after}"
        adjusted.append(new_line)
        if new_line != line:
            changed = True

    result = "\n".join(adjusted)
    if trailing_newline:
        result += "\n"
    return result, changed


def _strip_trailing_whitespace(content: str) -> tuple[str, bool]:
    trailing_newline = content.endswith("\n")
    lines = content.splitlines()
    cleaned: list[str] = []
    changed = False

    for line in lines:
        trimmed = line.rstrip(" \t")
        if trimmed != line:
            changed = True
        cleaned.append(trimmed)

    result = "\n".join(cleaned)
    if trailing_newline or content.endswith("\n\n"):
        result += "\n"
    return result, changed


def _normalise_yaml_content(content: str, *, phase: str) -> tuple[str, bool]:
    updated_content = content
    changed = False

    if phase in {"pre", "both"}:
        updated_content, pre_changed = _convert_multiline_quoted_scalars(
            updated_content
        )
        changed = changed or pre_changed

    if phase in {"post", "both"}:
        updated_content, comment_changed = _ensure_comment_spacing(updated_content)
        changed = changed or comment_changed
        updated_content, trailing_changed = _strip_trailing_whitespace(updated_content)
        changed = changed or trailing_changed

    return updated_content, changed


def apply_pre_format_fixes(
    files: Sequence[Path], modify: bool, *, phase: str
) -> list[Path]:
    updated: list[Path] = []
    for path in files:
        try:
            original = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"{path}: unable to read for helper normalization ({exc})",
                file=sys.stderr,
            )
            continue

        normalised, changed = _normalise_yaml_content(original, phase=phase)
        if not changed:
            continue

        if modify:
            try:
                path.write_text(normalised, encoding="utf-8")
            except OSError as exc:
                print(
                    f"{path}: failed to write helper normalization ({exc})",
                    file=sys.stderr,
                )
                continue
        updated.append(path)
    return updated


def _handle_helper_normalisations(
    files: Sequence[Path], check_mode: bool, *, phase: str
) -> None:
    helper_updates = apply_pre_format_fixes(files, modify=not check_mode, phase=phase)
    if not helper_updates:
        return

    action = (
        "Helper detected YAML normalisations required for"
        if check_mode
        else "Applied helper YAML normalisations to"
    )
    print(action + ":")
    for path in helper_updates:
        print(f"  - {path}")
    if check_mode:
        print("Run without --check to apply these fixes.")


def _is_literal_block_start(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("run: |")


def _inspect_literal_block(
    lines: list[str], start_index: int, base_indent: int
) -> tuple[int, list[tuple[int, str]]]:
    issues: list[tuple[int, str]] = []
    min_indent = base_indent + 2
    index = start_index + 1
    total = len(lines)
    while index < total:
        candidate = lines[index]
        stripped = candidate.rstrip("\n")
        stripped_content = stripped.lstrip()
        if stripped_content == "":
            index += 1
            continue
        indent = len(candidate) - len(candidate.lstrip(" "))
        is_comment = stripped_content.startswith("#")
        if indent <= base_indent and not is_comment:
            break
        if not is_comment and indent < min_indent:
            issues.append(
                (
                    index + 1,
                    "literal block line is indented "
                    f"{indent} spaces; expected at least {min_indent}",
                )
            )
        index += 1
    return index, issues


def _scan_literal_block_issues(lines: list[str]) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if _is_literal_block_start(line):
            base_indent = len(line) - len(line.lstrip(" "))
            index, block_issues = _inspect_literal_block(lines, index, base_indent)
            issues.extend(block_issues)
        else:
            index += 1
    return issues


def check_literal_blocks(paths: Sequence[Path]) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError as exc:
            warnings.append(
                ValidationIssue(
                    "literal-block",
                    f"Unable to read file for literal checks ({exc}).",
                    path=path,
                )
            )
            continue
        for line_no, message in _scan_literal_block_issues(lines):
            warnings.append(
                ValidationIssue(
                    "literal-block",
                    message,
                    path=path,
                    line=line_no,
                )
            )
    return warnings


def validate_yaml_structures(paths: Sequence[Path]) -> list[ValidationIssue]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return []

    errors: list[ValidationIssue] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as handle:
                content = handle.read()
        except OSError as exc:
            errors.append(
                ValidationIssue(
                    "yaml-parse",
                    f"Unable to read file for YAML validation ({exc}).",
                    path=path,
                )
            )
            continue
        try:
            for _ in yaml.safe_load_all(content):
                # Exhaust the generator to surface parsing errors while ignoring content.
                continue
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            mark = getattr(exc, "problem_mark", None)
            if mark is not None:
                errors.append(
                    ValidationIssue(
                        "yaml-parse",
                        str(getattr(exc, "problem", exc)),
                        path=path,
                        line=mark.line + 1,
                    )
                )
            else:
                errors.append(
                    ValidationIssue(
                        "yaml-parse",
                        f"YAML parse error: {exc}",
                        path=path,
                    )
                )
    return errors


def _suggest_indent_adjustment(file_lines: list[str], line_number: int) -> str | None:
    offending_line = file_lines[line_number - 1]
    if not offending_line.strip():
        return None
    offending_indent = len(offending_line) - len(offending_line.lstrip(" "))
    if offending_indent == 0:
        return None

    previous_index = line_number - 2
    while previous_index >= 0:
        candidate = file_lines[previous_index]
        if candidate.strip():
            break
        previous_index -= 1
    else:
        return None

    previous_indent = len(file_lines[previous_index]) - len(
        file_lines[previous_index].lstrip(" ")
    )
    if previous_indent <= offending_indent:
        return None

    diff = previous_indent - offending_indent
    context_hint = ""
    for idx in range(previous_index, max(-1, previous_index - 12), -1):
        if "run: |" in file_lines[idx]:
            context_hint = " within the same `run: |` literal block"
            break

    recommended = offending_indent + diff
    return (
        "Indentation hint: line "
        f"{line_number} is indented {offending_indent} spaces, but the previous "
        f"code line {previous_index + 1} uses {previous_indent}{context_hint}. "
        f"Increase indentation on line {line_number} by at least {diff} spaces "
        f"(to {recommended}) to keep it inside the block."
    )


def _emit_parse_error_context(stderr: str) -> None:
    for raw in stderr.splitlines():
        match = PARSE_ERROR_PATTERN.match(raw.strip())
        if not match:
            continue
        path = Path(match.group("path")).resolve()
        try:
            line_number = int(match.group("line"))
        except ValueError:
            continue
        message = match.group("message")
        print(f"\nParse error detected in {path} (line {line_number}): {message}")
        if not path.exists():
            print("File does not exist on disk; skipping snippet preview.")
            continue
        start = max(1, line_number - 3)
        end = line_number + 2
        with path.open(encoding="utf-8") as handle:
            file_lines = handle.readlines()
        for idx in range(start, min(end, len(file_lines)) + 1):
            prefix = "-->" if idx == line_number else "   "
            content = file_lines[idx - 1].rstrip("\n")
            print(f"{prefix} {idx:4}: {content}")

        hint = _suggest_indent_adjustment(file_lines, line_number)
        if hint:
            print(hint)


def run_yamlfmt(yamlfmt: str, check: bool, files: list[Path]) -> int:
    if not files:
        print("No YAML files found for formatting.")
        return 0

    cmd = ["-dstar"]
    if YAMLFMT_CONFIG_PATH.exists():
        cmd.extend(["-conf", str(YAMLFMT_CONFIG_PATH)])
    if check:
        cmd.append("-lint")
    cmd.extend(str(path) for path in files)

    command = prepare_command(yamlfmt, *cmd)
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")

    if completed.returncode != 0:
        print(
            "yamlfmt reported formatting differences. "
            "Run without --check to apply fixes.",
            file=sys.stderr,
        )
        _emit_parse_error_context(completed.stderr or "")
    return completed.returncode


def chunk_paths(
    paths: list[Path], chunk_size: int = DEFAULT_CHUNK_SIZE
) -> Iterable[list[Path]]:
    chunk_size = max(1, chunk_size)
    for index in range(0, len(paths), chunk_size):
        yield paths[index : index + chunk_size]


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _apply_boolean_default(
    args: argparse.Namespace, config_data: Mapping[str, Any], name: str
) -> None:
    if getattr(args, name):
        return
    if config_data.get(name):
        setattr(args, name, True)


def _apply_config_defaults(
    args: argparse.Namespace, config_data: Mapping[str, Any]
) -> None:
    if args.chunk_size == DEFAULT_CHUNK_SIZE and "chunk_size" in config_data:
        try:
            args.chunk_size = max(1, int(config_data["chunk_size"]))
        except (TypeError, ValueError):
            print(
                f"Ignoring invalid chunk_size in config: {config_data['chunk_size']}",
                file=sys.stderr,
            )
    if args.yamlfmt == "yamlfmt" and config_data.get("yamlfmt"):
        args.yamlfmt = str(config_data["yamlfmt"])

    for name in ("skip_cleanup", "all_tracked", "changed"):
        _apply_boolean_default(args, config_data, name)

    if args.base_ref == DEFAULT_BASE_REF and config_data.get("base_ref"):
        args.base_ref = str(config_data["base_ref"])


def _compile_pattern_sets(
    args: argparse.Namespace, config_data: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    include_patterns = _normalise_pattern_list(config_data.get("include"))
    exclude_patterns = _normalise_pattern_list(config_data.get("exclude"))
    include_patterns.extend(_normalise_pattern_list(args.include))
    exclude_patterns.extend(_normalise_pattern_list(args.exclude))
    return (
        _dedupe_preserve_order(include_patterns),
        _dedupe_preserve_order(exclude_patterns),
    )


def _determine_target_paths(
    args: argparse.Namespace, config_data: Mapping[str, Any]
) -> list[Path]:
    config_paths = [
        Path(os.path.abspath(path)) for path in config_data.get("paths", []) if path
    ]
    if not args.paths_provided and config_paths:
        args.paths = config_paths
        args.paths_provided = True

    unique_paths = list(
        dict.fromkeys(Path(os.path.abspath(path)) for path in args.paths)
    )
    return unique_paths or [Path.cwd()]


def configure_runtime(
    args: argparse.Namespace,
) -> tuple[list[Path], list[str], list[str]]:
    config_data = load_config(args.config)
    _apply_config_defaults(args, config_data)
    include_patterns, exclude_patterns = _compile_pattern_sets(args, config_data)
    target_paths = _determine_target_paths(args, config_data)
    return target_paths, include_patterns, exclude_patterns


def _collect_git_candidates(args: argparse.Namespace) -> list[Path]:
    operations: list[tuple[bool, Callable[[], Iterable[Path]]]] = [
        (args.changed, lambda: _collect_git_changed(args.base_ref)),
        (args.staged, _collect_git_staged),
        (args.include_untracked, _collect_git_untracked),
        (args.all_tracked, _collect_git_tracked),
    ]
    candidates: list[Path] = []
    for enabled, getter in operations:
        if not enabled:
            continue
        candidates.extend(getter())
    return candidates


def discover_yaml_files(
    args: argparse.Namespace,
    search_paths: Sequence[Path],
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
) -> tuple[list[Path], bool]:
    git_requested = any(
        (args.changed, args.staged, args.include_untracked, args.all_tracked)
    )
    candidates = _collect_git_candidates(args) if git_requested else []
    used_path_scan = args.paths_provided or not git_requested
    if used_path_scan:
        candidates.extend(iter_yaml_files(search_paths))

    normalized = sorted({Path(os.path.abspath(path)) for path in candidates})
    filtered = apply_glob_filters(normalized, include_patterns, exclude_patterns)
    git_only = git_requested and not used_path_scan
    return filtered, git_only


def collect_post_format_issues(paths: Sequence[Path]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(check_literal_blocks(paths))
    issues.extend(validate_yaml_structures(paths))
    return issues


def _emit_validation_report(issues: Sequence[ValidationIssue]) -> None:
    if not issues:
        return

    print("\nValidation findings:")
    for issue in issues:
        print(issue.format_console())


def _render_issue_summary(issue: ValidationIssue) -> list[str]:
    icon = "⚠️" if issue.severity == "warning" else "❌"
    location = str(issue.path) if issue.path else "(repository)"
    if issue.line is not None:
        location += f":{issue.line}"
    bullet = f"- {icon} {issue.category}: {location} — {issue.message}"
    return textwrap.wrap(
        bullet,
        width=80,
        subsequent_indent="  ",
    )


def write_summary(
    processed_files: Sequence[Path],
    issues: Sequence[ValidationIssue],
    *,
    check_mode: bool,
    summary_path: Path | None,
) -> None:
    target = summary_path or os.getenv("GITHUB_STEP_SUMMARY")
    if not target:
        return

    summary_lines = ["# YAML helper summary", ""]
    mode = "Check" if check_mode else "Format"
    summary_lines.append(f"- Mode: {mode}")
    summary_lines.append(f"- Files processed: {len(processed_files)}")
    summary_lines.append(f"- Issues: {len(issues)}")
    summary_lines.append("")

    if issues:
        summary_lines.append("## Findings")
        for issue in issues:
            summary_lines.extend(_render_issue_summary(issue))
        summary_lines.append("")
    else:
        summary_lines.append("No validation issues detected.")
        summary_lines.append("")

    summary_text = "\n".join(summary_lines)
    target_path = Path(target)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("a", encoding="utf-8") as handle:
            handle.write(summary_text)
            if not summary_text.endswith("\n"):
                handle.write("\n")
    except OSError as exc:
        print(f"Failed to write summary to {target_path}: {exc}", file=sys.stderr)


def _serialise_cache_key(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {"version": CACHE_VERSION, "files": {}}
    try:
        with CACHE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "files": {}}
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "files": {}}
    files = data.get("files")
    if not isinstance(files, dict):
        return {"version": CACHE_VERSION, "files": {}}
    return {"version": CACHE_VERSION, "files": files}


def save_cache(cache_data: Mapping[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(cache_data, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        print(f"Failed to write cache to {CACHE_PATH}: {exc}", file=sys.stderr)


def filter_cached_files(
    files: Sequence[Path], cache_files: MutableMapping[str, Any]
) -> tuple[list[Path], list[Path]]:
    active: list[Path] = []
    skipped: list[Path] = []
    for path in files:
        cache_key = _serialise_cache_key(path)
        entry = cache_files.get(cache_key)
        if not isinstance(entry, Mapping):
            active.append(path)
            continue
        try:
            stat = path.stat()
        except OSError:
            active.append(path)
            continue
        cached_mtime = entry.get("mtime_ns")
        cached_size = entry.get("size")
        if cached_mtime == stat.st_mtime_ns and cached_size == stat.st_size:
            skipped.append(path)
            continue
        active.append(path)
    return active, skipped


def update_cache_entries(
    cache_data: MutableMapping[str, Any], files: Sequence[Path]
) -> bool:
    if not files:
        return False
    cache_files = cache_data.setdefault("files", {})
    updated = False
    for path in files:
        cache_key = _serialise_cache_key(path)
        try:
            content = path.read_bytes()
            stat = path.stat()
        except OSError:
            if cache_key in cache_files:
                cache_files.pop(cache_key, None)
                updated = True
            continue
        cache_files[cache_key] = {
            "hash": hashlib.sha256(content).hexdigest(),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
        updated = True
    cache_data["version"] = CACHE_VERSION
    return updated


def _prepare_candidate_files(
    files: Sequence[Path], *, skip_cleanup: bool
) -> list[Path]:
    candidates = list(files)
    if skip_cleanup:
        return [path for path in candidates if path.exists()]
    removed = remove_resource_forks(candidates)
    if removed:
        print("Removed resource fork files:")
        for path in removed:
            print(f"  - {path}")
    return [path for path in candidates if path.exists()]


def _apply_cache_filter(
    files: list[Path],
) -> tuple[list[Path], list[Path], dict[str, Any]]:
    cache_data = load_cache()
    cache_files = cache_data.setdefault("files", {})
    filtered, skipped = filter_cached_files(files, cache_files)
    if skipped:
        print("Skipped YAML files via cache:")
        for path in skipped:
            print(f"  - {path}")
    return filtered, skipped, cache_data


def _extract_schema_entries(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("validation_errors", "errors", "items", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [entry for entry in candidate if isinstance(entry, Mapping)]
        return []
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, Mapping)]
    return []


def _parse_schema_issue_entry(entry: Mapping[str, Any]) -> ValidationIssue:
    filename = entry.get("filename")
    message = str(
        entry.get("message") or entry.get("error") or "Schema validation failed"
    )
    line: int | None = None
    location = entry.get("location")
    if isinstance(location, Mapping):
        line_value = location.get("line")
        if isinstance(line_value, int):
            line = line_value
        elif isinstance(line_value, str) and line_value.isdigit():
            line = int(line_value)
    else:
        line_value = entry.get("line")
        if isinstance(line_value, int):
            line = line_value
    target_path = Path(filename) if isinstance(filename, str) else None
    return ValidationIssue(
        "schema",
        message,
        path=target_path,
        line=line,
        severity="warning",
    )


def _parse_schema_issues_from_json(payload: Any) -> list[ValidationIssue]:
    return [
        _parse_schema_issue_entry(entry) for entry in _extract_schema_entries(payload)
    ]


def _build_check_jsonschema_commands(
    files: Sequence[Path],
) -> tuple[list[tuple[list[str], str]] | None, list[ValidationIssue]]:
    try:
        primary = prepare_command(
            CHECK_JSONSCHEMA_CMD,
            "--builtin-schema",
            CHECK_JSONSCHEMA_BUILTIN,
            "--output-format",
            "json",
            *[str(path) for path in files],
        )
    except FileNotFoundError:
        issue = ValidationIssue(
            "schema",
            "check-jsonschema CLI not found; install the 'check-jsonschema' package"
            " to enable workflow schema validation.",
            severity="warning",
        )
        return None, [issue]

    legacy = prepare_command(
        CHECK_JSONSCHEMA_CMD,
        "--schema-name",
        CHECK_JSONSCHEMA_LEGACY_SCHEMA,
        "--output-format",
        "json",
        *[str(path) for path in files],
    )

    return [(primary, "--builtin-schema"), (legacy, "--schema-name")], []


def _parse_schema_stream(stream: str) -> list[ValidationIssue]:
    stripped = stream.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return _parse_schema_issues_from_json(payload)


def validate_github_workflow_schemas(files: Sequence[Path]) -> list[ValidationIssue]:
    workflow_files = [path for path in files if _is_workflow_file(path)]
    if not workflow_files:
        return []

    command_entries, initial_issues = _build_check_jsonschema_commands(workflow_files)
    if command_entries is None:
        return initial_issues

    last_message: str | None = None
    for command, option_name in command_entries:
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
        )

        if completed.returncode == 0:
            return []

        for stream in (completed.stdout, completed.stderr):
            issues = _parse_schema_stream(stream)
            if issues:
                return issues

        combined_output = "\n".join(
            stream.strip()
            for stream in (completed.stderr, completed.stdout)
            if stream.strip()
        )
        last_message = combined_output or None

        if combined_output and f"No such option: {option_name}" in combined_output:
            # Try the next candidate which may target an older CLI version.
            continue

        break

    message = last_message or "check-jsonschema reported errors without details."
    return [
        ValidationIssue(
            "schema",
            message,
            severity="warning",
        )
    ]


def process_yaml_files(
    args: argparse.Namespace,
    yaml_files: Sequence[Path],
    git_only: bool,
    *,
    fail_on_warnings: bool,
) -> tuple[int, list[Path], list[ValidationIssue]]:
    issues = collect_config_contract_issues()
    if _should_fail(issues, fail_on_warnings=fail_on_warnings):
        return 1, [], issues

    files = _prepare_candidate_files(yaml_files, skip_cleanup=args.skip_cleanup)
    files, _, cache_data = _apply_cache_filter(files)

    if not files:
        selection_note = "from git changes" if git_only else "after cleanup"
        print(f"No YAML files found for formatting {selection_note}.")
        exit_code = _issues_exit_code(issues, fail_on_warnings=fail_on_warnings)
        return exit_code, [], issues

    _handle_helper_normalisations(files, args.check, phase="pre")

    exit_code = 0
    for batch in chunk_paths(files, args.chunk_size):
        exit_code = max(exit_code, run_yamlfmt(args.yamlfmt, args.check, batch))

    _handle_helper_normalisations(files, args.check, phase="post")

    post_issues = collect_post_format_issues(files)
    issues.extend(post_issues)
    exit_code = max(
        exit_code,
        _issues_exit_code(post_issues, fail_on_warnings=fail_on_warnings),
    )

    schema_issues = validate_github_workflow_schemas(files)
    issues.extend(schema_issues)
    exit_code = max(
        exit_code,
        _issues_exit_code(schema_issues, fail_on_warnings=fail_on_warnings),
    )

    exit_code = max(
        exit_code, _issues_exit_code(issues, fail_on_warnings=fail_on_warnings)
    )

    if exit_code == 0 and update_cache_entries(cache_data, files):
        save_cache(cache_data)

    return exit_code, files, issues


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    search_paths, include_patterns, exclude_patterns = configure_runtime(args)
    yaml_files, git_only = discover_yaml_files(
        args, search_paths, include_patterns, exclude_patterns
    )
    exit_code, processed_files, issues = process_yaml_files(
        args,
        yaml_files,
        git_only,
        fail_on_warnings=args.fail_on_warnings,
    )
    _emit_validation_report(issues)
    write_summary(
        processed_files,
        issues,
        check_mode=args.check,
        summary_path=args.summary_path,
    )
    if processed_files:
        mode = "Checked" if args.check else "Formatted"
        print(f"{mode} {len(processed_files)} YAML file(s).")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
