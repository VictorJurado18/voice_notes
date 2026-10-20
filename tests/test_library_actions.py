from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import send2trash

from record_transcript_resume.library_actions import (
    checked_delete_target, path_is_within, recycle_library_entry,
)


@pytest.mark.parametrize("is_folder", [False, True])
def test_only_the_selected_immediate_child_is_recycled(tmp_path: Path, monkeypatch, is_folder: bool) -> None:
    selected = tmp_path / "gravação de teste"
    if is_folder:
        selected.mkdir()
        (selected / "audio.mp3").write_bytes(b"synthetic audio")
    else:
        selected.write_bytes(b"synthetic audio")
    sibling = tmp_path / "outra gravação.mp3"
    sibling.write_bytes(b"keep")
    trash = Mock()
    monkeypatch.setattr(send2trash, "send2trash", trash)

    result = recycle_library_entry(tmp_path, selected, protected_roots=(tmp_path,))

    assert result == selected.resolve()
    trash.assert_called_once_with(str(selected.resolve()))
    assert sibling.read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["current", "ancestor", "outside", "nested", "missing"])
def test_invalid_targets_never_reach_the_recycle_bin(tmp_path: Path, monkeypatch, kind: str) -> None:
    directory = tmp_path / "library"
    directory.mkdir()
    folder = directory / "recording"
    folder.mkdir()
    nested = folder / "audio.mp3"
    nested.write_bytes(b"test")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"keep")
    selected = {
        "current": directory, "ancestor": tmp_path, "outside": outside,
        "nested": nested, "missing": directory / "missing.mp3",
    }[kind]
    trash = Mock()
    monkeypatch.setattr(send2trash, "send2trash", trash)

    with pytest.raises((OSError, ValueError)):
        recycle_library_entry(directory, selected)

    trash.assert_not_called()
    assert nested.is_file() and outside.read_bytes() == b"keep"


@pytest.mark.parametrize("protected_child", [False, True])
def test_library_and_recording_roots_cannot_be_deleted(tmp_path: Path, protected_child: bool) -> None:
    selected = tmp_path / "library"
    selected.mkdir()
    protected = selected / "recordings" if protected_child else selected
    protected.mkdir(exist_ok=True)

    with pytest.raises(ValueError, match="pasta principal"):
        checked_delete_target(tmp_path, selected, protected_roots=(protected,))


def test_similar_path_prefix_does_not_include_another_folder(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    archive = tmp_path / "library-old"
    archive.mkdir()

    assert not path_is_within(archive, library)
    assert checked_delete_target(tmp_path, archive, protected_roots=(library,)) == archive.resolve()


@pytest.mark.parametrize("attribute", ["is_symlink", "is_junction"])
def test_selected_links_are_rejected_without_following_them(tmp_path: Path, monkeypatch, attribute: str) -> None:
    selected = tmp_path / "link"
    selected.mkdir()
    monkeypatch.setattr(Path, attribute, lambda path: path == selected)

    with pytest.raises(ValueError, match="links ou junções"):
        checked_delete_target(tmp_path, selected)


def test_recycle_error_is_reported_without_permanent_deletion(tmp_path: Path, monkeypatch) -> None:
    selected = tmp_path / "audio.mp3"
    selected.write_bytes(b"keep")
    trash = Mock(side_effect=OSError("Recycle Bin unavailable"))
    monkeypatch.setattr(send2trash, "send2trash", trash)

    with pytest.raises(OSError, match="Recycle Bin unavailable"):
        recycle_library_entry(tmp_path, selected)

    trash.assert_called_once()
    assert selected.read_bytes() == b"keep"
