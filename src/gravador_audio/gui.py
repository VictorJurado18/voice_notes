from __future__ import annotations

import shutil
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gravador_audio.errors import DiskSpaceError, RecordingError, TranscriptionError
from gravador_audio.paths import default_output_dir
from gravador_audio.recording import MIN_FREE_BYTES, RecordingConfig, RecordingService, RecordingState
from gravador_audio.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig

_LANGUAGES = [
    ("Portugues (BR)", "pt"),
    ("Ingles", "en"),
    ("Espanhol", "es"),
    ("Frances", "fr"),
    ("Automatico", None),
]
_LANG_LABELS = [label for label, _ in _LANGUAGES]
_LANG_CODES = {label: code for label, code in _LANGUAGES}


class RecorderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Gravador de Audio")
        self.geometry("680x560")
        self.minsize(640, 520)
        self.configure(bg="#f3f4f6")

        self._service: RecordingService | None = None
        self._started_at: float | None = None
        self._last_output: Path | None = None
        self._stop_thread: threading.Thread | None = None
        self._pipeline_thread: threading.Thread | None = None

        self.output_dir = tk.StringVar(value=str(default_output_dir()))
        self.mode = tk.StringVar(value="both")
        self.status = tk.StringVar(value="Pronto para gravar")
        self.elapsed = tk.StringVar(value="00:00")
        self.last_file = tk.StringVar(value="-")
        self.disk_warning = tk.StringVar(value="")
        self.pipeline_language = tk.StringVar(value=_LANG_LABELS[0])

        self._eq_smooth: list[float] = [0.0] * 16
        self._eq_peaks: list[float] = [0.0] * 16
        self._eq_peak_hold: list[int] = [0] * 16

        self._build_ui()
        self._refresh_timer()
        self._eq_timer()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("App.TFrame", background="#f3f4f6")
        style.configure("Panel.TLabelframe", background="#f3f4f6")
        style.configure("Panel.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("App.TRadiobutton", background="#f3f4f6", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#f3f4f6", font=("Segoe UI", 11))
        style.configure("Timer.TLabel", background="#f3f4f6", font=("Segoe UI", 18, "bold"))
        style.configure("DiskWarn.TLabel", background="#f3f4f6", font=("Segoe UI", 10), foreground="#b45309")
        style.configure("PipelineInfo.TLabel", background="#f3f4f6", font=("Segoe UI", 10), foreground="#1d4ed8")

        container = ttk.Frame(self, padding=20, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="Gravador de Audio",
            font=("Segoe UI", 20, "bold"),
            background="#f3f4f6",
        ).pack(anchor=tk.W)

        status_row = ttk.Frame(container, style="App.TFrame")
        status_row.pack(fill=tk.X, pady=(16, 4))
        ttk.Label(status_row, textvariable=self.status, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.elapsed, style="Timer.TLabel").pack(side=tk.RIGHT)

        self._eq_canvas = tk.Canvas(container, height=56, bg="#111827", highlightthickness=0)
        self._eq_canvas.pack(fill=tk.X, pady=(0, 8))
        self._eq_canvas.bind("<Configure>", lambda _: self._redraw_eq())

        mode_frame = ttk.LabelFrame(container, text="Fonte de audio", padding=12, style="Panel.TLabelframe")
        mode_frame.pack(fill=tk.X, pady=8)
        for text, value in [
            ("Microfone + audio do sistema", "both"),
            ("Somente microfone", "microphone"),
            ("Somente audio do sistema", "system"),
        ]:
            ttk.Radiobutton(mode_frame, text=text, variable=self.mode, value=value, style="App.TRadiobutton").pack(anchor=tk.W)

        output_frame = ttk.LabelFrame(container, text="Pasta de saida", padding=12, style="Panel.TLabelframe")
        output_frame.pack(fill=tk.X, pady=8)
        ttk.Entry(output_frame, textvariable=self.output_dir, font=("Segoe UI", 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=4
        )
        tk.Button(
            output_frame,
            text="Escolher pasta",
            command=self._choose_output_dir,
            font=("Segoe UI", 10, "bold"),
            bg="#e5e7eb", fg="#111827",
            activebackground="#d1d5db", activeforeground="#111827",
            relief=tk.FLAT, padx=14, pady=8, width=14,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Botões principais: Iniciar / Parar
        buttons = tk.Frame(container, bg="#f3f4f6")
        buttons.pack(fill=tk.X, pady=(18, 4))
        self.start_button = tk.Button(
            buttons, text="Iniciar gravacao", command=self._start_recording,
            font=("Segoe UI", 13, "bold"),
            bg="#166534", fg="#ffffff",
            activebackground="#15803d", activeforeground="#ffffff",
            disabledforeground="#d1d5db",
            relief=tk.FLAT, padx=18, pady=14, height=1,
        )
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = tk.Button(
            buttons, text="Parar gravacao", command=self._stop_recording,
            state=tk.DISABLED,
            font=("Segoe UI", 13, "bold"),
            bg="#991b1b", fg="#ffffff",
            activebackground="#b91c1c", activeforeground="#ffffff",
            disabledforeground="#d1d5db",
            relief=tk.FLAT, padx=18, pady=14, height=1,
        )
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        # Botão Processar MP3 + seletor de idioma (modo manual)
        process_row = tk.Frame(container, bg="#f3f4f6")
        process_row.pack(fill=tk.X, pady=(4, 10))
        self.process_button = tk.Button(
            process_row, text="Processar MP3 existente", command=self._process_existing_mp3,
            font=("Segoe UI", 10, "bold"),
            bg="#1e40af", fg="#ffffff",
            activebackground="#1d4ed8", activeforeground="#ffffff",
            disabledforeground="#d1d5db",
            relief=tk.FLAT, padx=12, pady=8,
        )
        self.process_button.pack(side=tk.LEFT)
        ttk.Label(process_row, text="  Idioma:", background="#f3f4f6", font=("Segoe UI", 10)).pack(side=tk.LEFT)
        ttk.Combobox(
            process_row,
            textvariable=self.pipeline_language,
            values=_LANG_LABELS,
            state="readonly",
            width=14,
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=(4, 0))

        # Barra de progresso do pipeline
        self.progressbar = ttk.Progressbar(container, mode="indeterminate", length=640)
        self.progressbar.pack(fill=tk.X, pady=(8, 0))

        # Último resultado
        last_frame = ttk.Frame(container, style="App.TFrame")
        last_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(last_frame, text="Ultimo resultado:", font=("Segoe UI", 10, "bold"), background="#f3f4f6").pack(anchor=tk.W)
        ttk.Label(last_frame, textvariable=self.last_file, wraplength=620, background="#f3f4f6").pack(anchor=tk.W)

        ttk.Label(
            container, textvariable=self.disk_warning,
            style="DiskWarn.TLabel", wraplength=620,
        ).pack(anchor=tk.W, pady=(6, 0))

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or ".")
        if selected:
            self.output_dir.set(selected)

    def _start_recording(self) -> None:
        try:
            mode = self.mode.get()
            backend_config = WindowsAudioBackendConfig(
                capture_microphone=mode in {"both", "microphone"},
                capture_system_audio=mode in {"both", "system"},
            )
            service = RecordingService(
                config=RecordingConfig(output_dir=Path(self.output_dir.get())),
                backend=WindowsAudioBackend(backend_config),
            )
            output_path = service.start()
        except DiskSpaceError as exc:
            messagebox.showerror("Espaco em disco insuficiente", str(exc))
            self.status.set("Espaco em disco insuficiente")
            return
        except RecordingError as exc:
            messagebox.showerror("Nao foi possivel iniciar", str(exc))
            self.status.set("Erro ao iniciar gravacao")
            return
        except OSError as exc:
            messagebox.showerror("Pasta invalida", str(exc))
            self.status.set("Erro na pasta de saida")
            return

        self._service = service
        self._started_at = time.monotonic()
        self._last_output = output_path
        self.status.set("Gravando")
        self.last_file.set(str(output_path))
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.process_button.configure(state=tk.DISABLED)

    def _stop_recording(self) -> None:
        if self._service is None or self._service.state != RecordingState.RECORDING:
            return
        self.stop_button.configure(state=tk.DISABLED)
        self.status.set("Finalizando...")
        self._stop_thread = threading.Thread(target=self._stop_recording_worker, daemon=True)
        self._stop_thread.start()

    def _stop_recording_worker(self) -> None:
        assert self._service is not None
        try:
            output_path = self._service.stop()
        except RecordingError as exc:
            self.after(0, self._show_stop_error, str(exc))
            return
        self.after(0, self._show_completed, output_path)

    def _show_stop_error(self, message: str) -> None:
        self.status.set("Erro ao finalizar")
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.NORMAL)
        messagebox.showerror("Erro ao finalizar", message)

    def _show_completed(self, output_path: Path) -> None:
        self.stop_button.configure(state=tk.DISABLED)
        self._started_at = None
        self._last_output = output_path
        self.last_file.set(str(output_path))
        self._start_pipeline(output_path, language="pt")

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _process_existing_mp3(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar arquivo MP3",
            filetypes=[("Arquivos MP3", "*.mp3"), ("Todos os arquivos", "*.*")],
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if not path:
            return
        mp3_path = Path(path)
        label = self.pipeline_language.get()
        lang_code = _LANG_CODES.get(label, "pt")

        self.start_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.DISABLED)
        self.status.set("Iniciando pipeline...")
        self.last_file.set(str(mp3_path))
        self._start_pipeline(mp3_path, language=lang_code)

    def _start_pipeline(self, mp3_path: Path, language: str | None) -> None:
        self.progressbar.start(12)

        def on_status(msg: str) -> None:
            self.after(0, self.status.set, msg)

        self._pipeline_thread = threading.Thread(
            target=self._pipeline_worker,
            args=(mp3_path, language or "pt", on_status),
            daemon=True,
        )
        self._pipeline_thread.start()

    def _pipeline_worker(self, mp3_path: Path, language: str, on_status: object) -> None:
        from gravador_audio.pipeline import run
        try:
            result = run(mp3_path, mp3_path.parent, language=language, on_status=on_status)
        except TranscriptionError as exc:
            self.after(0, self._on_pipeline_error, str(exc))
            return
        except Exception as exc:
            self.after(0, self._on_pipeline_error, str(exc))
            return
        self.after(0, self._on_pipeline_done, result)

    def _on_pipeline_done(self, result: object) -> None:
        from gravador_audio.pipeline import PipelineResult
        assert isinstance(result, PipelineResult)
        self.progressbar.stop()
        self.status.set(f"Pronto: {result.folder.name}")
        self.last_file.set(str(result.folder))
        self.start_button.configure(state=tk.NORMAL)
        self.process_button.configure(state=tk.NORMAL)

    def _on_pipeline_error(self, message: str) -> None:
        self.progressbar.stop()
        self.status.set("Erro no pipeline")
        self.start_button.configure(state=tk.NORMAL)
        self.process_button.configure(state=tk.NORMAL)
        messagebox.showerror("Erro no pipeline", message)

    # ── Equalizador ───────────────────────────────────────────────────────────

    def _eq_timer(self) -> None:
        recording = (
            self._service is not None
            and self._service.state == RecordingState.RECORDING
        )
        if recording:
            raw = self._service.eq_levels  # type: ignore[union-attr]
        else:
            raw = [0.0] * 16

        _DECAY = 0.75
        _ATTACK = 0.55
        _PEAK_HOLD = 8

        for i in range(16):
            target = raw[i]
            if target > self._eq_smooth[i]:
                self._eq_smooth[i] = self._eq_smooth[i] * (1 - _ATTACK) + target * _ATTACK
            else:
                self._eq_smooth[i] *= _DECAY

            if self._eq_smooth[i] >= self._eq_peaks[i]:
                self._eq_peaks[i] = self._eq_smooth[i]
                self._eq_peak_hold[i] = _PEAK_HOLD
            elif self._eq_peak_hold[i] > 0:
                self._eq_peak_hold[i] -= 1
            else:
                self._eq_peaks[i] = max(0.0, self._eq_peaks[i] - 0.04)

        self._redraw_eq()
        self.after(80, self._eq_timer)

    def _redraw_eq(self) -> None:
        c = self._eq_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2 or h < 2:
            return

        n = 16
        gap = 3
        bar_w = max(4, (w - gap * (n + 1)) // n)
        max_h = h - 6

        for i in range(n):
            x0 = gap + i * (bar_w + gap)
            x1 = x0 + bar_w
            level = self._eq_smooth[i]
            bar_h = int(level * max_h)

            # Barra principal em 3 faixas de cor
            if bar_h > 0:
                # Verde (0–60%)
                green_h = min(bar_h, int(max_h * 0.60))
                c.create_rectangle(x0, h - green_h, x1, h, fill="#22c55e", outline="")

                # Amarelo (60–85%)
                if bar_h > int(max_h * 0.60):
                    yellow_h = min(bar_h - int(max_h * 0.60), int(max_h * 0.25))
                    y_bot = h - int(max_h * 0.60)
                    c.create_rectangle(x0, y_bot - yellow_h, x1, y_bot, fill="#eab308", outline="")

                # Vermelho (85–100%)
                if bar_h > int(max_h * 0.85):
                    red_h = bar_h - int(max_h * 0.85)
                    y_bot = h - int(max_h * 0.85)
                    c.create_rectangle(x0, y_bot - red_h, x1, y_bot, fill="#ef4444", outline="")

            # Pico (linha branca)
            peak_y = h - int(self._eq_peaks[i] * max_h) - 1
            if self._eq_peaks[i] > 0.02:
                c.create_rectangle(x0, peak_y, x1, peak_y + 2, fill="#ffffff", outline="")

    # ── Timer / disco ─────────────────────────────────────────────────────────

    def _refresh_timer(self) -> None:
        if self._started_at is not None:
            seconds = int(time.monotonic() - self._started_at)
            minutes, remainder = divmod(seconds, 60)
            self.elapsed.set(f"{minutes:02d}:{remainder:02d}")
        else:
            self.elapsed.set("00:00")
        self._check_disk_space()
        self.after(500, self._refresh_timer)

    def _check_disk_space(self) -> None:
        if self._service is None or self._service.state != RecordingState.RECORDING:
            self.disk_warning.set("")
            return
        if self._last_output is None:
            return
        try:
            free = shutil.disk_usage(self._last_output.parent).free
        except OSError:
            return
        if free < MIN_FREE_BYTES:
            free_mb = free // (1024 * 1024)
            self.disk_warning.set(f"Aviso: espaco em disco baixo — {free_mb} MB disponiveis.")
        else:
            self.disk_warning.set("")

    def _on_close(self) -> None:
        if self._service is not None and self._service.state == RecordingState.RECORDING:
            should_close = messagebox.askyesno(
                "Gravacao em andamento",
                "Existe uma gravacao em andamento. Deseja parar e fechar?",
            )
            if not should_close:
                return
            try:
                self._service.stop()
            except RecordingError as exc:
                messagebox.showerror("Erro ao finalizar", str(exc))
                return
        self.destroy()


def main() -> int:
    app = RecorderApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
