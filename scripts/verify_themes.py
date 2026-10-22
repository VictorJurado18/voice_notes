r"""Render the real Windows GUI and capture every theme/page/window combination.

Run from the repository with .venv\Scripts\python.exe scripts/verify_themes.py
--output <folder>. This opens an isolated test instance on the desktop. It
invokes the actual UI buttons, uses temporary preferences/media/jobs, and never
records a microphone, contacts providers, or changes the user's library.

Screenshots are desktop pixels, not recreated HTML or mocked widget images.
The JSON report distinguishes rendered UI checks from manual pointer testing.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import statistics
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--themes", nargs="*")
    parser.add_argument("--pages", nargs="+", choices=("record", "file", "library", "processing", "youtube", "settings"),
                        help="Capture only selected destinations; the default covers every page.")
    parser.add_argument("--startup-only", action="store_true")
    parser.add_argument("--interactions-only", action="store_true")
    parser.add_argument("--appearance-only", action="store_true")
    parser.add_argument("--dialogs-only", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This capture run requires an unlocked Windows desktop.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Only this test process sees the temporary app-data path.
    temporary = tempfile.TemporaryDirectory(prefix="voice-notes-theme-qa-")
    os.environ["LOCALAPPDATA"] = temporary.name
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from PIL import Image, ImageChops, ImageDraw, ImageGrab
    import customtkinter as ctk
    import tkinter as tk
    from record_transcript_resume import gui
    from record_transcript_resume.preferences import load_color_theme, save_color_theme
    from record_transcript_resume.themes import DEFAULT_THEME, THEMES, THEME_LABELS, ThemeColor

    library = Path(temporary.name) / "Biblioteca de teste"
    recording = library / "Reunião de planejamento"
    recording.mkdir(parents=True)
    (library / "Projetos").mkdir()
    audio = recording / "recording-20261018-100000.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * 16000)
    (recording / "transcription.md").write_text(
        "# Reunião de planejamento\n\nParticipante 1: Vamos revisar os próximos passos.\n", encoding="utf-8")
    (recording / "summary.md").write_text(
        "# Planejamento\n\n## Decisões\n- Revisar os temas.\n- Manter a biblioteca organizada.\n", encoding="utf-8")
    (library / "Notas.md").write_text("# Notas\n\nConteúdo de teste.", encoding="utf-8")
    gui.default_output_dir = lambda: library
    gui._saved_huggingface_token = lambda: ""
    # Suppress unrelated external services. All layout, drawing, state, page,
    # theme, window-mode and preference code runs unchanged.
    gui.RecorderApp._check_provider_login = lambda self: None
    gui.RecorderApp._check_for_updates = lambda self: None
    gui.RecorderApp._resume_interrupted_jobs = lambda self: None
    names = args.themes or list(THEMES)
    if not all(name in THEMES for name in names):
        parser.error("Unknown theme")
    save_color_theme(names[0] if args.startup_only else DEFAULT_THEME)
    app = gui.RecorderApp(enable_tray=False)
    failures: list[str] = []
    captures: list[dict] = []
    actions: list[dict] = []
    completed: list[str] = []
    transition_stability: list[dict] = []
    # Unexpected GUI error dialogs must fail the run, rather than block it.
    gui.messagebox.showerror = lambda title, message, **kwargs: failures.append(f"UI error: {title}: {message}")
    selected = app._job_store.enqueue(audio, recording, "pt", "small", "codex", "meeting")
    app._job_store.update(selected.id, status="failed", stage="Transcrição", error="Falha de teste: modelo local indisponível.")
    queued = app._job_store.enqueue(library / "entrevista.wav", library, "pt", "small", "claude", "meeting")
    app._job_store.update(queued.id, status="cancelled", stage="Cancelado pelo usuário")

    def callback_error(exc_type, value, tb):
        failure = "".join(traceback.format_exception(exc_type, value, tb))
        failures.append(failure)
        print(failure, flush=True)
    app.report_callback_exception = callback_error

    def visible_widgets(widget):
        if widget is app._theme_choice_grid or not widget.winfo_ismapped():
            return
        # Retained native pages remain mapped behind the raised opaque page.
        # They are not visible pixels and must not be audited as the front page.
        if getattr(widget, "_voice_page", app._current_page) != app._current_page:
            return
        yield widget
        if hasattr(widget, "_apply_appearance_mode") and not isinstance(
            widget, (ctk.CTk, ctk.CTkToplevel, ctk.CTkFrame, ctk.CTkScrollableFrame)
        ):
            return
        for child in widget.winfo_children():
            yield from visible_widgets(child)

    def native_checks():
        checked = 0
        options = ("fg_color", "bg_color", "text_color", "text_color_disabled", "border_color",
                   "hover_color", "progress_color", "button_color", "dropdown_fg_color", "dropdown_text_color", "dropdown_hover_color")
        for widget in visible_widgets(app):
            if not hasattr(widget, "_apply_appearance_mode"):
                continue
            checked += 1
            for option in options:
                try:
                    value = widget.cget(option)
                except (ValueError, AttributeError, tk.TclError):
                    continue
                if isinstance(value, ThemeColor) and value != value.for_theme(app._theme_name):
                    failures.append(f"Stale role {app._theme_name}: {widget} {option}: {value} / {value.role}")
            if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton)):
                label = getattr(widget, "_label", None) if isinstance(widget, ctk.CTkLabel) else getattr(widget, "_text_label", None)
                if label is not None:
                    foreground = widget.cget("fg_color")
                    expected = foreground if foreground != "transparent" else widget.cget("bg_color")
                    if (isinstance(widget, ctk.CTkButton) and widget._mouse_inside
                            and widget.cget("hover") and widget.cget("state") == "normal"):
                        # A real pointer can rest on a control during capture.
                        # Its label must match the active hover color in that
                        # case, rather than the button's resting foreground.
                        expected = widget.cget("hover_color") or expected
                    if label.winfo_rgb(label.cget("bg")) != label.winfo_rgb(expected):
                        failures.append(f"Native label background differs from its control: {widget}; theme={app._theme_name}; page={app._current_page}; fullscreen={app._maximized}; text={widget.cget('text')!r}; native={label.cget('bg')}; expected={expected}")
            if isinstance(widget, ctk.CTkScrollableFrame):
                parent = widget._parent_frame
                expected = parent.cget("fg_color")
                if expected == "transparent":
                    expected = parent.cget("bg_color")
                if widget.winfo_rgb(widget._parent_canvas.cget("bg")) != widget.winfo_rgb(expected):
                    failures.append(f"Native scroll canvas background differs from its frame: {widget}")
        return checked

    def capture(theme, mode, page, window=None):
        app.update_idletasks()
        target = window or app
        width, height = target.winfo_width(), target.winfo_height()
        x, y = target.winfo_rootx(), target.winfo_rooty()
        filename = f"{theme}--{mode}--{page}.png"
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True, include_layered_windows=True)
        image.save(output / filename)
        # A correct color binding does not prove the text was painted. Catch
        # native copied-scroll pixels that can leave fully visible labels blank.
        text_checks = 0
        for widget in visible_widgets(target):
            if not isinstance(widget, ctk.CTkLabel):
                continue
            native = getattr(widget, "_label", None)
            if native is None or len(str(native.cget("text")).strip()) < 3:
                continue
            left, top = native.winfo_rootx(), native.winfo_rooty()
            right, bottom = left + native.winfo_width(), top + native.winfo_height()
            clip = [x, y, x+width, y+height]
            parent = native.master
            while parent is not None and parent is not target:
                px, py = parent.winfo_rootx(), parent.winfo_rooty()
                clip = [max(clip[0],px),max(clip[1],py),
                        min(clip[2],px+parent.winfo_width()),min(clip[3],py+parent.winfo_height())]
                parent = parent.master
            if (right-left < 10 or bottom-top < 8 or left < clip[0] or top < clip[1]
                    or right > clip[2] or bottom > clip[3]):
                continue
            foreground = tuple(channel//257 for channel in native.winfo_rgb(native.cget("fg")))
            crop = image.crop((left-x,top-y,right-x,bottom-y)).convert("RGB")
            pixels = crop.get_flattened_data() if hasattr(crop,"get_flattened_data") else crop.getdata()
            if not any(all(abs(pixel[i]-foreground[i]) <= 20 for i in range(3)) for pixel in pixels):
                failures.append(f"Visible text not painted: {theme}/{mode}/{page}: {native.cget('text')!r}")
            text_checks += 1
        control_checks = 0
        for widget in visible_widgets(target):
            if not isinstance(widget, (ctk.CTkRadioButton, ctk.CTkFrame)):
                continue
            # This Frame subclass is a composite whose child buttons draw its
            # outline. Its inherited backing canvas intentionally has no border.
            if isinstance(widget, ctk.CTkSegmentedButton):
                continue
            if isinstance(widget, ctk.CTkFrame) and not widget.cget("border_width"):
                continue
            canvas = getattr(widget, "_canvas", None)
            if canvas is None or not canvas.winfo_ismapped():
                continue
            left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
            right, bottom = left + canvas.winfo_width(), top + canvas.winfo_height()
            if left < x or top < y or right > x+width or bottom > y+height:
                continue
            parent = canvas.master
            clipped = False
            while parent is not None and parent is not target:
                px, py = parent.winfo_rootx(), parent.winfo_rooty()
                if left < px or top < py or right > px+parent.winfo_width() or bottom > py+parent.winfo_height():
                    clipped = True
                    break
                parent = parent.master
            if clipped:
                continue
            colors = [widget.cget("border_color")]
            if isinstance(widget, ctk.CTkRadioButton):
                colors.append(widget.cget("fg_color"))
            expected = [tuple(c//257 for c in widget.winfo_rgb(widget._apply_appearance_mode(color))) for color in colors if color != "transparent"]
            crop = image.crop((left-x,top-y,right-x,bottom-y)).convert("RGB")
            if isinstance(widget, ctk.CTkFrame):
                # Inspect the border itself: labels inside a missing card may
                # still contain the same palette color and mask the defect.
                cw, ch = crop.size
                edges = [crop.crop(box) for box in ((0,0,cw,min(3,ch)), (0,max(0,ch-3),cw,ch),
                         (0,0,min(3,cw),ch), (max(0,cw-3),0,cw,ch))]
                pixels = [pixel for edge in edges for pixel in (edge.get_flattened_data() if hasattr(edge,"get_flattened_data") else edge.getdata())]
            else:
                pixels = crop.get_flattened_data() if hasattr(crop,"get_flattened_data") else crop.getdata()
            if not any(any(all(abs(pixel[i]-color[i]) <= 20 for i in range(3)) for color in expected) for pixel in pixels):
                failures.append(f"Control border not painted: {theme}/{mode}/{page}: {widget}")
            control_checks += 1
        captures.append(dict(theme=theme, mode=mode, page=page, file=filename,
                             width=width, height=height, checked_widgets=native_checks(),
                             checked_text_pixels=text_checks, checked_control_pixels=control_checks))
        print(f"CAPTURE {len(captures):03d} {filename} {width}x{height}", flush=True)

    steps = []
    def add_action(label, action, wait=350):
        steps.append((label, action, wait))

    def capture_view(theme, mode, page):
        capture(theme, mode, page)
        first, last = app._container._parent_canvas.yview()
        if last - first < .999:
            canvas = app._container._parent_canvas
            steps[:0] = [
                ("scroll-bottom", lambda: canvas.yview_moveto(1), 250),
                ("capture", lambda: capture(theme, mode, page + "-bottom"), 0),
                ("scroll-top", lambda: canvas.yview_moveto(0), 200),
            ]

    for theme in names:
        add_action("settings", lambda: app._page_buttons["settings"].invoke())
        add_action("appearance", lambda: app._settings_section_buttons["appearance"].invoke())
        add_action(f"theme:{theme}", lambda t=theme: app._theme_choice_buttons[t].invoke(), 250)
        for mode in ("focus", "fullscreen"):
            if mode == "fullscreen":
                add_action("fullscreen", lambda: app.maximize_button.invoke(), 280)
            for page in args.pages or ("record", "file", "library", "processing", "youtube", "settings"):
                add_action(f"page:{page}", lambda p=page: app._page_buttons[p].invoke())
                if page == "settings":
                    for section in app._settings_section_buttons:
                        add_action(f"section:{section}", lambda s=section: app._settings_section_buttons[s].invoke())
                        add_action("capture", lambda t=theme, m=mode, s=section: capture_view(t, m, f"settings-{s}"), 0)
                else:
                    add_action("capture", lambda t=theme, m=mode, p=page: capture_view(t, m, p), 0)
        add_action("focus", lambda: app.maximize_button.invoke(), 260)
        add_action("compact", lambda: app.minimize_button.invoke())
        add_action("capture", lambda t=theme: capture(t, "compact", "recorder"), 0)
        add_action("restore", lambda: app.compact_open_button.invoke(), 250)
        add_action("persisted", lambda t=theme: completed.append(t) if load_color_theme() == t else failures.append(f"Theme not saved: {t}"), 0)

    if args.startup_only:
        steps.clear()
        if app._theme_name != names[0]:
            failures.append(f"Startup ignored the saved theme: {names[0]}")
        add_action("settings", lambda: app._page_buttons["settings"].invoke())
        add_action("appearance", lambda: app._settings_section_buttons["appearance"].invoke())
        add_action("capture", lambda: capture(names[0], "focus", "startup"), 0)

    if args.appearance_only:
        steps.clear()

        def verify_settled(theme, mode):
            fast = Image.open(output / f"{theme}--{mode}--settings-appearance.png").convert("RGB")
            app.update_idletasks()
            x, y = app.winfo_rootx(), app.winfo_rooty()
            reference = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()), all_screens=True, include_layered_windows=True).convert("RGB")
            reference.save(output / f"reference--{theme}--{mode}.png")
            if reference.size != fast.size:
                failures.append(f"Window dimensions still changing after capture: {theme}/{mode}")
                return
            difference = ImageChops.difference(fast, reference)
            changed = sum(pixel != (0, 0, 0) for pixel in difference.get_flattened_data())
            fraction = changed / (fast.width * fast.height)
            transition_stability.append(dict(theme=theme, mode=mode, changed_pixels=changed, fraction=fraction))
            # Allow tiny hover/caret changes, not stale blocks of the old view.
            if fraction > .005:
                failures.append(f"Unsettled transition {theme}/{mode}: {fraction:.2%} of pixels changed")

        add_action("settings", lambda: app._page_buttons["settings"].invoke())
        add_action("appearance", lambda: app._settings_section_buttons["appearance"].invoke())
        for theme in names:
            add_action(f"theme:{theme}", lambda t=theme: app._theme_choice_buttons[t].invoke(), 250)
            add_action("capture", lambda t=theme: capture(t, "focus", "settings-appearance"), 650)
            add_action("settled", lambda t=theme: verify_settled(t, "focus"), 0)
            add_action("fullscreen", lambda: app.maximize_button.invoke(), 350)
            add_action("capture", lambda t=theme: capture(t, "fullscreen", "settings-appearance"), 650)
            add_action("settled", lambda t=theme: verify_settled(t, "fullscreen"), 0)
            add_action("focus", lambda: app.maximize_button.invoke(), 350)

    if args.interactions_only:
        steps.clear()

        def click_entry(name):
            index = next(i for i, entry in enumerate(app._browser_visible_entries) if entry.path.name == name)
            canvas = app._browser_canvas
            canvas.event_generate("<Button-1>", x=90, y=int(index * 70 + 20 - canvas.canvasy(0)))
            if app._browser_selected is None or app._browser_selected.path.name != name:
                raise AssertionError(f"Canvas selection failed: {name}")

        def close_document():
            window = app._library_document_window
            buttons = [widget for widget in visible_widgets(window) if isinstance(widget, ctk.CTkButton) and widget.cget("text") == "Fechar"]
            if len(buttons) != 1:
                raise AssertionError("Document close control missing")
            buttons[0].invoke()

        from types import SimpleNamespace
        for theme in names:
            add_action("settings", lambda: app._page_buttons["settings"].invoke())
            add_action("appearance", lambda: app._settings_section_buttons["appearance"].invoke())
            add_action(f"theme:{theme}", lambda t=theme: app._theme_choice_buttons[t].invoke(), 250)
            # Exercise the real asynchronous-result handler, in both states.
            add_action("update-none", lambda: app._on_update_checked(SimpleNamespace(available=False, message="Nenhuma atualização disponível.")))
            add_action("verification", lambda: app._settings_section_buttons["verification"].invoke())
            add_action("capture", lambda t=theme: capture(t, "focus", "update-none"), 0)
            add_action("update-available", lambda: app._on_update_checked(SimpleNamespace(available=True, message="Atualização de teste disponível.")))
            add_action("capture", lambda t=theme: capture(t, "focus", "update-available"), 0)
            for mode in ("focus", "fullscreen"):
                if mode == "fullscreen":
                    add_action("fullscreen", lambda: app.maximize_button.invoke(), 350)
                add_action("library", lambda: app._page_buttons["library"].invoke())
                add_action("select-folder", lambda: click_entry(recording.name))
                add_action("open-folder", lambda: app._browser_open_button.invoke())
                add_action("select-audio", lambda: click_entry(audio.name))
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "audio-selected"), 0)
                add_action("play", lambda: app._browser_play_button.invoke(), 100)
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "audio-playing"), 0)
                add_action("pause", lambda: app._browser_play_button.invoke(), 100)
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "audio-paused"), 0)
                add_action("select-document", lambda: click_entry("transcription.md"))
                add_action("open-document", lambda: app._browser_open_button.invoke())
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "document-editor", app._library_document_window), 0)
                add_action("close-document", close_document)
                add_action("up-folder", lambda: app._browser_up_button.invoke())
            add_action("focus", lambda: app.maximize_button.invoke(), 350)

    if args.dialogs_only:
        steps.clear()

        def dialog_window():
            windows = [widget for widget in app.winfo_children() if isinstance(widget, ctk.CTkToplevel) and widget.winfo_exists()]
            if len(windows) != 1:
                raise AssertionError(f"Expected one dialog, found {len(windows)}")
            return windows[0]

        def click_button(parent, text):
            buttons = [widget for widget in visible_widgets(parent) if isinstance(widget, ctk.CTkButton) and widget.cget("text") == text]
            if not buttons:
                raise AssertionError(f"Button missing: {text}")
            buttons[0].invoke()

        for theme in names:
            add_action("settings", lambda: app._page_buttons["settings"].invoke())
            add_action("appearance", lambda: app._settings_section_buttons["appearance"].invoke())
            add_action(f"theme:{theme}", lambda t=theme: app._theme_choice_buttons[t].invoke(), 250)
            for mode in ("focus", "fullscreen"):
                if mode == "fullscreen":
                    add_action("fullscreen", lambda: app.maximize_button.invoke(), 350)
                add_action("profiles", lambda: app._settings_section_buttons["profiles"].invoke())
                add_action("scroll-bottom", lambda: app._container._parent_canvas.yview_moveto(1))
                add_action("new-profile", lambda: click_button(app._settings_sections["profiles"], "+ Novo perfil"))
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "new-profile-dialog", dialog_window()), 0)
                add_action("cancel-profile", lambda: click_button(dialog_window(), "Cancelar"))
                add_action("scroll-top", lambda: app._container._parent_canvas.yview_moveto(0))
                add_action("prompt", lambda: click_button(app._settings_sections["profiles"], "Ver prompt"))
                add_action("capture", lambda t=theme, m=mode: capture(t, m, "prompt-dialog", dialog_window()), 0)
                add_action("close-prompt", lambda: click_button(dialog_window(), "Fechar"))
            add_action("focus", lambda: app.maximize_button.invoke(), 350)

    started = time.perf_counter()
    def finish():
        metrics = [a["ms"] for a in actions if a["action"].startswith("theme:")] or [0]
        report = dict(
            captures=captures, failures=failures, actions=actions,
            preference_round_trips=completed, duration_seconds=round(time.perf_counter() - started, 2),
            transition_stability=transition_stability,
            theme_switch_ms=dict(median=round(statistics.median(metrics), 2), maximum=max(metrics)),
            method="Actual RecorderApp, real UI button invoke(), Windows desktop pixel screenshots; unrelated external service checks suppressed; no physical mouse input.",
        )
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Contact sheets aid human review of every frame. Individual full-size
        # captures remain available, including their exact measured dimensions.
        for theme in names:
            for mode in ("focus", "fullscreen", "compact"):
                group = [item for item in captures if item["theme"] == theme and item["mode"] == mode]
                if not group:
                    continue
                cell_w, cell_h = (400, 530) if mode == "focus" else (640, 390) if mode == "fullscreen" else (640, 100)
                columns = 3 if mode != "compact" else 1
                sheet = Image.new("RGB", (cell_w * columns, cell_h * ((len(group) + columns - 1) // columns)), "#DDE2EB")
                draw = ImageDraw.Draw(sheet)
                for index, item in enumerate(group):
                    x, y = (index % columns) * cell_w, (index // columns) * cell_h
                    draw.text((x + 8, y + 6), f'{theme} / {mode} / {item["page"]}', fill="#101827")
                    with Image.open(output / item["file"]) as shot:
                        shot.thumbnail((cell_w - 12, cell_h - 28))
                        sheet.paste(shot, (x + 6, y + 25))
                sheet.save(output / f"contact--{theme}--{mode}.jpg", quality=92)
        cards = "".join(
            f'<a class="card" data-theme="{item["theme"]}" data-mode="{item["mode"]}" href="{item["file"]}" target="_blank"><b>{html.escape(THEME_LABELS[item["theme"]])} · {item["mode"]} · {item["page"]}</b><img loading="lazy" src="{item["file"]}"></a>'
            for item in captures
        )
        gallery = '<!doctype html><meta charset="utf-8"><title>Voice Notes — revisão dos temas</title><style>body{margin:24px;background:#edf0f5;color:#202a3b;font:15px system-ui}header{position:sticky;top:0;background:#edf0f5;padding:12px;z-index:1}select{padding:8px;margin:8px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}.card{background:white;border:1px solid #ccd4e2;padding:12px;border-radius:10px;color:inherit;text-decoration:none}img{width:100%;height:auto;margin-top:12px}b{display:block;font-size:13px}</style>'
        gallery += f'<header><h1>Capturas reais do app</h1><p>{len(captures)} capturas · {len(failures)} falhas · troca mediana {report["theme_switch_ms"]["median"]} ms</p><select id="theme"><option value="">Todos os temas</option>'
        gallery += "".join(f'<option value="{name}">{html.escape(THEME_LABELS[name])}</option>' for name in names)
        gallery += '</select><select id="mode"><option value="">Todos os formatos</option><option>focus</option><option>fullscreen</option><option>compact</option></select></header><main>' + cards + '</main><script>function filter(){document.querySelectorAll(".card").forEach(c=>c.style.display=(!theme.value||c.dataset.theme===theme.value)&&(!mode.value||c.dataset.mode===mode.value)?"":"none")}theme.onchange=mode.onchange=filter;</script>'
        (output / "index.html").write_text(gallery, encoding="utf-8")
        print("RESULT", json.dumps(dict(captures=len(captures), failures=len(failures),
              preference_round_trips=completed, duration_seconds=report["duration_seconds"],
              theme_switch_ms=report["theme_switch_ms"]), ensure_ascii=False), flush=True)
        app.destroy()

    def next_step():
        if not steps:
            finish()
            return
        label, action, wait = steps.pop(0)
        before = time.perf_counter()
        try:
            action()
            if label in {"fullscreen", "focus"}:
                app.attributes("-topmost", True)
                app.lift()
        except Exception:
            failures.append(traceback.format_exc())
            print(failures[-1], flush=True)
        actions.append(dict(action=label, ms=round((time.perf_counter() - before) * 1000, 2)))
        app.after(wait, next_step)

    app.after(500, next_step)
    app.mainloop()
    temporary.cleanup()
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
