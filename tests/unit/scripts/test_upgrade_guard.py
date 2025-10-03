"""Tests for the upgrade guard aggregation script."""

from __future__ import annotations

import json
import os
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import dependency_drift, upgrade_guard


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_contract(path: Path, *, validated_age_days: int) -> Path:
    validated_at = datetime.now(UTC) - timedelta(days=validated_age_days)
    contract = textwrap.dedent(
        f"""
        [contract]
        status = "active"
        default_review_days = 14
        last_validated = "{validated_at.isoformat().replace('+00:00', 'Z')}"
        """
    ).strip()
    path.write_text(contract + "\n", encoding="utf-8")
    return path


def test_upgrade_guard_safe_exit_code(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight.json",
        {
            "packages": [
                {"name": "orjson", "version": "3.10.0", "status": "ok"},
                {"name": "numpy", "version": "1.26.4", "status": "ok"},
            ]
        },
    )

    exit_code = upgrade_guard.main(["--preflight", str(preflight_path)])

    assert exit_code == 1


@pytest.mark.parametrize(
    "status, expected_code",
    [
        ("warn", 1),
        ("error", 2),
    ],
)
def test_upgrade_guard_exit_codes(
    tmp_path: Path, status: str, expected_code: int
) -> None:
    preflight_path = _write_json(
        tmp_path / f"preflight-{status}.json",
        {
            "packages": [
                {
                    "name": "uvicorn",
                    "version": "0.29.0",
                    "status": status,
                    "missing_targets": ["macos-arm64"] if status == "warn" else [],
                }
            ]
        },
    )

    exit_code = upgrade_guard.main(["--preflight", str(preflight_path)])

    assert exit_code == expected_code


def test_upgrade_guard_outputs_assessment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight-blocked.json",
        {
            "packages": [
                {
                    "name": "pydantic",
                    "version": "2.7.0",
                    "status": "error",
                    "missing_targets": ["linux-x86_64"],
                }
            ]
        },
    )
    output_path = tmp_path / "assessment.json"
    markdown_path = tmp_path / "assessment.md"

    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--output",
            str(output_path),
            "--markdown",
            str(markdown_path),
            "--verbose",
        ]
    )

    assert exit_code == 2
    assert output_path.exists()
    assert markdown_path.exists()

    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    assert assessment["summary"]["highest_severity"] == upgrade_guard.RISK_BLOCKED
    assert assessment["summary"]["packages_flagged"] == 1

    stdout = capsys.readouterr().out
    assert "Upgrade Guard Assessment" in stdout
    assert "pydantic" in stdout


def test_upgrade_guard_contract_staleness_escalates_risk(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight-ok.json",
        {
            "packages": [
                {
                    "name": "httpx",
                    "version": "0.27.0",
                    "status": "ok",
                }
            ]
        },
    )
    contract_path = _write_contract(tmp_path / "contract.toml", validated_age_days=45)
    output_path = tmp_path / "assessment.json"

    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    assert assessment["summary"]["highest_severity"] == upgrade_guard.RISK_BLOCKED
    assert assessment["contract"]["risk"] == upgrade_guard.RISK_BLOCKED
    assert assessment["contract"]["status"] == "expired"


def test_upgrade_guard_missing_contract_is_needs_review(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight-ok.json",
        {
            "packages": [
                {
                    "name": "fastapi",
                    "version": "0.110.0",
                    "status": "ok",
                }
            ]
        },
    )
    missing_contract = tmp_path / "missing-contract.toml"
    output_path = tmp_path / "assessment.json"

    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(missing_contract),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    assert assessment["summary"]["highest_severity"] == upgrade_guard.RISK_NEEDS_REVIEW
    assert "contract" in assessment["summary"]["inputs_missing"]
    assert assessment["summary"]["notes"]
    assert assessment["contract"]["risk"] == upgrade_guard.RISK_NEEDS_REVIEW


def test_upgrade_guard_contract_metadata_includes_policies(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight-ok.json",
        {
            "packages": [
                {
                    "name": "fastapi",
                    "version": "0.110.0",
                    "status": "ok",
                }
            ]
        },
    )
    contract_path = tmp_path / "contract.toml"
    validated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    contract_path.write_text(
        textwrap.dedent(
            f"""
            [contract]
            status = "active"
            default_review_days = 14
            last_validated = "{validated_at}"

            [policies.signatures]
            required = true
            keyring = "sops/keyring.asc"
            enforced_artifacts = ["sdist", "wheel"]
            attestation_required = ["sbom", "provenance"]
            grace_period_days = 5
            trusted_publishers = ["prometheus-ai"]
            allow_unsigned_profiles = ["sandbox"]

            [[governance.snoozes]]
            id = "SNOOZE-123"
            reason = "Awaiting upstream fix"
            expires_at = "2024-12-31T00:00:00Z"
            requested_by = "alice"
            approver = "bob"
            [governance.snoozes.scope]
            package = "example"
            environment = "prod"

            [environment_alignment]
            alert_channel = "slack://#supply-chain"
            default_sync_window_days = 10

            [[environment_alignment.environments]]
            name = "prod"
            profiles = ["prod"]
            lockfiles = ["poetry.lock"]
            model_registry = "mlflow://prod"
            last_synced = "2024-05-01T12:00:00Z"
            sync_window_days = 7
            requires_signatures = true

            [[environment_alignment.environments]]
            name = "stage"
            profiles = ["stage"]
            requires_signatures = false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "assessment.json"

    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    contract = assessment["contract"]

    signature_policy = contract.get("signature_policy")
    assert signature_policy
    assert signature_policy["required"] is True
    assert signature_policy["keyring"] == "sops/keyring.asc"
    assert signature_policy["enforced_artifacts"] == ["sdist", "wheel"]
    assert signature_policy["attestation_required"] == ["sbom", "provenance"]
    assert signature_policy["grace_period_days"] == 5
    assert signature_policy["trusted_publishers"] == ["prometheus-ai"]
    assert signature_policy["allow_unsigned_profiles"] == ["sandbox"]

    snoozes = contract.get("snoozes")
    assert snoozes and len(snoozes) == 1
    snooze = snoozes[0]
    assert snooze["id"] == "SNOOZE-123"
    assert snooze["reason"] == "Awaiting upstream fix"
    assert snooze["expires_at"] == "2024-12-31T00:00:00Z"
    assert snooze["requested_by"] == "alice"
    assert snooze["approver"] == "bob"
    assert snooze["scope"] == {"package": "example", "environment": "prod"}

    alignment = contract.get("environment_alignment")
    assert alignment
    assert alignment["alert_channel"] == "slack://#supply-chain"
    assert alignment["default_sync_window_days"] == 10
    assert len(alignment["environments"]) == 2
    assert alignment["environments"][0]["name"] == "prod"
    assert alignment["environments"][0]["profiles"] == ["prod"]
    assert alignment["environments"][0]["lockfiles"] == ["poetry.lock"]
    assert alignment["environments"][0]["requires_signatures"] is True
    assert alignment["environments"][1]["name"] == "stage"
    assert alignment["environments"][1]["requires_signatures"] is False
    compliance = contract["signature_compliance"]
    assert compliance["status"] == "unknown"
    snooze_status = contract["snooze_status"]
    assert snooze_status["risk"] == upgrade_guard.RISK_BLOCKED


def test_signature_policy_requires_mirror_context(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight.json",
        {
            "packages": [
                {
                    "name": "uvicorn",
                    "version": "0.30.0",
                    "status": "ok",
                }
            ]
        },
    )

    validated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    contract_path = tmp_path / "contract.toml"
    contract_path.write_text(
        textwrap.dedent(
            f"""
            [contract]
            status = "active"
            default_review_days = 14
            last_validated = "{validated_at}"

            [policies.signatures]
            required = true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "assessment.json"
    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    contract = assessment["contract"]
    compliance = contract["signature_compliance"]
    assert compliance["status"] == "unknown"
    assert compliance["risk"] == upgrade_guard.RISK_NEEDS_REVIEW
    assert compliance["issues"]
    assert contract["risk"] == upgrade_guard.RISK_NEEDS_REVIEW


def test_signature_policy_missing_signature_blocks(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight.json",
        {
            "packages": [
                {
                    "name": "uvicorn",
                    "version": "0.30.0",
                    "status": "ok",
                }
            ]
        },
    )

    validated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    contract_path = tmp_path / "contract.toml"
    contract_path.write_text(
        textwrap.dedent(
            f"""
            [contract]
            status = "active"
            default_review_days = 14
            last_validated = "{validated_at}"

            [policies.signatures]
            required = true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    mirror_root = tmp_path / "mirror"
    mirror_root.mkdir()
    wheel_path = mirror_root / "example-1.0.0-py3-none-any.whl"
    wheel_path.write_bytes(b"wheel")

    output_path = tmp_path / "assessment.json"
    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(contract_path),
            "--mirror-root",
            str(mirror_root),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    contract = assessment["contract"]
    compliance = contract["signature_compliance"]
    assert compliance["status"] == "failed"
    assert compliance["risk"] == upgrade_guard.RISK_BLOCKED
    assert any("signature" in issue for issue in compliance["issues"])
    assert contract["risk"] == upgrade_guard.RISK_BLOCKED


def _write_index_file(index_dir: Path, run_id: str, payload: dict[str, object]) -> Path:
    path = index_dir / f"{run_id}.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_prune_snapshot_index_refreshes_latest(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    index_dir = root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    run_a = "20240101T000000Z"
    run_b = "20240201T000000Z"
    _write_index_file(index_dir, run_a, {"run_id": run_a, "highest_severity": "ok"})
    _write_index_file(
        index_dir, run_b, {"run_id": run_b, "highest_severity": "critical"}
    )
    latest_path = index_dir / "latest.json"
    latest_path.write_text(json.dumps({"run_id": run_a}), encoding="utf-8")

    upgrade_guard._prune_snapshot_index(root, [run_a])

    assert not (index_dir / f"{run_a}.json").exists()
    latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest_payload["run_id"] == run_b


def test_prune_snapshot_index_clears_latest_when_empty(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    index_dir = root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    run_a = "20240101T000000Z"
    _write_index_file(index_dir, run_a, {"run_id": run_a})
    latest_path = index_dir / "latest.json"
    latest_path.write_text(json.dumps({"run_id": run_a}), encoding="utf-8")

    upgrade_guard._prune_snapshot_index(root, [run_a])

    assert not (index_dir / f"{run_a}.json").exists()
    assert not latest_path.exists()


def test_snooze_expiry_escalates_contract_risk(tmp_path: Path) -> None:
    preflight_path = _write_json(
        tmp_path / "preflight.json",
        {
            "packages": [
                {
                    "name": "uvicorn",
                    "version": "0.30.0",
                    "status": "ok",
                }
            ]
        },
    )

    validated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    expired_at = (
        (datetime.now(UTC) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    )
    contract_path = tmp_path / "contract.toml"
    contract_path.write_text(
        textwrap.dedent(
            f"""
            [contract]
            status = "active"
            default_review_days = 14
            last_validated = "{validated_at}"

            [[governance.snoozes]]
            id = "SNOOZE-999"
            reason = "Awaiting upstream fix"
            expires_at = "{expired_at}"
            requested_by = "alice"
            approver = "bob"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "assessment.json"
    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    contract = assessment["contract"]
    snooze_status = contract["snooze_status"]
    assert snooze_status["risk"] == upgrade_guard.RISK_BLOCKED
    assert snooze_status["entries"][0]["status"] == "expired"
    assert contract["risk"] == upgrade_guard.RISK_BLOCKED


def test_upgrade_guard_drift_escalates_highest_severity(tmp_path: Path) -> None:
    sbom_path = _write_json(
        tmp_path / "sbom.json",
        {
            "components": [
                {
                    "name": "example",
                    "version": "1.0.0",
                }
            ]
        },
    )
    metadata_path = _write_json(
        tmp_path / "metadata.json",
        {
            "packages": {
                "example": {
                    "latest": "2.0.0",
                }
            }
        },
    )
    contract_path = _write_contract(tmp_path / "contract.toml", validated_age_days=0)
    output_path = tmp_path / "assessment.json"

    exit_code = upgrade_guard.main(
        [
            "--sbom",
            str(sbom_path),
            "--metadata",
            str(metadata_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    assert assessment["summary"]["highest_severity"] == upgrade_guard.RISK_BLOCKED
    assert assessment["drift"]["severity"] == dependency_drift.RISK_MAJOR
    assert assessment["drift"]["packages"][0]["name"] == "example"
    assert assessment["drift"]["packages"][0]["severity"] == dependency_drift.RISK_MAJOR
    assert assessment["drift"]["metadata_path"] == str(metadata_path)
    assert assessment["evidence"]["drift"] == str(sbom_path)
    assert assessment["evidence"]["drift_metadata"] == str(metadata_path)
    assert assessment["drift"]["sbom_stale"] is False
    assert assessment["drift"]["sbom_age_days"] is not None


def test_upgrade_guard_flags_stale_sbom(tmp_path: Path) -> None:
    sbom_path = _write_json(
        tmp_path / "sbom.json",
        {
            "components": [
                {
                    "name": "stable",
                    "version": "1.0.0",
                }
            ]
        },
    )
    metadata_path = _write_json(
        tmp_path / "metadata.json",
        {
            "packages": {
                "stable": {
                    "latest": "1.0.0",
                }
            }
        },
    )
    contract_path = _write_contract(tmp_path / "contract.toml", validated_age_days=0)
    output_path = tmp_path / "assessment.json"

    stale_days = 3
    stale_timestamp = (datetime.now(UTC) - timedelta(days=stale_days)).timestamp()
    os.utime(sbom_path, (stale_timestamp, stale_timestamp))

    exit_code = upgrade_guard.main(
        [
            "--sbom",
            str(sbom_path),
            "--metadata",
            str(metadata_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
            "--sbom-max-age-days",
            "1",
        ]
    )

    assert exit_code == 1
    assessment = json.loads(output_path.read_text(encoding="utf-8"))
    assert assessment["summary"]["highest_severity"] == upgrade_guard.RISK_NEEDS_REVIEW
    assert assessment["drift"]["severity"] == dependency_drift.RISK_SAFE
    assert assessment["drift"]["sbom_stale"] is True
    assert assessment["drift"]["sbom_age_days"] >= stale_days
    assert any("exceeds cadence" in note for note in assessment["drift"]["notes"])


def test_upgrade_guard_writes_snapshot_bundle(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshots"
    legacy_dir = snapshot_root / "20240101T000000Z"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "old.txt").write_text("legacy", encoding="utf-8")

    preflight_path = _write_json(
        tmp_path / "preflight.json",
        {
            "packages": [
                {"name": "orjson", "version": "3.10.0", "status": "ok"},
            ]
        },
    )

    exit_code = upgrade_guard.main(
        [
            "--preflight",
            str(preflight_path),
            "--snapshot-root",
            str(snapshot_root),
            "--snapshot-retention-days",
            "0",
        ]
    )

    assert exit_code == 1
    run_dirs = [
        path
        for path in snapshot_root.iterdir()
        if path.is_dir() and path.name != "index"
    ]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    copied_preflight = manifest["inputs"][upgrade_guard.SOURCE_PREFLIGHT]
    assert copied_preflight is not None
    assert Path(copied_preflight).exists()

    assessment_path = manifest["reports"]["assessment"]
    assert Path(assessment_path).exists()
    assessment = json.loads(Path(assessment_path).read_text(encoding="utf-8"))
    assert assessment["summary"]["packages_flagged"] == 0

    assert not legacy_dir.exists()
    assert manifest["retention_days"] == 0
    assert legacy_dir.name in manifest["pruned_snapshots"]
