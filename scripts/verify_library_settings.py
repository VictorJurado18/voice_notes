"""Exercise Library/Settings UI using fictional data and capture Windows pixels.

No real recording, account, library or update is accessed. AI responses are
synthetic fixtures; document rendering, workers, persistence and UI run normally.
Use --interactive to leave this isolated instance open for pointer checks.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.temp_root:
        args.temp_root.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = os.environ["TMP"] = str(args.temp_root.resolve())
        tempfile.tempdir = None
    temporary = tempfile.TemporaryDirectory(prefix="voice-notes-library-review-")
    os.environ["LOCALAPPDATA"] = temporary.name
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from PIL import ImageGrab
    from record_transcript_resume import gui, synthesis
    from record_transcript_resume.meeting_topics import load_topic, save_topic

    library = Path(temporary.name) / "Biblioteca de exemplo"
    old = library / "recording-20261019-090000"
    new = library / "recording-20261020-110000"
    for folder in (old, new):
        folder.mkdir(parents=True)
        with wave.open(str(folder / f"{folder.name}.wav"), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 16000)
        (folder / "summary.md").write_text(
            "# Planejamento da plataforma\n\n## Decisões\n"
            "Revisar o cronograma e dividir as entregas entre as equipes.\n", encoding="utf-8",
        )
        (folder / "transcription.md").write_text(
            "# Transcrição\n\nPessoa 1: Precisamos revisar o cronograma.\n", encoding="utf-8",
        )
    save_topic(new, "Revisão do cronograma e divisão das entregas")
    (library / "Projetos").mkdir()
    (library / "Notas.md").write_text("# Notas\n\nDocumento de exemplo.", encoding="utf-8")
    gui.default_output_dir = lambda: library
    gui._saved_huggingface_token = lambda: ""
    gui.RecorderApp._check_provider_login = lambda self: None
    gui.RecorderApp._check_for_updates = lambda self: None
    gui.RecorderApp._resume_interrupted_jobs = lambda self: None
    app = gui.RecorderApp(enable_tray=False)
    app.title("Voice Notes · Biblioteca de exemplo · QA")
    failures, captures, requests, opened = [], [], [], []
    heartbeats = [0]
    gui.messagebox.showerror = lambda title, text, **kw: failures.append(f"{title}: {text}")

    def synthetic_response(prompt, provider):
        requests.append({"provider": provider, "summary_only": "Resumo:\n# Planejamento" in prompt})
        time.sleep(.35)  # UI must remain responsive while the provider works.
        return json.dumps({"topic": "Planejamento das prioridades e dos prazos da plataforma"})
    synthesis._provider_response = synthetic_response
    actual_startfile = os.startfile
    def open_pdf(path):
        path = Path(path)
        assert path.suffix == ".pdf" and path.read_bytes().startswith(b"%PDF")
        opened.append(str(path))
        if args.interactive:
            actual_startfile(str(path))
    gui.os.startfile = open_pdf

    def error_callback(kind, value, tb):
        failures.append("".join(traceback.format_exception(kind, value, tb)))
    app.report_callback_exception = error_callback

    def beat():
        heartbeats[0] += 1
        app.after(25, beat)
    app.after(25, beat)

    def select(path):
        app._browser_selected = next(entry for entry in app._browser_visible_entries if entry.path == path)
        app._browser_select()
        app._draw_browser_rows()

    def capture(name):
        app.update_idletasks()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x+app.winfo_width(), y+app.winfo_height()),
                       all_screens=True, include_layered_windows=True).save(output / f"{name}.png")
        captures.append(name)
        if app._current_page == "library":
            if app._container._parent_canvas.yview()[1] - app._container._parent_canvas.yview()[0] < .999:
                failures.append(f"Outer Library viewport overflows: {name}")
                print("OVERFLOW", {"canvas":app._container._parent_canvas.winfo_height(),
                    "panel":app._focus_library_panel.winfo_height(), "desired":app._focus_library_panel.cget("height"),
                    "content":app._container.winfo_height(), "region":app._container._parent_canvas.cget("scrollregion"),
                    "yview":app._container._parent_canvas.yview()}, flush=True)
            preview = app._browser_preview
            for widget in (app._browser_open_button.master, app._browser_secondary_actions,
                           app._browser_topic_label, app._browser_topic_button):
                if widget.winfo_ismapped() and widget.winfo_y()+widget.winfo_height() > preview.winfo_height():
                    failures.append(f"Preview control clipped: {name}/{widget}")
            for widget in (app._browser_count_label, app._browser_full_path_label):
                if not widget.winfo_ismapped() or widget.winfo_y()+widget.winfo_height() > widget.master.winfo_height():
                    failures.append(f"Library footer clipped: {name}/{widget}")
        print("CAPTURE", name, flush=True)

    def check_sort():
        assert app._browser_sort.get() == "Mais recentes"
        entries = app._browser_visible_entries
        assert entries.index(next(e for e in entries if e.path == new)) < entries.index(next(e for e in entries if e.path == old))

    def check_topic():
        assert load_topic(old) and requests and requests[-1]["summary_only"]
        assert not app._topic_active_folder
        assert heartbeats[0] > before_generation[0] + 4

    def check_pdf():
        assert opened and not app._pdf_preview_running

    def close_editor():
        app.transcript_editor.edit_modified(False)
        app._close_transcript_editor()

    steps = []
    def add(label, action, wait=450):
        steps.append((label, action, wait))
    add("library", lambda: app._page_buttons["library"].invoke())
    add("sort", check_sort, 0)
    add("select-new", lambda: select(new))
    add("capture-new", lambda: capture("focus-new-topic"), 0)
    add("select-old", lambda: select(old))
    add("capture-old", lambda: capture("focus-old-topic"), 0)
    before_generation = [0]
    add("heartbeat", lambda: before_generation.__setitem__(0, heartbeats[0]), 0)
    add("generate-topic", lambda: app._browser_topic_button.invoke(), 1200)
    add("check-topic", check_topic, 0)
    add("capture-generated", lambda: capture("focus-generated-topic"), 0)
    add("preview-pdf", lambda: app._browser_pdf_button.invoke(), 1000)
    add("check-pdf", check_pdf, 0)
    add("open-folder", lambda: app._browser_open_button.invoke())
    add("select-document", lambda: select(old / "summary.md"))
    add("capture-document", lambda: capture("focus-document-actions"), 0)
    add("open-editor", lambda: app._browser_open_button.invoke())
    add("editor-pdf", lambda: app._editor_pdf_button.invoke(), 1000)
    add("check-editor-pdf", lambda: (check_pdf(), len(opened) == 2 or failures.append("Editor PDF missing")), 0)
    add("close-editor", close_editor)
    add("up", lambda: app._browser_up_button.invoke())
    add("select-new", lambda: select(new))
    add("fullscreen", lambda: app.maximize_button.invoke(), 600)
    add("capture-full", lambda: capture("fullscreen-new-topic"), 0)
    for section in app._settings_section_buttons:
        add("settings", lambda: app._page_buttons["settings"].invoke())
        add("section", lambda key=section: app._settings_section_buttons[key].invoke())
        add("capture-settings", lambda key=section: capture(f"fullscreen-settings-{key}"), 0)
    add("focus", lambda: app.maximize_button.invoke(), 600)
    add("library", lambda: app._page_buttons["library"].invoke())
    add("select-old", lambda: select(old))
    add("final", lambda: capture("focus-library-final"), 0)

    def finish():
        report = {"failures": failures, "captures": captures, "requests": requests,
                  "pdf_previews": opened, "heartbeats": heartbeats[0],
                  "method": "Real GUI callbacks/workers and Windows pixels; synthetic AI provider and fictional meetings."}
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULT", json.dumps({"failures": failures, "captures": len(captures), "pdf_previews": len(opened)}), flush=True)
        if args.interactive:
            app.overrideredirect(False)
            app.lift()
        else:
            app.destroy()

    def next_step():
        if not steps:
            finish()
            return
        label, action, wait = steps.pop(0)
        try:
            action()
            app.lift()
        except Exception:
            failures.append(f"{label}: {traceback.format_exc()}")
        app.after(wait, next_step)
    app.after(600, next_step)
    app.mainloop()
    temporary.cleanup()
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
