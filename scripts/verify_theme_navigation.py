"""Check theme colors at native Map events, before navigation has settled.

Runs the real app with isolated preferences and no external service checks.
The native backing frame is briefly visible while Tk maps its drawing canvas;
checking only final screenshots does not catch an obsolete backing color.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--themes", nargs="*", default=["claro", "machine_red", "oceano"])
    parser.add_argument("--capture-delay", type=int, default=16,
                        help="Milliseconds after navigation to capture, without flushing redraws")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voice-notes-navigation-qa-") as temporary:
        os.environ["LOCALAPPDATA"] = temporary
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        import tkinter as tk
        import customtkinter as ctk
        from PIL import ImageGrab
        from record_transcript_resume import gui
        from record_transcript_resume.preferences import save_color_theme
        from record_transcript_resume.themes import ThemeColor

        library = Path(temporary) / "Biblioteca"
        library.mkdir()
        gui.default_output_dir = lambda: library
        gui._saved_huggingface_token = lambda: ""
        gui.RecorderApp._check_provider_login = lambda self: None
        gui.RecorderApp._check_for_updates = lambda self: None
        gui.RecorderApp._resume_interrupted_jobs = lambda self: None
        save_color_theme("violeta")
        app = gui.RecorderApp(enable_tray=False)
        failures: list[dict] = []
        mapped = 0
        timings: list[float] = []
        steps: list[tuple] = []
        screenshots: list[str] = []
        current = {"mode": "focus", "page": "record", "theme": "violeta"}

        def failure(kind, widget, **values):
            failures.append(dict(kind=kind, widget=str(widget), **current, **values))

        def check_widget(widget):
            for option in ("bg_color", "fg_color", "text_color", "border_color"):
                try:
                    value = widget.cget(option)
                except (ValueError, AttributeError, tk.TclError):
                    continue
                if isinstance(value, ThemeColor) and value != value.for_theme(app._theme_name):
                    failure("stale-role-at-map", widget, option=option, actual=value,
                            expected=value.for_theme(app._theme_name))
            if isinstance(widget, ctk.CTkBaseClass):
                expected = widget._apply_appearance_mode(widget.cget("bg_color"))
                actual = tk.Frame.cget(widget, "background")
                if widget.winfo_rgb(actual) != widget.winfo_rgb(expected):
                    failure("stale-native-backing-at-map", widget, actual=actual, expected=expected)

        def on_map(event):
            nonlocal mapped
            widget = event.widget
            if isinstance(widget, ctk.CTkBaseClass):
                mapped += 1
                check_widget(widget)

        app.bind_all("<Map>", on_map, add="+")
        app.report_callback_exception = lambda typ, value, tb: failure("callback", app, error=str(value))

        def shot(label):
            # No update()/update_idletasks(): capture the frame as it is now.
            x, y = app.winfo_rootx(), app.winfo_rooty()
            name = f'{current["theme"]}--{current["mode"]}--{label}.png'
            ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()),
                           all_screens=True, include_layered_windows=True).save(args.output / name)
            screenshots.append(name)

        def navigate(page):
            current["page"] = page
            start = time.perf_counter()
            app._page_buttons[page].invoke()
            timings.append((time.perf_counter() - start) * 1000)

        def theme(name):
            current["theme"] = name
            app._theme_choice_buttons[name].invoke()

        def mode(name):
            current["mode"] = name
            app.maximize_button.invoke()

        def compact():
            current["mode"] = "compact"
            app.minimize_button.invoke()

        def restore():
            current["mode"] = "focus"
            app.compact_open_button.invoke()

        for name in args.themes:
            steps.append((lambda: navigate("settings"), 100))
            steps.append((lambda: app._settings_section_buttons["appearance"].invoke(), 100))
            steps.append((lambda n=name: theme(n), 100))
            for window_mode in ("focus", "fullscreen"):
                if window_mode == "fullscreen":
                    steps.append((lambda: mode("fullscreen"), 250))
                # First visits exercise hidden controls left in the previous
                # palette; second visits exercise the cached page path.
                for cycle in range(2):
                    for page in ("record", "file", "library", "processing", "youtube", "settings"):
                        steps.append((lambda p=page: navigate(p), args.capture_delay))
                        steps.append((lambda p=page, c=cycle: shot(f"{p}-{c}-early"), 80))
                        if page == "settings":
                            for section in app._settings_section_buttons:
                                steps.append((lambda s=section: app._settings_section_buttons[s].invoke(), args.capture_delay))
                                steps.append((lambda s=section, c=cycle: shot(f"settings-{s}-{c}-early"), 80))
                if window_mode == "fullscreen":
                    steps.append((lambda: mode("focus"), 250))
            steps.append((compact, args.capture_delay))
            steps.append((lambda: shot("recorder-early"), 80))
            steps.append((restore, 150))

        def finish():
            report = dict(map_events=mapped, failures=failures, screenshots=screenshots,
                          capture_delay_ms=args.capture_delay,
                          navigation_ms=dict(median=round(statistics.median(timings), 2),
                                             maximum=round(max(timings), 2)),
                          method="Real RecorderApp Map event checks and immediate native desktop captures; isolated preferences; UI button invoke, no physical mouse input.")
            (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({key: value for key, value in report.items() if key not in {"failures", "screenshots"}}), flush=True)
            print(f"FAILURES {len(failures)} / CAPTURES {len(screenshots)}", flush=True)
            app.destroy()

        def next_step():
            if not steps:
                finish()
                return
            action, wait = steps.pop(0)
            action()
            app.after(wait, next_step)

        app.after(600, next_step)
        app.mainloop()
        return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
