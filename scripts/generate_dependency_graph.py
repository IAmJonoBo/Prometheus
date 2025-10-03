#!/usr/bin/env python3
"""Generate dependency graph visualization for Prometheus architecture.

This script analyzes Python imports across the codebase and generates
a dependency graph showing relationships between modules.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_imports(file_path: Path, repo_root: Path) -> list[str]:
    """Extract import statements from a Python file.
    
    Only considers absolute imports, not relative imports within the same module.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    # Determine the module this file belongs to
    try:
        relative = file_path.relative_to(repo_root)
        current_module = str(relative.parts[0])
    except (ValueError, IndexError):
        current_module = None

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports (e.g., from .base import ...)
            if node.level > 0:
                continue
            if node.module:
                module_root = node.module.split(".")[0]
                # Skip imports from the same module (e.g., common.contracts importing from common.events)
                if module_root != current_module:
                    imports.append(module_root)
    return list(set(imports))


def analyze_dependencies(
    repo_root: Path, exclude_patterns: list[str] | None = None
) -> dict[str, dict[str, Any]]:
    """Analyze dependencies across all Python files in the repository."""
    if exclude_patterns is None:
        exclude_patterns = ["vendor", ".venv", "tmpreposim2", "__pycache__", ".git"]

    modules = [
        "ingestion",
        "retrieval",
        "reasoning",
        "decision",
        "execution",
        "monitoring",
        "common",
        "model",
        "security",
        "governance",
        "observability",
        "api",
        "prometheus",
        "scripts",
        "sdk",
    ]

    graph: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"internal_deps": set(), "external_deps": set(), "files": []}
    )

    for py_file in repo_root.rglob("*.py"):
        # Skip excluded patterns
        if any(pattern in str(py_file) for pattern in exclude_patterns):
            continue

        # Determine which module this file belongs to
        try:
            relative = py_file.relative_to(repo_root)
            module_name = str(relative.parts[0])
        except (ValueError, IndexError):
            continue

        if module_name not in modules:
            continue

        imports = parse_imports(py_file, repo_root)
        graph[module_name]["files"].append(str(relative))

        for imp in imports:
            if imp in modules and imp != module_name:
                graph[module_name]["internal_deps"].add(imp)
            elif imp not in modules:
                graph[module_name]["external_deps"].add(imp)

    # Convert sets to lists for JSON serialization
    result = {}
    for module, data in graph.items():
        result[module] = {
            "internal_deps": sorted(data["internal_deps"]),
            "external_deps": sorted(data["external_deps"]),
            "file_count": len(data["files"]),
        }

    return result


def generate_mermaid(graph: dict[str, dict[str, Any]]) -> str:
    """Generate a Mermaid diagram from the dependency graph."""
    lines = ["```mermaid", "graph TD"]

    # Define core pipeline stages with special styling
    pipeline_stages = [
        "ingestion",
        "retrieval",
        "reasoning",
        "decision",
        "execution",
        "monitoring",
    ]

    # Add nodes
    for module in sorted(graph.keys()):
        if module in pipeline_stages:
            lines.append(f"    {module}[{module.title()}]:::pipeline")
        else:
            lines.append(f"    {module}[{module.title()}]")

    lines.append("")

    # Add edges for internal dependencies
    for module, data in sorted(graph.items()):
        for dep in sorted(data["internal_deps"]):
            lines.append(f"    {module} --> {dep}")

    lines.append("")
    lines.append("    classDef pipeline fill:#e1f5ff,stroke:#01579b,stroke-width:2px")
    lines.append("```")

    return "\n".join(lines)


def detect_cycles(graph: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Detect circular dependencies in the module graph."""
    cycles = []

    def visit(
        node: str, path: list[str], visited: set[str], rec_stack: set[str]
    ) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for dep in graph.get(node, {}).get("internal_deps", []):
            if dep not in visited:
                visit(dep, path.copy(), visited, rec_stack)
            elif dep in rec_stack:
                # Found a cycle
                cycle_start = path.index(dep)
                cycles.append(path[cycle_start:] + [dep])

        rec_stack.remove(node)

    visited_set: set[str] = set()
    for module in graph:
        if module not in visited_set:
            visit(module, [], visited_set, set())

    return cycles


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate dependency graph for Prometheus"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: docs/dependency-graph.md)",
    )
    parser.add_argument(
        "--format",
        choices=["mermaid", "json"],
        default="mermaid",
        help="Output format",
    )
    parser.add_argument(
        "--check-cycles",
        action="store_true",
        help="Check for circular dependencies and exit with error if found",
    )

    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_path = args.output or repo_root / "docs" / "dependency-graph.md"

    print(f"Analyzing dependencies in {repo_root}...", file=sys.stderr)
    graph = analyze_dependencies(repo_root)

    if args.check_cycles:
        cycles = detect_cycles(graph)
        if cycles:
            print(f"ERROR: Found {len(cycles)} circular dependencies:", file=sys.stderr)
            for cycle in cycles:
                print(f"  {' -> '.join(cycle)}", file=sys.stderr)
            return 1
        print("✓ No circular dependencies detected", file=sys.stderr)

    if args.format == "json":
        content = json.dumps(graph, indent=2)
    else:
        # Generate Mermaid markdown document
        lines = [
            "# Prometheus Dependency Graph",
            "",
            "This diagram shows the internal dependencies between Prometheus modules.",
            "Generated automatically by `scripts/generate_dependency_graph.py`.",
            "",
            "## Module Dependencies",
            "",
            generate_mermaid(graph),
            "",
            "## Module Details",
            "",
        ]

        for module in sorted(graph.keys()):
            data = graph[module]
            lines.append(f"### {module.title()}")
            lines.append(f"- Files: {data['file_count']}")
            if data["internal_deps"]:
                lines.append(
                    f"- Internal dependencies: {', '.join(data['internal_deps'])}"
                )
            if data["external_deps"]:
                ext_deps = data["external_deps"][:10]  # Limit to first 10
                if len(data["external_deps"]) > 10:
                    ext_deps.append("...")
                lines.append(f"- External dependencies: {', '.join(ext_deps)}")
            lines.append("")

        content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"✓ Dependency graph written to {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
