"""Retained navigation controls that wait for Tk's layout to settle."""
from __future__ import annotations

from contextlib import contextmanager
import sys
import tkinter as tk
from typing import Iterator

import customtkinter as ctk


_WM_SETREDRAW = 0x000B
_RDW_INVALIDATE = 0x0001
_RDW_ERASE = 0x0004
_RDW_ALLCHILDREN = 0x0080
_RDW_FRAME = 0x0400
_frozen_windows: set[int] = set()


@contextmanager
def frozen_paint(widget: tk.Misc) -> Iterator[None]:
    """Present a navigation change as one finished frame on Windows.

    Tk and CustomTkinter paint every control separately and without double
    buffering, so raising a page shows it being assembled piece by piece.
    WM_SETREDRAW suspends painting of the application's client window while
    the destination is raised and laid out, then one invalidation repaints the
    final result. Hidden windows are left alone: re-enabling redraw would set
    WS_VISIBLE on them. Any failure simply falls back to normal painting.
    """
    user32 = None
    hwnd = 0
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(widget.winfo_id())
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
            user32.IsWindowVisible.restype = ctypes.c_int
            user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.RedrawWindow.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)
            user32.RedrawWindow.restype = ctypes.c_int
            if not hwnd or hwnd in _frozen_windows or not user32.IsWindowVisible(hwnd):
                user32 = None
            else:
                user32.SendMessageW(hwnd, _WM_SETREDRAW, 0, 0)
                _frozen_windows.add(hwnd)
        except (AttributeError, OSError, ValueError, tk.TclError):
            user32 = None
    try:
        yield
    finally:
        if user32 is not None:
            _frozen_windows.discard(hwnd)
            try:
                user32.SendMessageW(hwnd, _WM_SETREDRAW, 1, 0)
                user32.RedrawWindow(hwnd, None, None,
                                    _RDW_INVALIDATE | _RDW_ERASE | _RDW_ALLCHILDREN | _RDW_FRAME)
            except OSError:
                pass


class RetainedPageDeck(ctk.CTkFrame):
    """Keep every destination's native viewport at stable bounds.

    Raising an opaque page preserves its layout, canvas origin and controls.
    No destination is unpacked merely because the user visits another one.
    """

    def __init__(self, master, *, pages, color, **kwargs) -> None:
        super().__init__(master, fg_color=color, corner_radius=0, **kwargs)
        self.shells: dict[str, ctk.CTkFrame] = {}
        self.viewports: dict[str, NavigationScrollFrame] = {}
        self.current: str | None = None
        for name in pages:
            shell = ctk.CTkFrame(self, fg_color=color, corner_radius=0)
            shell._voice_page = name
            shell.place(x=0, y=0, relwidth=1, relheight=1)
            viewport = NavigationScrollFrame(shell, fg_color="transparent", corner_radius=0,
                                             scrollbar_fg_color="transparent")
            viewport.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 4))
            viewport._parent_frame.grid_columnconfigure(1, minsize=viewport._scrollbar.winfo_reqwidth())
            self.shells[name] = shell
            self.viewports[name] = viewport

    def show(self, name: str) -> None:
        if name not in self.shells:
            raise ValueError(f"Unknown page: {name}")
        self.shells[name].tkraise()
        self.current = name


class NavigationScrollFrame(ctk.CTkScrollableFrame):
    """Coalesce scrollbar paints without flushing partially mapped pages.

    CTkScrollbar.set redraws even unchanged fractions and its drawing routine
    calls update_idletasks. Calling it from Canvas's yscrollcommand reenters
    geometry/painting while a destination is still being packed. Keep CTk's
    drawing and input behavior, but deliver only the final changed fractions.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._scroll_paint_after: str | None = None
        self._scroll_fractions: tuple[float, float] | None = None
        self._painted_scroll_fractions: tuple[float, float] | None = None
        axis = "xscrollcommand" if self._orientation == "horizontal" else "yscrollcommand"
        self._parent_canvas.configure(**{axis: self._queue_scrollbar})
        self.bind("<Destroy>", self._cancel_scroll_paint, add="+")

    def _queue_scrollbar(self, first: str, last: str) -> None:
        self._scroll_fractions = (float(first), float(last))
        if self._scroll_paint_after is None:
            self._scroll_paint_after = self.after_idle(self._paint_scrollbar)

    def _paint_scrollbar(self) -> None:
        self._scroll_paint_after = None
        fractions = self._scroll_fractions
        if fractions is not None and fractions != self._painted_scroll_fractions:
            self._painted_scroll_fractions = fractions
            self._scrollbar.set(*fractions)

    def _cancel_scroll_paint(self, event: tk.Event) -> None:
        if event.widget is self and self._scroll_paint_after is not None:
            self.after_cancel(self._scroll_paint_after)
            self._scroll_paint_after = None
