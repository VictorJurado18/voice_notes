from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gravador_audio.errors import RecordingError
from gravador_audio.paths import default_output_dir
from gravador_audio.recording import RecordingConfig, RecordingService, RecordingState
from gravador_audio.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig


class RecorderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Gravador de Audio")
        self.geometry("680x440")
        self.minsize(640, 420)
        self.configure(bg="#f3f4f6")

        self._service: RecordingService | None = None
        self._started_at: float | None = None
        self._last_output: Path | None = None
        self._stop_thread: threading.Thread | None = None

        self.output_dir = tk.StringVar(value=str(default_output_dir()))
        self.mode = tk.StringVar(value="both")
        self.status = tk.StringVar(value="Pronto para gravar")
        self.elapsed = tk.StringVar(value="00:00")
        self.last_file = tk.StringVar(value="-")

        self._build_ui()
        self._refresh_timer()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("App.TFrame", background="#f3f4f6")
        style.configure("Panel.TLabelframe", background="#f3f4f6")
        style.configure("Panel.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("App.TRadiobutton", background="#f3f4f6", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#f3f4f6", font=("Segoe UI", 11))
        style.configure("Timer.TLabel", background="#f3f4f6", font=("Segoe UI", 18, "bold"))

        container = ttk.Frame(self, padding=20, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            container,
            text="Gravador de Audio",
            font=("Segoe UI", 20, "bold"),
            background="#f3f4f6",
        )
        title.pack(anchor=tk.W)

        status_row = ttk.Frame(container)
        status_row.pack(fill=tk.X, pady=(16, 8))
        status_row.configure(style="App.TFrame")
        ttk.Label(status_row, textvariable=self.status, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.elapsed, style="Timer.TLabel").pack(side=tk.RIGHT)

        mode_frame = ttk.LabelFrame(container, text="Fonte de audio", padding=12, style="Panel.TLabelframe")
        mode_frame.pack(fill=tk.X, pady=8)
        ttk.Radiobutton(
            mode_frame,
            text="Microfone + audio do sistema",
            variable=self.mode,
            value="both",
            style="App.TRadiobutton",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            mode_frame,
            text="Somente microfone",
            variable=self.mode,
            value="microphone",
            style="App.TRadiobutton",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            mode_frame,
            text="Somente audio do sistema",
            variable=self.mode,
            value="system",
            style="App.TRadiobutton",
        ).pack(anchor=tk.W)

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
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            activeforeground="#111827",
            relief=tk.FLAT,
            padx=14,
            pady=8,
            width=14,
        ).pack(side=tk.LEFT, padx=(8, 0))

        buttons = tk.Frame(container, bg="#f3f4f6")
        buttons.pack(fill=tk.X, pady=(18, 10))
        self.start_button = tk.Button(
            buttons,
            text="Iniciar gravacao",
            command=self._start_recording,
            font=("Segoe UI", 13, "bold"),
            bg="#166534",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            disabledforeground="#d1d5db",
            relief=tk.FLAT,
            padx=18,
            pady=14,
            height=1,
        )
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = tk.Button(
            buttons,
            text="Parar gravacao",
            command=self._stop_recording,
            state=tk.DISABLED,
            font=("Segoe UI", 13, "bold"),
            bg="#991b1b",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            disabledforeground="#d1d5db",
            relief=tk.FLAT,
            padx=18,
            pady=14,
            height=1,
        )
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        last_file_frame = ttk.Frame(container, style="App.TFrame")
        last_file_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(
            last_file_frame,
            text="Ultimo arquivo:",
            font=("Segoe UI", 10, "bold"),
            background="#f3f4f6",
        ).pack(anchor=tk.W)
        ttk.Label(
            last_file_frame,
            textvariable=self.last_file,
            wraplength=620,
            background="#f3f4f6",
        ).pack(anchor=tk.W)

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
        messagebox.showerror("Erro ao finalizar", message)

    def _show_completed(self, output_path: Path) -> None:
        self.status.set("Gravacao finalizada")
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self._started_at = None
        self._last_output = output_path
        self.last_file.set(str(output_path))
        messagebox.showinfo("Gravacao finalizada", f"Arquivo salvo em:\n{output_path}")

    def _refresh_timer(self) -> None:
        if self._started_at is not None:
            seconds = int(time.monotonic() - self._started_at)
            minutes, remainder = divmod(seconds, 60)
            self.elapsed.set(f"{minutes:02d}:{remainder:02d}")
        else:
            self.elapsed.set("00:00")

        self.after(500, self._refresh_timer)

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
