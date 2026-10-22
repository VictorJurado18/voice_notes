"""Exercise update notifications and release notices in an isolated real GUI.

The update service is a deterministic fixture: no installer is downloaded or
executed. Screenshots are actual desktop pixels; UI buttons invoke their real
callbacks. No user library, account, microphone or system setting is changed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="update-ui-", dir=output)
    os.environ["LOCALAPPDATA"] = temporary.name
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import customtkinter as ctk
    from PIL import ImageGrab
    from record_transcript_resume import gui, updates
    from record_transcript_resume.preferences import save_color_theme
    library = Path(temporary.name) / "Biblioteca de exemplo"
    for name in ("planejamento", "entrevista"):
        folder = library / name
        folder.mkdir(parents=True)
        with wave.open(str(folder / (name + ".wav")), "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * 16000)
    save_color_theme("oceano")
    gui.default_output_dir = lambda: library
    gui.RecorderApp._check_provider_login = lambda self: None
    gui.RecorderApp._resume_interrupted_jobs = lambda self: None
    poll_calls = []
    def check_updates():
        poll_calls.append(time.monotonic())
        if len(poll_calls) == 2:
            return updates.ApplicationUpdate(False, "Falha de conexão simulada.", check_succeeded=False)
        return updates.ApplicationUpdate(True, "Nova versão disponível: 0.10.999.", "0.10.999", "https://example.invalid/setup.exe")
    updates.check_for_updates = check_updates
    updates.UPDATE_CHECK_INTERVAL_MS = 700
    updates.UPDATE_CHECK_RETRY_MS = 400
    app = gui.RecorderApp(enable_tray=False)
    app.withdraw()
    major, minor, patch = updates.APP_VERSION.split(".")
    previous = f"{major}.{minor}.{max(0,int(patch)-1)}"
    app._release_notice_store.prepare(previous)
    checks, failures, captures = [], [], []
    app.report_callback_exception = lambda kind, value, tb: failures.append("".join(traceback.format_exception(kind, value, tb)))
    gui.messagebox.showerror = lambda title, text, **kw: failures.append(f"{title}: {text}")

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    def capture(name, target=None):
        target = target or app
        target.update_idletasks()
        x, y = target.winfo_rootx(), target.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+target.winfo_width(),y+target.winfo_height()),
                       all_screens=True, include_layered_windows=True).save(output / (name + ".png"))
        captures.append(name)
        print("CAPTURE", name, flush=True)

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def button(parent, label):
        matches = [w for w in widgets(parent) if isinstance(w, ctk.CTkButton) and w.cget("text") == label and w.winfo_ismapped()]
        if len(matches) != 1:
            raise AssertionError(f"Expected one visible button {label}, got {len(matches)}")
        return matches[0]

    def header_bounds():
        controls = [w for w in app._window_controls.winfo_children() if isinstance(w, ctk.CTkButton) and w.winfo_ismapped()]
        boxes = sorted((w.winfo_rootx(),w.winfo_rootx()+w.winfo_width()) for w in controls)
        check("Header controls do not overlap", all(right <= next_left for (_,right),(next_left,_) in zip(boxes,boxes[1:])))
        check("Header controls stay within the window", boxes[0][0] >= app.winfo_rootx() and boxes[-1][1] <= app.winfo_rootx()+app.winfo_width())

    steps = []
    def add(name, callback, wait=350):
        steps.append((name, callback, wait))

    add("hidden-start", lambda: check("Hidden startup does not consume release notice", app._pending_release_notice.pending and app._whats_new_dialog is None and not app._release_notice_store.has_seen(updates.APP_VERSION)))
    add("automatic-check", lambda: check("Startup check discovers new release while hidden", bool(app._available_update and app._available_update.available)), 800)
    add("automatic-offline-retry", lambda: check("Periodic and offline retry preserve confirmed update", len(poll_calls) >= 2 and app._available_update.available))
    add("show-window", app._show_widget, 800)
    add("popup-mapped", lambda: check("Release notice marks version seen only after display", app._whats_new_dialog is not None and app._whats_new_dialog.winfo_viewable() and app._release_notice_store.has_seen(updates.APP_VERSION)))
    add("popup-capture", lambda: capture("focus-release-notice", app._whats_new_dialog), 0)
    add("understood", lambda: button(app._whats_new_dialog,"Entendido").invoke())
    add("same-version", app._prepare_release_notice, 500)
    add("only-once", lambda: check("Same version does not reopen automatically", app._whats_new_dialog is None and not app._pending_release_notice.pending))
    add("focus-indicator", header_bounds, 0)
    add("focus-capture", lambda: capture("focus-update-indicator"), 0)
    add("indicator-click", lambda: app.update_available_button.invoke())
    add("updates-page", lambda: check("Indicator opens Updates settings without starting installer", app._current_page=="settings" and app._active_settings_section=="updates" and not app._update_install_running))
    add("manual-notice", lambda: app.whats_new_button.invoke())
    add("manual-capture", lambda: capture("manual-release-notice",app._whats_new_dialog),0)
    add("manual-close", lambda: button(app._whats_new_dialog,"Entendido").invoke())
    add("library", lambda: app.library_button.invoke(),600)
    def edit_search():
        app._browser_search_entry.focus_set()
        app._browser_search_entry.insert(0,"planejamento")
        app._browser_search_entry._entry.event_generate("<KeyRelease>",keysym="o")
    add("search-edit", edit_search)
    add("search-result", lambda: check("Search entry edits filter actual library rows", len(app._browser_visible_entries)==1 and app._browser_visible_entries[0].path.name=="planejamento"))
    add("search-capture", lambda: capture("focus-library-search"),0)
    add("clear-search", lambda: app._browser_search.set(""))
    add("search-cleared", lambda: check("Programmatic clear restores both rows and the field", len(app._browser_visible_entries)==2 and app._browser_search_entry.get()==""))
    add("select-all", app._browser_select_all)
    add("batch-review", lambda: app._browser_batch_button.invoke())
    add("batch-capture", lambda: capture("batch-review",app._batch_dialog),0)
    add("batch-cancel", lambda: button(app._batch_dialog,"Cancelar").invoke())
    add("full", lambda: app.maximize_button.invoke(),500)
    add("full-header", header_bounds,0)
    add("full-click", lambda: app.update_available_button.invoke())
    add("full-update-capture", lambda: capture("fullscreen-update-settings"),0)
    add("api-section", lambda: app._settings_section_buttons["provider"].invoke())
    add("api-form", lambda: app.new_provider_button.invoke())
    add("api-capture", lambda: capture("fullscreen-provider-form"),0)
    add("api-bottom", lambda: app._container._parent_canvas.yview_moveto(1))
    add("api-bottom-capture", lambda: capture("fullscreen-provider-form-bottom"),0)
    add("api-close", lambda: app.new_provider_button.invoke())
    add("compact", lambda: app.minimize_button.invoke())
    add("compact-capture", lambda: capture("compact-update-indicator"),0)
    def compact_bounds():
        visible=[w for w in widgets(app._compact_surface) if isinstance(w,ctk.CTkButton) and w.winfo_ismapped()]
        check("Compact actions remain within 584 pixels", all(w.winfo_rootx()+w.winfo_width() <= app.winfo_rootx()+app.winfo_width() for w in visible))
        check("Compact update indicator is visible",app.compact_update_button.winfo_ismapped())
    add("compact-bounds",compact_bounds,0)
    add("compact-click",lambda: app.compact_update_button.invoke(),500)
    add("compact-opens-updates",lambda:check("Compact update flag restores normal window and opens Updates",not app._compact_mode and app._active_settings_section=="updates"))
    add("focus",lambda:app.maximize_button.invoke(),500)
    # Fit the fixed modes to a smaller monitor without changing system settings.
    def small_monitor():
        app._current_monitor_bounds = lambda **kw:(0,0,1280,720)
        app._monitor_bounds_at = lambda *args, **kw:(0,0,1280,720)
    add("small-monitor",small_monitor,0)
    add("small-focus",app._apply_page_minimum,500)
    for page in ("record","file","library","processing","youtube","settings"):
        add("small-"+page,lambda p=page:app._page_buttons[p].invoke())
        add("small-capture",lambda p=page:capture("small-focus-"+p),0)
    add("small-popup",lambda:app.whats_new_button.invoke())
    add("small-popup-capture",lambda:capture("small-release-notice",app._whats_new_dialog),0)
    add("small-popup-close",lambda:button(app._whats_new_dialog,"Entendido").invoke())
    add("small-full",lambda:app.maximize_button.invoke(),500)
    add("small-full-bounds",lambda:check("Small full-screen really uses 1280x720",(app.winfo_width(),app.winfo_height())==(1280,720)),0)
    for page in ("record","file","library","processing","youtube","settings"):
        add("small-full-"+page,lambda p=page:app._page_buttons[p].invoke())
        add("small-full-capture",lambda p=page:capture("small-fullscreen-"+p),0)
    add("periodic-count",lambda:check("Automatic checks continue without pressing Verify",len(poll_calls)>=5),0)

    def finish():
        (output/"report.json").write_text(json.dumps(dict(checks=checks,failures=failures,captures=captures,
               automatic_checks=len(poll_calls),method=__doc__),ensure_ascii=False,indent=2),encoding="utf-8")
        print("RESULT",json.dumps(dict(checks=len(checks),failures=failures,captures=len(captures),automatic_checks=len(poll_calls)),ensure_ascii=False),flush=True)
        app.destroy()

    def next_step():
        if not steps or failures:
            finish()
            return
        label, callback, wait = steps.pop(0)
        try:
            callback()
            app.lift()
        except Exception:
            failures.append(label+": "+traceback.format_exc())
        app.after(wait,next_step)
    app.after(2100,next_step)
    app.mainloop()
    temporary.cleanup()
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
