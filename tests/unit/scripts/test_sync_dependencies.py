"""Tests for dependency contract manifest generation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNC_DEP_PATH = REPO_ROOT / "scripts" / "sync-dependencies.py"
_SPEC = importlib.util.spec_from_file_location(
    "sync_dependencies_module", SYNC_DEP_PATH
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive
    raise RuntimeError(f"Unable to import sync-dependencies.py from {SYNC_DEP_PATH}")
_sync_dependencies = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("sync_dependencies_module", _sync_dependencies)
_SPEC.loader.exec_module(_sync_dependencies)


def test_package_requirement_appends_marker() -> None:
    record = _sync_dependencies.PackageRecord(
        name="llama-cpp-python",
        profile="optional_llm",
        constraint=">=0.3.0,<0.4.0",
        locked="0.3.1",
        marker="python_version < '3.12'",
    )

    assert record.requirement() == "llama-cpp-python==0.3.1; python_version < '3.12'"
    assert (
        record.requirement(prefer_locked=False)
        == "llama-cpp-python>=0.3.0,<0.4.0; python_version < '3.12'"
    )


def test_contract_manifests_include_markers(tmp_path: Path) -> None:
    contract_data = {
        "profiles": {
            "runtime": {
                "packages": [
                    {
                        "name": "requests",
                        "locked": "2.32.5",
                        "constraint": ">=2.32.0,<3.0.0",
                    }
                ]
            },
            "optional_llm": {
                "condition": "extra:llm",
                "packages": [
                    {
                        "name": "llama-cpp-python",
                        "constraint": ">=0.3.0,<0.4.0",
                        "locked": "0.3.1",
                        "marker": "python_version < '3.12'",
                    }
                ],
            },
        }
    }
    contract = _sync_dependencies.DependencyContract(
        contract_data, tmp_path / "contract.toml"
    )
    bundle = contract.to_manifests()

    assert (
        "llama-cpp-python==0.3.1; python_version < '3.12'" in bundle.constraints_lines
    )
    assert "llama-cpp-python==0.3.1; python_version < '3.12'" in bundle.wheelhouse_lines
    optional_llm = bundle.pyproject.optional.get("llm")
    assert optional_llm is not None
    assert "llama-cpp-python>=0.3.0,<0.4.0; python_version < '3.12'" in optional_llm


def test_cyclonedx_sbom_includes_package_metadata(tmp_path: Path) -> None:
    contract_data = {
        "profiles": {
            "runtime": {
                "packages": [
                    {
                        "name": "requests",
                        "locked": "2.32.5",
                        "constraint": "~=2.32",
                        "notes": "core http client",
                    }
                ]
            }
        }
    }
    contract = _sync_dependencies.DependencyContract(
        contract_data, tmp_path / "contract.toml"
    )
    sbom_raw = _sync_dependencies._render_cyclonedx_sbom(contract)
    payload = json.loads(sbom_raw)

    assert payload["bomFormat"] == "CycloneDX"
    assert payload["metadata"]["component"]["properties"][0]["value"].endswith(
        "contract.toml"
    )
    component = payload["components"][0]
    assert component["name"] == "requests"
    assert component["version"] == "2.32.5"
    assert any(prop["name"] == "constraint" for prop in component["properties"])
