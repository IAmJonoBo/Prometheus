from __future__ import annotations

import argparse

import pytest

from prometheus.packaging import OfflinePackagingConfig
from scripts import offline_package


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return offline_package.build_parser()


def test_auto_update_cli_overrides_enable_policy(parser: argparse.ArgumentParser) -> None:
    config = OfflinePackagingConfig()
    args = parser.parse_args(
        [
            "--auto-update",
            "--auto-update-max",
            "minor",
            "--auto-update-allow",
            "Foo",
            "--auto-update-allow",
            "foo",
            "--auto-update-deny",
            "Bar",
            "--auto-update-batch",
            "3",
        ]
    )

    offline_package._apply_auto_update_overrides(config, args)

    policy = config.updates.auto
    assert policy.enabled is True
    assert policy.max_update_type == "minor"
    assert policy.allow == ["Foo"]
    assert policy.deny == ["Bar"]
    assert policy.max_batch == 3


def test_auto_update_cli_overrides_respect_disable(parser: argparse.ArgumentParser) -> None:
    config = OfflinePackagingConfig()
    config.updates.auto.enabled = True
    args = parser.parse_args([
        "--no-auto-update",
        "--auto-update-max",
        "patch",
    ])

    offline_package._apply_auto_update_overrides(config, args)

    policy = config.updates.auto
    assert policy.enabled is False
    assert policy.max_update_type == "patch"


def test_auto_update_cli_overrides_reject_negative_batch(
    parser: argparse.ArgumentParser,
) -> None:
    config = OfflinePackagingConfig()
    args = parser.parse_args([
        "--auto-update",
        "--auto-update-batch",
        "-1",
    ])

    with pytest.raises(ValueError):
        offline_package._apply_auto_update_overrides(config, args)


def test_log_auto_update_policy_outputs_details(caplog) -> None:
    config = OfflinePackagingConfig()
    policy = config.updates.auto
    policy.enabled = True
    policy.allow = ["Foo"]
    policy.deny = ["Bar"]
    policy.max_update_type = "minor"
    policy.max_batch = 2

    with caplog.at_level("INFO"):
        offline_package._log_auto_update_policy(policy)

    message = " ".join(record.getMessage() for record in caplog.records)
    assert "Auto-update policy" in message
    assert "minor" in message
    assert "Foo" in message
    assert "Bar" in message
    assert "2" in message
