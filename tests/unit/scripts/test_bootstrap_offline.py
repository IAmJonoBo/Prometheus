import tarfile
from pathlib import Path

import pytest

from scripts import bootstrap_offline


def _create_archive(source_root: Path, subdir: str) -> Path:
    archive = source_root.parent / f"{subdir}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_root / subdir, arcname=subdir)
    return archive


def test_directory_missing_or_empty(tmp_path):
    missing = tmp_path / "missing"
    assert bootstrap_offline._directory_missing_or_empty(missing) is True

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert bootstrap_offline._directory_missing_or_empty(empty_dir) is True

    (empty_dir / "data.txt").write_text("hello")
    assert bootstrap_offline._directory_missing_or_empty(empty_dir) is False

    file_path = tmp_path / "file.txt"
    file_path.write_text("content")
    with pytest.raises(RuntimeError):
        bootstrap_offline._directory_missing_or_empty(file_path)


def test_download_and_extract_replaces_existing_directory(tmp_path):
    source_root = tmp_path / "source"
    wheelhouse_dir = source_root / "wheelhouse"
    wheelhouse_dir.mkdir(parents=True)
    (wheelhouse_dir / "original.txt").write_text("hello")

    archive = _create_archive(source_root, "wheelhouse")

    destination = tmp_path / "dest"
    existing = destination / "wheelhouse"
    existing.mkdir(parents=True)
    (existing / "stale.txt").write_text("stale")

    bootstrap_offline._download_and_extract(
        archive.as_uri(),
        token=None,
        extract_root=destination,
        expected_subdir="wheelhouse",
    )

    extracted_file = destination / "wheelhouse" / "original.txt"
    assert extracted_file.exists()
    assert extracted_file.read_text() == "hello"
    assert not (destination / "wheelhouse" / "stale.txt").exists()

    # Subsequent download updates contents
    (wheelhouse_dir / "original.txt").write_text("updated")
    archive = _create_archive(source_root, "wheelhouse")

    bootstrap_offline._download_and_extract(
        archive.as_uri(),
        token=None,
        extract_root=destination,
        expected_subdir="wheelhouse",
    )

    assert extracted_file.read_text() == "updated"
