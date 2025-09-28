"""Tests for the shared packaging metadata helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from prometheus.packaging.metadata import (
    WheelhouseManifest,
    load_wheelhouse_manifest,
    write_wheelhouse_manifest,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            {
                "generated_at": "2024-04-01T12:00:00Z",
                "extras": ["dev", "docs", ""],
                "include_dev": True,
                "create_archive": True,
                "commit": "abc123",
            },
            WheelhouseManifest(
                generated_at="2024-04-01T12:00:00Z",
                extras=("dev", "docs"),
                include_dev=True,
                create_archive=True,
                commit="abc123",
            ),
        ),
        (
            {
                "extras": ["api"],
            },
            WheelhouseManifest(
                generated_at=None,
                extras=("api",),
                include_dev=False,
                create_archive=False,
                commit=None,
            ),
        ),
    ],
)
def test_wheelhouse_manifest_from_mapping(raw: dict[str, object], expected: WheelhouseManifest) -> None:
    assert WheelhouseManifest.from_mapping(raw) == expected


def test_wheelhouse_manifest_round_trip(tmp_path: Path) -> None:
    manifest = WheelhouseManifest(
        generated_at="2024-04-01T12:00:00Z",
        extras=("dev", "docs"),
        include_dev=True,
        create_archive=True,
        commit="abc123",
    )
    path = tmp_path / "manifest.json"

    write_wheelhouse_manifest(path, manifest)
    loaded = load_wheelhouse_manifest(path)

    assert loaded == manifest