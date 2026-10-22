"""Real UI/recording service/encoder and subprocess protocol with synthetic audio.

Hardware capture and AI inference are replaced with deterministic fixtures.
Everything uses isolated app data; no real meeting, account or audio device is accessed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="voice-notes-parallel-", dir=output)
    os.environ["LOCALAPPDATA"] = temporary.name
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
    from PIL import ImageGrab
    import customtkinter as ctk
    import lameenc
    from record_transcript_resume import gui
    from record_transcript_resume.processing_metrics import media_duration
    from record_transcript_resume.recording import RecordingState
    from record_transcript_resume.preferences import save_color_theme
    save_color_theme("oceano")
    library = Path(temporary.name)/"Biblioteca de exemplo"
    media = []
    for name in ("planejamento", "cancelamento", "aguarda-memoria"):
        folder = library/name
        folder.mkdir(parents=True)
        audio = folder/f"{name}.wav"
        with wave.open(str(audio),"wb") as wav:
            wav.setparams((1,2,16000,0,"NONE","not compressed"))
            wav.writeframes(b"\0\0"*16000*60)
        media.append(audio)

    class SyntheticCapture:
        capture_warning = ""
        def __init__(self,config):
            self.stop_event = threading.Event()
        def start(self,path):
            def capture():
                encoder = lameenc.Encoder()
                encoder.set_bit_rate(128)
                encoder.set_in_sample_rate(48000)
                encoder.set_channels(2)
                encoder.set_quality(2)
                with path.open("wb") as stream:
                    while not self.stop_event.is_set():
                        stream.write(encoder.encode(b"\0\0"*4800*2))
                        time.sleep(.1)
                    stream.write(encoder.flush())
            self.thread = threading.Thread(target=capture,daemon=True)
            self.thread.start()
        def stop(self):
            self.stop_event.set()
            self.thread.join(timeout=3)
            assert not self.thread.is_alive()

    gui.WindowsAudioBackend = SyntheticCapture
    gui.default_output_dir = lambda:library
    gui._saved_huggingface_token = lambda:""
    gui.RecorderApp._check_provider_login = lambda self:None
    gui.RecorderApp._check_for_updates = lambda self:None
    gui.RecorderApp._resume_interrupted_jobs = lambda self:None
    gui.memory_headroom = lambda:16*1024**3
    actual_popen = gui.subprocess.Popen
    def fixture_worker(command,*args,**kwargs):
        if "record_transcript_resume._pipeline_proc" in command:
            index = command.index("record_transcript_resume._pipeline_proc")
            command = [command[0], str(Path(__file__).with_name("parallel_fixture_worker.py")), *command[index+1:]]
        return actual_popen(command,*args,**kwargs)
    gui.subprocess.Popen = fixture_worker
    app = gui.RecorderApp(enable_tray=False)
    failures, captures, checks, notices = [], [], [], []
    threading.excepthook = lambda event:failures.append("".join(traceback.format_exception(event.exc_type,event.exc_value,event.exc_traceback)))
    gui.messagebox.showerror = lambda title,text,**kwargs:failures.append(f"{title}: {text}")
    gui.messagebox.showinfo = lambda title,text,**kwargs:notices.append((title,text))
    gui.messagebox.askyesno = lambda *args,**kwargs:True
    app.report_callback_exception = lambda kind,value,tb:failures.append("".join(traceback.format_exception(kind,value,tb)))
    current_capture = [None]
    processed_audio = [None]
    started_at = [None]
    capture_sizes = []

    def screenshot(name):
        app.update_idletasks()
        x,y = app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height()),all_screens=True,
                       include_layered_windows=True).save(output/f"{name}.png")
        captures.append(name)
        print("CAPTURE",name,flush=True)

    def open_audio(path):
        app._page_buttons["library"].invoke()
        app._browser_navigate(path.parent)
        app._browser_selected = next(e for e in app._browser_visible_entries if e.path==path)
        app._browser_select()
        app._draw_browser_rows()

    def begin_capture():
        app._page_buttons["record"].invoke()
        (app.inline_start_button if app._maximized else app._focus_start_button).invoke()
        assert app._service.state == RecordingState.RECORDING
        current_capture[0] = app._service.current_output_path
        started_at[0] = app._started_at
        assert app.last_file.get() == str(current_capture[0])

    def assert_capture():
        assert app._service.state == RecordingState.RECORDING
        assert app._started_at == started_at[0]
        assert app.last_file.get() == str(current_capture[0])
        assert app.status.get() == "Recording"
        assert app._focus_start_button.cget("state") == "disabled"
        assert app._focus_stop_button.cget("state") == "normal"
        capture_sizes.append(current_capture[0].stat().st_size)

    def stop_capture():
        (app.inline_stop_button if app._maximized else app._focus_stop_button).invoke()

    def assert_saved():
        assert app._service.state == RecordingState.COMPLETED
        assert media_duration(current_capture[0]) > 0
        assert app._focus_start_button.cget("state") == "normal"

    def assert_automatic_name():
        job = next(j for j in app._job_store.list() if j.status == "completed")
        processed_audio[0] = job.audio_path
        assert job.audio_path.is_file()
        assert job.audio_path.stem == job.audio_path.parent.name == "revisao-do-cronograma"
        assert job.audio_path.read_bytes()[:4] == b"RIFF"
        assert not media[0].parent.exists()
        assert app._last_output == current_capture[0]
        check("Automatic folder/audio name keeps live recording and job links", True)

    def click_cancel():
        assert app._active_job_id is not None
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child,ctk.CTkButton): yield child
                else: yield from buttons(child)
        button = next(b for b in buttons(app._process_table.rows[0]) if getattr(b,"operation",None)=="cancel")
        assert button.cget("state")=="normal"
        button.invoke()

    steps = []
    def add(name,action,delay=450): steps.append((name,action,delay))
    def check(name,condition):
        assert condition,name
        checks.append(name)
    add("audio",lambda:open_audio(media[0]),800)
    add("estimate",lambda:check("Estimate visible before processing", "Processamento" in app._browser_estimate.cget("text")),0)
    add("capture-estimate",lambda:screenshot("focus-audio-estimate"),0)
    add("process",lambda:app._browser_process_button.invoke(),900)
    add("record-during-processing",begin_capture,900)
    add("record-running",assert_capture,0)
    add("capture-parallel",lambda:screenshot("focus-recording-and-processing"),0)
    add("compact",lambda:app.minimize_button.invoke(),400)
    add("check-compact",lambda:check("Compact controls keep capture independent",app._compact_status.get().startswith("GRAVANDO") and app.compact_stop_button.cget("state")=="normal"),0)
    add("capture-compact",lambda:screenshot("compact-recording-and-processing"),0)
    add("restore",lambda:app.compact_open_button.invoke(),400)
    add("wait-finish",lambda:None,4000)
    add("completion-preserves-capture",assert_capture,0)
    add("check-completed",lambda:check("Processing completed while capture continued",any(j.status=="completed" for j in app._job_store.list())),0)
    add("check-automatic-name",assert_automatic_name,0)
    add("processes",lambda:app._page_buttons["processing"].invoke())
    add("capture-list",lambda:screenshot("focus-process-table"),0)
    add("full",lambda:app.maximize_button.invoke(),700)
    add("capture-list-full",lambda:screenshot("fullscreen-process-table"),0)
    add("stop",stop_capture,900)
    add("saved",assert_saved,0)
    add("named-audio-full",lambda:open_audio(processed_audio[0]),800)
    add("capture-name-full",lambda:screenshot("fullscreen-automatic-name"),0)
    add("name-focus",lambda:app.maximize_button.invoke(),700)
    add("capture-name-focus",lambda:screenshot("focus-automatic-name"),0)
    add("return-full",lambda:app.maximize_button.invoke(),700)
    add("second-audio",lambda:open_audio(media[1]),800)
    add("process-second",lambda:app._browser_process_button.invoke(),800)
    add("record-again",begin_capture,900)
    add("processes",lambda:app._page_buttons["processing"].invoke())
    add("cancel-worker",click_cancel,1800)
    add("cancel-preserves-capture",assert_capture,0)
    add("cancelled",lambda:check("Cancelling processing preserves live capture",any(j.status=="cancelled" for j in app._job_store.list())),0)
    add("stop-second",stop_capture,900)
    add("saved-second",assert_saved,0)
    add("third-capture",begin_capture,800)
    add("low-memory",lambda:setattr(gui,"memory_headroom",lambda:100*1024**2),0)
    add("queue-low-memory",lambda:app._queue_pipeline(media[2],"pt","small","codex","meeting",reuse_source_folder=True),700)
    add("capture-safe",assert_capture,0)
    add("memory-queued",lambda:check("Low memory leaves task queued",any(j.status=="queued" and "memória" in j.stage for j in app._job_store.list())),0)
    add("writing-input",lambda:check("Current recording cannot be processed",not app._queue_pipeline(current_capture[0],"pt","small","codex","meeting")),0)
    add("memory-returned",lambda:setattr(gui,"memory_headroom",lambda:16*1024**3),0)
    add("stop-third",stop_capture,5000)
    add("saved-third",assert_saved,0)
    add("processes",lambda:app._page_buttons["processing"].invoke())
    add("clear-success",lambda:app._process_table.clear_button.invoke())
    add("clear-check",lambda:check("Clear keeps cancelled jobs and all media",not any(j.status=="completed" for j in app._job_store.list()) and any(j.status=="cancelled" for j in app._job_store.list()) and processed_audio[0].is_file()),0)
    add("capture-final",lambda:screenshot("fullscreen-after-clear"),0)

    def finish():
        if app._service and app._service.state == RecordingState.RECORDING:
            app._service.stop()
        report = dict(failures=failures,captures=captures,checks=checks,capture_sizes=capture_sizes,
                      method="Real GUI callbacks, RecordingService, streaming MP3 encoder and child-process pipeline; synthetic capture and AI upstreams.")
        (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("RESULT",json.dumps(report,ensure_ascii=False),flush=True)
        app.destroy()

    def next_step():
        if not steps or failures:
            finish()
            return
        name,action,delay = steps.pop(0)
        try:
            action()
            app.lift()
        except Exception:
            failures.append(f"{name}: {traceback.format_exc()}")
        app.after(delay,next_step)
    app.after(600,next_step)
    app.mainloop()
    temporary.cleanup()
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
