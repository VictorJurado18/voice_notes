from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.release_notes import ReleaseNotice
from record_transcript_resume.updates import (
    ApplicationUpdate, UPDATE_CHECK_INTERVAL_MS, UPDATE_CHECK_RETRY_MS,
)


def update_app():
    app = SimpleNamespace(
        _update_check_running=True, _update_install_running=False,
        _available_update=None, _update_check_after=None,
        update_hint=Mock(), update_check_button=Mock(), update_apply_button=Mock(),
        update_available_button=Mock(), compact_update_button=Mock(),
        _schedule_update_check=Mock(), _sync_update_indicator=Mock(),
        after=Mock(return_value="timer"), after_cancel=Mock(),
        _check_for_updates=Mock(), _poll_for_updates=Mock(), _retheme_widget_tree=Mock(), _compact_meter=Mock(),
    )
    return app


def test_periodic_check_schedules_a_single_next_attempt():
    app = update_app()
    app._update_check_after = "old"
    RecorderApp._schedule_update_check(app, UPDATE_CHECK_INTERVAL_MS)
    app.after_cancel.assert_called_once_with("old")
    assert app._update_check_after == "timer"
    app._poll_for_updates = Mock()


def test_poll_invokes_the_same_checker_as_the_manual_button():
    app = update_app()
    RecorderApp._poll_for_updates(app)
    app._schedule_update_check.assert_called_once_with(UPDATE_CHECK_INTERVAL_MS)
    app._check_for_updates.assert_called_once()


@pytest.mark.parametrize("running,installing", [(True, False), (False, True)])
def test_checks_never_overlap_downloads_or_another_check(running, installing):
    app = update_app()
    app._update_check_running = running
    app._update_install_running = installing
    RecorderApp._check_for_updates(app)
    app.update_check_button.configure.assert_not_called()


def test_offline_retry_preserves_an_already_confirmed_update():
    app = update_app()
    app._available_update = ApplicationUpdate(True, "New", "0.10.28")
    RecorderApp._on_update_checked(app, ApplicationUpdate(False, "Offline", check_succeeded=False))
    assert app._available_update.version == "0.10.28"
    app._schedule_update_check.assert_called_once_with(UPDATE_CHECK_RETRY_MS)
    assert app.update_apply_button.configure.call_args.kwargs["state"] == "normal"
    assert "0.10.28" in app.update_hint.set.call_args.args[0]


def test_successful_current_version_check_clears_the_old_indicator():
    app = update_app()
    app._available_update = ApplicationUpdate(True, "New", "0.10.28")
    result = ApplicationUpdate(False, "Current")
    RecorderApp._on_update_checked(app, result)
    assert app._available_update is result
    app._sync_update_indicator.assert_called_once()
    app._schedule_update_check.assert_called_once_with(UPDATE_CHECK_INTERVAL_MS)


def test_a_late_check_result_does_not_reenable_buttons_during_installation():
    app = update_app()
    app._update_install_running = True
    RecorderApp._on_update_checked(app, ApplicationUpdate(True, "New", "0.10.28"))
    app.update_apply_button.configure.assert_not_called()
    app.update_check_button.configure.assert_not_called()


def test_prepared_update_finishes_without_launching_a_second_installer():
    app = SimpleNamespace(_update_install_running=True, _update_helper_started=True,
                          _close_for_update=Mock())
    RecorderApp._apply_update(app)
    app._close_for_update.assert_called_once()


def test_unavailable_indicator_is_hidden_in_both_window_formats():
    app = update_app()
    RecorderApp._sync_update_indicator(app)
    app.update_available_button.pack_forget.assert_called_once()
    app.compact_update_button.pack_forget.assert_called_once()


@pytest.mark.parametrize("hidden,compact,busy,modal", [(True, False, False, False), (False, True, False, False), (False, False, True, False), (False, False, False, True)])
def test_release_popup_does_not_interrupt_hidden_compact_busy_or_modal_windows(hidden, compact, busy, modal):
    app = SimpleNamespace(
        _whats_new_after=None, _pending_release_notice=ReleaseNotice("0.10.28", "0.10.27", True),
        winfo_viewable=lambda: not hidden, _compact_mode=compact, state=lambda: "normal",
        _active_work_description=lambda: "recording" if busy else None,
        grab_current=lambda: object() if modal else None,
        after=Mock(), _maybe_show_release_notice=Mock(), _show_whats_new=Mock(),
    )
    RecorderApp._maybe_show_release_notice(app)
    app._show_whats_new.assert_not_called()
    assert app._pending_release_notice.pending


def test_release_popup_only_opens_if_the_version_is_still_unseen():
    app = SimpleNamespace(
        _whats_new_after=None, _pending_release_notice=ReleaseNotice("0.10.28", "0.10.27", True),
        winfo_viewable=lambda: True, _compact_mode=False, state=lambda: "normal",
        _active_work_description=lambda: None, grab_current=lambda: None,
        _release_notice_store=SimpleNamespace(has_seen=lambda _version: True), _show_whats_new=Mock(),
    )
    RecorderApp._maybe_show_release_notice(app)
    assert app._pending_release_notice is None
    app._show_whats_new.assert_not_called()
