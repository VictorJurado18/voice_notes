from __future__ import annotations

import json

import pytest

from record_transcript_resume import release_notes
from record_transcript_resume.release_notes import ReleaseNoticeStore, _version


def test_first_install_establishes_baseline_without_a_popup(tmp_path, monkeypatch):
    monkeypatch.setattr(release_notes, "_install_history", lambda: ("", ""))
    store = ReleaseNoticeStore(tmp_path / "notice.json")
    assert not store.prepare("0.10.28").pending
    assert store.has_seen("0.10.28")
    assert not store.prepare("0.10.28").pending


def test_upgrade_is_pending_until_really_shown_even_after_restarting(tmp_path):
    path = tmp_path / "notice.json"
    store = ReleaseNoticeStore(path, development=True)
    store.prepare("0.10.27")
    notice = store.prepare("0.10.28")
    assert notice.pending and notice.previous_version == "0.10.27"
    assert ReleaseNoticeStore(path, development=True).prepare("0.10.28").pending
    store.mark_seen("0.10.28")
    assert not ReleaseNoticeStore(path, development=True).prepare("0.10.28").pending
    assert store.prepare("0.10.29").pending


def test_first_upgrade_from_legacy_version_uses_installer_history(tmp_path, monkeypatch):
    monkeypatch.setattr(release_notes, "_install_history", lambda: ("0.10.28", "0.10.27"))
    store = ReleaseNoticeStore(tmp_path / "notice.json")
    assert store.prepare("0.10.28").pending
    store.mark_seen("0.10.28")
    assert not store.prepare("0.10.28").pending


def test_downgrade_and_reinstall_do_not_repeat_an_already_seen_version(tmp_path):
    store = ReleaseNoticeStore(tmp_path / "notice.json", development=True)
    store.prepare("0.10.27")
    store.prepare("0.10.28")
    store.mark_seen("0.10.28")
    assert not store.prepare("0.10.26").pending
    assert not store.prepare("0.10.28").pending
    assert store.prepare("0.11.0").pending


def test_development_does_not_consume_the_installed_apps_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(release_notes, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(release_notes, "_install_history", lambda: ("0.10.28", "0.10.27"))
    dev = ReleaseNoticeStore(development=True)
    installed = ReleaseNoticeStore()
    assert dev.path != installed.path
    assert not dev.prepare("0.10.28").pending
    assert installed.prepare("0.10.28").pending


@pytest.mark.parametrize("contents", ["broken json", "[]", '{"last_launched_version": []}'])
def test_invalid_notice_state_recovers_using_install_history(tmp_path, monkeypatch, contents):
    monkeypatch.setattr(release_notes, "_install_history", lambda: ("0.10.28", "0.10.27"))
    path = tmp_path / "notice.json"
    path.write_text(contents, encoding="utf-8")
    assert ReleaseNoticeStore(path).prepare("0.10.28").pending
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize("value", [None, [], "", "garbage", "1.2.beta"])
def test_invalid_versions_do_not_trigger_notices(tmp_path, value):
    assert _version(value) is None
    assert not ReleaseNoticeStore(tmp_path / "notice.json").prepare(value).pending


def test_unknown_version_does_not_write_state(tmp_path):
    path = tmp_path / "notice.json"
    assert not ReleaseNoticeStore(path).prepare("0.0.0").pending
    assert not path.exists()


def test_newer_installer_history_is_not_applied_to_an_older_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(release_notes, "_install_history", lambda: ("0.10.29", "0.10.27"))
    assert not ReleaseNoticeStore(tmp_path / "notice.json").prepare("0.10.28").pending
