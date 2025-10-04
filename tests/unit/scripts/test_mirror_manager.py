import hashlib
import json
import os
from pathlib import Path

import pytest

from chiron.deps.mirror_manager import (
    _should_copy,
    _validate_signature,
    discover_mirror,
    render_status,
    update_mirror,
)


@pytest.fixture()
def sample_files(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source" / "package.whl"
    target = tmp_path / "mirror" / "package.whl"
    source.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"new-bytes")
    return source, target


def test_should_copy_when_target_missing(sample_files: tuple[Path, Path]) -> None:
    source, target = sample_files
    assert not target.exists()
    assert _should_copy(source, target, manifest_entry=None)


def test_should_copy_when_manifest_hash_mismatch(
    sample_files: tuple[Path, Path],
) -> None:
    source, target = sample_files
    target.write_bytes(b"old-bytes")
    manifest_entry = {"sha256": "0" * 64}
    assert _should_copy(source, target, manifest_entry)


def test_should_not_copy_when_manifest_hash_matches(
    sample_files: tuple[Path, Path],
) -> None:
    source, target = sample_files
    target.write_bytes(b"old-bytes")
    expected = hashlib.sha256(b"old-bytes").hexdigest()
    manifest_entry = {"sha256": expected}
    assert not _should_copy(source, target, manifest_entry)


def test_should_copy_when_source_newer_without_manifest(
    sample_files: tuple[Path, Path],
) -> None:
    source, target = sample_files
    target.write_bytes(b"old-bytes")
    os.utime(target, (1, 1))
    os.utime(source, (2, 2))
    assert _should_copy(source, target, manifest_entry=None)


def test_should_not_copy_when_target_newer_without_manifest(
    sample_files: tuple[Path, Path],
) -> None:
    source, target = sample_files
    target.write_bytes(b"old-bytes")
    os.utime(source, (1, 1))
    os.utime(target, (2, 2))
    assert not _should_copy(source, target, manifest_entry=None)


def test_validate_signature_verifies_sha256(sample_files: tuple[Path, Path]) -> None:
    source, _ = sample_files
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    signature_path = source.with_name(source.name + ".sha256")
    signature_path.write_text(f"{digest}  {source.name}\n", encoding="utf-8")

    result = _validate_signature(source, require_signature=True)

    assert result.status == "verified"
    assert result.signature_path == signature_path
    assert result.reason is None


def test_validate_signature_missing_required(sample_files: tuple[Path, Path]) -> None:
    source, _ = sample_files
    result = _validate_signature(source, require_signature=True)

    assert result.status == "missing"
    assert "required" in (result.reason or "")


def test_validate_signature_detects_sha256_mismatch(
    sample_files: tuple[Path, Path],
) -> None:
    source, _ = sample_files
    signature_path = source.with_name(source.name + ".sha256")
    signature_path.write_text("deadbeef  package.whl\n", encoding="utf-8")

    result = _validate_signature(source, require_signature=True)

    assert result.status == "failed"
    assert result.signature_path == signature_path
    assert "mismatch" in (result.reason or "")


@pytest.mark.parametrize("suffix", [".sig", ".asc"])
def test_validate_signature_accepts_non_sha_signature(
    sample_files: tuple[Path, Path], suffix: str
) -> None:
    source, _ = sample_files
    signature_path = source.with_name(source.name + suffix)
    signature_path.write_text("signature", encoding="utf-8")

    result = _validate_signature(source, require_signature=True)

    assert result.status == "verified"
    assert result.signature_path == signature_path


def test_update_mirror_copies_signatures_and_prunes(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    mirror_root = tmp_path / "mirror"
    source_root.mkdir(parents=True, exist_ok=True)
    mirror_root.mkdir(parents=True, exist_ok=True)

    wheel_path = source_root / "foo-1.0.whl"
    wheel_bytes = b"foo-content"
    wheel_path.write_bytes(wheel_bytes)

    tar_dir = source_root / "nested"
    tar_dir.mkdir(parents=True, exist_ok=True)
    tar_path = tar_dir / "bar-2.0.tar.gz"
    tar_path.write_bytes(b"bar")
    tar_sig = tar_path.with_name(tar_path.name + ".sig")
    tar_sig.write_text("signed", encoding="utf-8")

    manifest_data = {
        "foo-1.0.whl": {"sha256": hashlib.sha256(wheel_bytes).hexdigest()},
        "nested/bar-2.0.tar.gz": {},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Present a stale artifact that should be pruned.
    stale_dir = mirror_root / "stale"
    stale_dir.mkdir(parents=True, exist_ok=True)
    stale_path = stale_dir / "baz.whl"
    stale_path.write_bytes(b"old")

    result = update_mirror(
        source=source_root,
        mirror_root=mirror_root,
        manifest=manifest_path,
        prune=True,
    )

    assert result.mirror_root == mirror_root
    assert sorted(result.copied) == ["foo-1.0.whl", "nested/bar-2.0.tar.gz"]
    assert result.skipped == []
    assert result.pruned == ["stale/baz.whl"]

    copied_wheel = mirror_root / "foo-1.0.whl"
    assert copied_wheel.exists()
    generated_sha = copied_wheel.with_name("foo-1.0.whl.sha256")
    assert generated_sha.exists()
    assert hashlib.sha256(wheel_bytes).hexdigest() in generated_sha.read_text(
        encoding="utf-8"
    )

    copied_tar = mirror_root / "nested" / "bar-2.0.tar.gz"
    assert copied_tar.exists()
    copied_signature = copied_tar.with_name("bar-2.0.tar.gz.sig")
    assert copied_signature.exists()
    assert copied_signature.read_text(encoding="utf-8") == "signed"

    assert not stale_path.exists()
    assert not stale_path.with_name(stale_path.name + ".sig").exists()


def test_update_mirror_preserves_extra_when_prune_disabled(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    mirror_root = tmp_path / "mirror"
    source_root.mkdir(parents=True, exist_ok=True)
    mirror_root.mkdir(parents=True, exist_ok=True)

    wheel_path = source_root / "foo-1.0.whl"
    wheel_path.write_bytes(b"foo")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}), encoding="utf-8")

    extra_path = mirror_root / "extra" / "keep.whl"
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_bytes(b"extra")

    result = update_mirror(
        source=source_root,
        mirror_root=mirror_root,
        manifest=manifest_path,
        prune=False,
    )

    assert "foo-1.0.whl" in result.copied
    assert result.pruned == []
    assert extra_path.exists()


def test_update_mirror_refreshes_stale_signature(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    mirror_root = tmp_path / "mirror"
    source_root.mkdir(parents=True, exist_ok=True)
    mirror_root.mkdir(parents=True, exist_ok=True)

    wheel_path = source_root / "foo-1.0.whl"
    source_bytes = b"fresh"
    wheel_path.write_bytes(source_bytes)
    source_signature = wheel_path.with_name("foo-1.0.whl.sha256")
    source_signature.write_text(
        f"{hashlib.sha256(source_bytes).hexdigest()}  {wheel_path.name}\n",
        encoding="utf-8",
    )

    existing_target = mirror_root / "foo-1.0.whl"
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_bytes(b"stale")
    stale_signature = existing_target.with_name("foo-1.0.whl.sha256")
    stale_signature.write_text("0000  foo-1.0.whl\n", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {"foo-1.0.whl": {"sha256": hashlib.sha256(source_bytes).hexdigest()}}
        ),
        encoding="utf-8",
    )

    result = update_mirror(
        source=source_root,
        mirror_root=mirror_root,
        manifest=manifest_path,
        prune=False,
    )

    assert "foo-1.0.whl" in result.copied
    updated_content = existing_target.read_bytes()
    assert updated_content == source_bytes
    updated_signature = existing_target.with_name("foo-1.0.whl.sha256")
    assert hashlib.sha256(source_bytes).hexdigest() in updated_signature.read_text(
        encoding="utf-8"
    )


def test_discover_mirror_requires_signed_artifacts(tmp_path: Path) -> None:
    mirror_root = tmp_path / "mirror"
    artifact = mirror_root / "unsigned-1.0.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"payload")

    status = discover_mirror(mirror_root, require_signature=True)

    assert not status.verified
    assert status.artifacts
    signature = status.artifacts[0].signature
    assert signature.status == "missing"
    assert "required" in (signature.reason or "")
    summary = status.to_dict()["summary"]
    assert summary["missing"] == 1
    rendered = render_status(status)
    assert "missing" in rendered
    assert "required" in rendered


def test_discover_mirror_validates_sha256_signature(tmp_path: Path) -> None:
    mirror_root = tmp_path / "mirror"
    artifact = mirror_root / "signed-1.0.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    data = b"content"
    artifact.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    signature_path = artifact.with_name("signed-1.0.whl.sha256")
    signature_path.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    status = discover_mirror(mirror_root, require_signature=True)

    assert status.verified
    assert status.artifacts[0].signature.status == "verified"
    summary = status.to_dict()["summary"]
    assert summary["verified"] == 1


def test_discover_mirror_detects_signature_mismatch(tmp_path: Path) -> None:
    mirror_root = tmp_path / "mirror"
    artifact = mirror_root / "signed-1.0.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"content")
    signature_path = artifact.with_name("signed-1.0.whl.sha256")
    signature_path.write_text("deadbeef  signed-1.0.whl\n", encoding="utf-8")

    status = discover_mirror(mirror_root, require_signature=True)

    assert not status.verified
    signature = status.artifacts[0].signature
    assert signature.status == "failed"
    assert "mismatch" in (signature.reason or "")
    summary = status.to_dict()["summary"]
    assert summary["failed"] == 1
