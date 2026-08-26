from __future__ import annotations

from unittest.mock import Mock, patch

from record_transcript_resume import windows_process


def test_terminate_process_tree_skips_finished_worker() -> None:
    process = Mock()
    process.poll.return_value = 0

    windows_process.terminate_process_tree(process)

    process.terminate.assert_not_called()


def test_terminate_process_tree_uses_process_terminate_outside_windows() -> None:
    process = Mock()
    process.poll.return_value = None
    with patch.object(windows_process.os, "name", "posix"):
        windows_process.terminate_process_tree(process)

    process.terminate.assert_called_once_with()


def test_terminate_process_tree_uses_taskkill_for_windows_worker() -> None:
    process = Mock(pid=4321)
    process.poll.return_value = None
    with (
        patch.object(windows_process.os, "name", "nt"),
        patch.object(windows_process.subprocess, "run") as run,
    ):
        windows_process.terminate_process_tree(process)

    assert run.call_args.args[0] == ["taskkill", "/PID", "4321", "/T", "/F"]
