from types import SimpleNamespace
from unittest.mock import Mock

import tkinter as tk

from record_transcript_resume import gui
from record_transcript_resume.gui import RecorderApp


def test_selecting_current_page_does_not_repack_or_retheme_controls():
    app = SimpleNamespace(
        _page_layouts={"library": []}, _maximized=False, _desktop_layout=False,
        _shown_page_key=("library", False, False, False, False),
        _refresh_page_data=Mock(), _apply_page_theme=Mock(), _ensure_page_layout=Mock(),
    )
    RecorderApp._show_page(app, "library")
    app._refresh_page_data.assert_called_once_with("library")
    app._apply_page_theme.assert_not_called()
    app._ensure_page_layout.assert_not_called()


def test_page_canvas_repair_is_cached_at_unchanged_bounds():
    app = SimpleNamespace(
        _navigation_serial=2, _compact_mode=False, _current_page="file",
        _maximized=False, _desktop_layout=False, _page_paint_cache={},
        _container=SimpleNamespace(_parent_canvas=SimpleNamespace(winfo_width=lambda: 740,winfo_height=lambda: 800)),
        _apply_page_theme=Mock(), after_idle=Mock(), _invalidate_native_content=Mock(),
    )
    RecorderApp._settle_page_paint(app,2)
    RecorderApp._settle_page_paint(app,2)
    app._apply_page_theme.assert_called_once_with("file",force=True)
    RecorderApp._settle_page_paint(app,1)
    assert app.after_idle.call_count == 2


def test_native_repaint_includes_backing_canvases_and_skips_hidden_controls(monkeypatch):
    monkeypatch.setattr(gui.sys, "platform", "win32")
    monkeypatch.setattr(tk.Misc, "winfo_children", lambda widget: widget.native_children)
    class Canvas:
        pass
    monkeypatch.setattr(gui.tk, "Canvas", Canvas)
    shown = Canvas()
    shown.winfo_ismapped = lambda: True
    shown.native_children = []
    shown.configure = Mock()
    shown.cget = lambda key: "#123456"
    hidden = SimpleNamespace(winfo_ismapped=lambda: False, configure=Mock())
    app = SimpleNamespace(winfo_exists=lambda: True, winfo_ismapped=lambda: True,
                          configure=Mock(), native_children=[shown, hidden],
                          update_idletasks=Mock(),
                          winfo_children=lambda: [],  # CTkFrame hides its backing canvas.
                          winfo_width=lambda: 760, winfo_height=lambda: 920)
    RecorderApp._invalidate_native_content(app)
    app.configure.assert_not_called()
    shown.configure.assert_called_once_with(background="#123456")
    hidden.configure.assert_not_called()
    assert app.update_idletasks.call_count == 2


def test_native_repaint_tolerates_a_window_closing(monkeypatch):
    monkeypatch.setattr(gui.sys, "platform", "win32")
    app = SimpleNamespace(winfo_exists=lambda: True, winfo_ismapped=lambda: True,
                          update_idletasks=Mock(side_effect=tk.TclError("destroyed")))
    RecorderApp._invalidate_native_content(app)
    assert not app._native_repaint_running


def test_old_background_library_result_cannot_overwrite_a_newer_request(tmp_path):
    root = tmp_path / "library"
    app = SimpleNamespace(
        _library_scan_running=True, _library_scan_generation=2,
        library_dir=SimpleNamespace(get=lambda:str(root)), _browser_directory=root,
        _apply_library_items=Mock(), _apply_browser_snapshot=Mock(), _start_library_scan=Mock(),
    )
    RecorderApp._finish_library_scan(app,1,root,root,(root,[],[],True,[]),None)
    assert not app._library_scan_running
    app._apply_library_items.assert_not_called()
    app._apply_browser_snapshot.assert_not_called()
    app._start_library_scan.assert_called_once()


def test_result_for_a_different_folder_is_discarded(tmp_path):
    root = tmp_path / "library"
    app = SimpleNamespace(
        _library_scan_running=True, _library_scan_generation=2,
        library_dir=SimpleNamespace(get=lambda:str(root)), _browser_directory=root / "other",
        _apply_library_items=Mock(), _apply_browser_snapshot=Mock(), _start_library_scan=Mock(),
    )
    RecorderApp._finish_library_scan(app,2,root,root,(root,[],[],True,[]),None)
    app._apply_browser_snapshot.assert_not_called()
    app._apply_library_items.assert_not_called()


class _FakeUser32:
    def __init__(self, visible=True):
        self.visible = visible
        self.calls = []
        for name in ("IsWindowVisible", "SendMessageW", "RedrawWindow"):
            setattr(self, name, self._recorder(name))

    def _recorder(self, name):
        def call(*args):
            self.calls.append((name, args))
            return self.visible if name == "IsWindowVisible" else 1
        return call


def _fake_windows(monkeypatch, user32):
    import ctypes
    from record_transcript_resume import navigation_view
    monkeypatch.setattr(navigation_view.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: user32, raising=False)
    return navigation_view


def test_frozen_paint_is_a_no_op_outside_windows(monkeypatch):
    from record_transcript_resume import navigation_view
    monkeypatch.setattr(navigation_view.sys, "platform", "linux")
    widget = SimpleNamespace(winfo_id=Mock())
    with navigation_view.frozen_paint(widget):
        pass
    widget.winfo_id.assert_not_called()


def test_frozen_paint_suspends_then_repaints_once(monkeypatch):
    user32 = _FakeUser32()
    navigation_view = _fake_windows(monkeypatch, user32)
    with navigation_view.frozen_paint(SimpleNamespace(winfo_id=lambda: 42)):
        assert [c for c in user32.calls if c[0] == "SendMessageW"] == [("SendMessageW", (42, 0x000B, 0, 0))]
    assert user32.calls[-2] == ("SendMessageW", (42, 0x000B, 1, 0))
    assert user32.calls[-1][0] == "RedrawWindow" and user32.calls[-1][1][0] == 42
    assert not navigation_view._frozen_windows


def test_frozen_paint_restores_painting_after_an_error(monkeypatch):
    user32 = _FakeUser32()
    navigation_view = _fake_windows(monkeypatch, user32)
    try:
        with navigation_view.frozen_paint(SimpleNamespace(winfo_id=lambda: 7)):
            raise RuntimeError("layout failed")
    except RuntimeError:
        pass
    assert ("SendMessageW", (7, 0x000B, 1, 0)) in user32.calls
    assert not navigation_view._frozen_windows


def test_frozen_paint_leaves_hidden_windows_and_nested_freezes_alone(monkeypatch):
    hidden = _FakeUser32(visible=False)
    navigation_view = _fake_windows(monkeypatch, hidden)
    with navigation_view.frozen_paint(SimpleNamespace(winfo_id=lambda: 9)):
        pass
    assert [c[0] for c in hidden.calls] == ["IsWindowVisible"]

    shown = _FakeUser32()
    navigation_view = _fake_windows(monkeypatch, shown)
    widget = SimpleNamespace(winfo_id=lambda: 11)
    with navigation_view.frozen_paint(widget):
        with navigation_view.frozen_paint(widget):
            pass
        assert 11 in navigation_view._frozen_windows
    assert sum(c[0] == "RedrawWindow" for c in shown.calls) == 1
