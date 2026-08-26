from __future__ import annotations

import shutil
import subprocess
import threading
import time
import tkinter as tk
import argparse
import os
import re
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from record_transcript_resume.errors import DiskSpaceError, RecordingError
from record_transcript_resume.paths import default_output_dir
from record_transcript_resume.recording import MIN_FREE_BYTES, RecordingConfig, RecordingService, RecordingState
from record_transcript_resume.transcription import available_models
from record_transcript_resume.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig
from record_transcript_resume.jobs import JobStore, ProcessingJob
from record_transcript_resume.library import LibraryItem, discover_recordings
from record_transcript_resume.synthesis import SUMMARY_TEMPLATE_LABELS
from record_transcript_resume.windows_process import hidden_process_kwargs

def _log_hint() -> str:
    from record_transcript_resume.log import _log_path
    return f"Full log at: {_log_path()}"


_LANGUAGES = [
    ("Portuguese (BR)", "pt"),
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("Auto-detect", None),
]
_LANG_LABELS = [label for label, _ in _LANGUAGES]
_LANG_CODES = {label: code for label, code in _LANGUAGES}
_SUMMARY_PROVIDERS = [("Codex", "codex"), ("Claude Code", "claude"), ("API por token", "api")]
_SUMMARY_PROVIDER_CODES = dict(_SUMMARY_PROVIDERS)
_SUMMARY_PROVIDER_LABELS = [label for label, _ in _SUMMARY_PROVIDERS]
_SUMMARY_TEMPLATE_CODES = {label: code for code, label in SUMMARY_TEMPLATE_LABELS.items()}
_SUMMARY_TEMPLATE_LABELS = list(_SUMMARY_TEMPLATE_CODES)
_WHISPER_MODEL_DESCRIPTIONS = {
    "tiny": "Mais rápido · menor precisão",
    "base": "Rápido · qualidade básica",
    "small": "Equilibrado · recomendado",
    "medium": "Mais preciso · mais lento",
    "large-v3": "Máxima precisão · mais pesado",
}
_PROCESSING_PROFILES = {
    "Personalizado": (None, None, None),
    "Reunião de trabalho": ("Reunião", "small", True),
    "Aula": ("Aula", "medium", False),
    "Entrevista": ("Entrevista", "medium", True),
    "Call comercial": ("Call comercial", "small", True),
    "Estudo": ("Estudo", "medium", False),
    "Plano de ação": ("Plano de ação", "small", True),
}
_RECORDING_OUTPUT_OPTIONS = (
    ("Salvar só o áudio", "audio"),
    ("Áudio + transcrição", "transcription"),
    ("Áudio + transcrição + resumo", "both"),
)
_RECORDING_OUTPUT_LABELS = {value: label for label, value in _RECORDING_OUTPUT_OPTIONS}
_RECORDING_OUTPUT_CODES = {label: value for label, value in _RECORDING_OUTPUT_OPTIONS}
_PIX_KEY = "f608aca6-81f0-4c41-a77f-347777f75b0e"


def _saved_huggingface_token() -> str:
    try:
        import keyring
        return keyring.get_password("Voice Notes", "huggingface-token") or ""
    except Exception:
        return os.environ.get("HF_TOKEN", "")


def _diarization_enabled_by_default(token: str) -> bool:
    """Enable speaker separation on launch whenever an authorized token exists."""
    return bool(token.strip())


_COLORS = {
    "transparent": "#010203",
    "bg": "#080C16",
    "surface": "#101827",
    "surface_alt": "#162136",
    "border": "#283754",
    "text": "#F6F8FF",
    "muted": "#AAB8D4",
    "brand": "#D3DCF3",
    "brand_muted": "#8FA1C9",
    # The primary action keeps enough contrast with its white label in both
    # the resting and hovered states.
    "accent": "#6656D8",
    "accent_hover": "#7162DD",
    "success": "#55D6A0",
    "success_hover": "#70E4B4",
    "danger": "#F17A91",
    "danger_hover": "#FF92A6",
    "warning": "#F5B942",
}


def _asset_path(filename: str) -> Path:
    """Return a bundled asset path in development and in the Windows build."""
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "assets" / filename


class _TrayController:
    """Owns the Windows notification-area icon without coupling Tk to pystray."""

    def __init__(self, app: "RecorderApp") -> None:
        self._app = app
        self._icon: object | None = None

    @staticmethod
    def _create_image(image_module: object, draw_module: object) -> object:
        """Load the application mark, with a code-drawn fallback for resilience."""
        icon_path = _asset_path("voice-notes.png")
        if icon_path.is_file():
            try:
                image = image_module.open(icon_path).convert("RGBA")
                resampling = getattr(image_module, "Resampling", image_module).LANCZOS
                return image.resize((64, 64), resampling)
            except Exception:
                pass

        image = image_module.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = draw_module.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=_COLORS["accent"])
        for x, top, bottom in ((19, 27, 37), (27, 21, 43), (35, 25, 39), (43, 29, 35)):
            draw.rounded_rectangle((x, top, x + 5, bottom), radius=2, fill="#FFFFFF")
        return image

    def start(self) -> bool:
        """Start the tray icon on its own event loop. Returns False if unavailable."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            icon = pystray.Icon(
                "voice_notes",
                self._create_image(Image, ImageDraw),
                "Voice Notes",
                menu=pystray.Menu(
                    pystray.MenuItem("Mostrar widget", self._show, default=True),
                    pystray.MenuItem("Ocultar widget", self._hide),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Encerrar", self._quit),
                ),
            )
            self._icon = icon
            threading.Thread(
                target=icon.run,
                name="voice-notes-tray",
                daemon=True,
            ).start()
            return True
        except Exception as exc:
            from record_transcript_resume.log import log

            log(f"GUI: notificacao na bandeja indisponivel: {exc}")
            self._icon = None
            return False

    def _show(self, *_: object) -> None:
        self._app.after(0, self._app._show_widget)

    def _hide(self, *_: object) -> None:
        self._app.after(0, self._app._hide_to_tray)

    def _quit(self, *_: object) -> None:
        self._app.after(0, self._app._on_close)

    def notify(self, title: str, message: str) -> None:
        """Show best-effort feedback without requiring the widget to be visible."""
        icon = self._icon
        if icon is None:
            return
        try:
            icon.notify(message, title)  # type: ignore[attr-defined]
        except Exception:
            # Windows can reject notification requests while Explorer is restarting.
            # The tray icon itself remains the reliable way to restore the widget.
            pass

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                # The application is already closing; the icon will disappear
                # with the process if the notification API has stopped first.
                pass


class RecorderApp(ctk.CTk):
    def __init__(
        self,
        widget_mode: bool = True,
        *,
        start_hidden: bool = False,
        enable_tray: bool = True,
    ) -> None:
        super().__init__()
        self.title("Voice Notes (Beta)")
        try:
            self.iconbitmap(default=str(_asset_path("voice-notes.ico")))
        except tk.TclError:
            # The icon is optional when running the source on a non-Windows host.
            pass
        # A borderless widget does not receive the native Windows resize frame.
        # Its lower-right corner is handled directly by the root window.
        self._min_widget_width = 520
        self._min_widget_height = 560
        self._active_min_width = self._min_widget_width
        self._active_min_height = self._min_widget_height
        # Keep the primary workflow fully visible on a typical desktop while
        # preserving enough room for the taskbar on smaller displays.
        self._main_widget_height = min(658, max(self._min_widget_height, self.winfo_screenheight() - 200))
        self._preferred_widget_width = 560
        self._user_resized_window = False
        self._widget_scale = 1.0
        self._minimum_widget_scale = 0.85
        self._maximum_widget_scale = 1.35
        self._resize_hit_size = 28
        self._resize_apply_after: str | None = None
        self._pending_resize_geometry: tuple[int, int, float] | None = None
        self._round_region_after: str | None = None
        self._content_scrollbar_after: str | None = None
        self.geometry(f"560x{self._main_widget_height}")
        self.minsize(self._min_widget_width, self._min_widget_height)
        # Do not rely on chroma-key transparency for the outer silhouette.
        # It leaks a rectangular background below rounded CTk frames on resize.
        self.configure(fg_color=_COLORS["surface"])

        self._service: RecordingService | None = None
        self._started_at: float | None = None
        self._last_output: Path | None = None
        self._stop_thread: threading.Thread | None = None
        self._pipeline_thread: threading.Thread | None = None
        self._pending_jobs: list[ProcessingJob] = []
        self._job_store = JobStore()
        self._library_items: list[LibraryItem] = []
        self._library_open = False
        self._library_editing = False
        self._library_document_window: ctk.CTkToplevel | None = None
        self._youtube_open = False
        self._widget_mode = False
        self._restore_borderless_on_map = False
        self._drag_active = False
        self._resize_active = False
        self._settings_open = False
        self._compact_mode = False
        self._full_widget_geometry = ""
        self._full_widget_scale = 1.0
        self._compact_position: tuple[int, int] | None = None
        self._compact_drag_active = False
        self._compact_drag_moved = False
        self._compact_width = 468
        self._compact_height = 64
        self._provider_setup_running = False
        self._provider_setup_attempted = False
        self._provider_status_check_running = False
        self._update_check_running = False
        self._pix_support_window: ctk.CTkToplevel | None = None
        self._tray = _TrayController(self)
        self._tray_available = False

        self.output_dir = tk.StringVar(value=str(default_output_dir()))
        self.mode = tk.StringVar(value="both")
        self.status = tk.StringVar(value="Pronto para gravar")
        self.elapsed = tk.StringVar(value="00:00")
        self._compact_status = tk.StringVar(value="PRONTO")
        self.recording_limit_value = tk.StringVar(value="")
        self.recording_limit_unit = tk.StringVar(value="minutos")
        self.recording_limit_hint = tk.StringVar(value="Sem parada automática")
        self.recording_output_mode = tk.StringVar(value="both")
        self.recording_output_choice = tk.StringVar(value=_RECORDING_OUTPUT_LABELS["both"])
        self.recording_output_hint = tk.StringVar(
            value="O áudio é sempre salvo antes do processamento."
        )
        self._recording_deadline: float | None = None
        self.last_file = tk.StringVar(value="-")
        self.disk_warning = tk.StringVar(value="")
        self.pipeline_language = tk.StringVar(value=_LANG_LABELS[0])
        self._available_models = available_models()
        self.pipeline_model = tk.StringVar(value="small")
        self.model_description = tk.StringVar(value=_WHISPER_MODEL_DESCRIPTIONS["small"])
        self.youtube_url = tk.StringVar(value="")
        self.youtube_mode = tk.StringVar(value="Transcrição e resumo")
        self.youtube_hint = tk.StringVar(value="Use somente conteúdo próprio ou autorizado.")
        self.summary_provider = tk.StringVar(value="Codex")
        from record_transcript_resume.api_provider import load_config
        api_config = load_config()
        self.api_provider_name = tk.StringVar(value=api_config.name)
        self.api_protocol = tk.StringVar(value=api_config.protocol)
        self.api_base_url = tk.StringVar(value=api_config.base_url)
        self.api_model = tk.StringVar(value=api_config.model)
        self.api_auth_header = tk.StringVar(value=api_config.auth_header)
        self.api_auth_prefix = tk.StringVar(value=api_config.auth_prefix)
        self.api_response_path = tk.StringVar(value=api_config.response_path)
        self.api_request_template_default = api_config.request_template
        self.api_token = tk.StringVar(value="")
        self._api_provider_open = False
        self._api_advanced_open = False
        self.summary_template = tk.StringVar(value="Reunião")
        self.processing_profile = tk.StringVar(value="Personalizado")
        saved_huggingface_token = _saved_huggingface_token()
        self.huggingface_token = tk.StringVar(value=saved_huggingface_token)
        # Once configured, speaker separation should be the normal behavior.
        # The checkbox remains available for users who deliberately want to
        # skip this extra processing for one recording.
        self.diarize_speakers = tk.BooleanVar(
            value=_diarization_enabled_by_default(saved_huggingface_token),
        )
        self.provider_hint = tk.StringVar()
        self.update_hint = tk.StringVar(value="Verifique se há uma nova versão do repositório.")
        self.device_info_text = tk.StringVar(value="")
        self.library_search = tk.StringVar(value="")
        self.library_detail = tk.StringVar(value="Selecione uma gravação para ver as ações disponíveis.")
        self.queue_hint = tk.StringVar(value="Fila vazia")
        self.import_text_title = tk.StringVar(value="")
        self.library_editor_title = tk.StringVar(value="")
        self._text_import_open = False
        self._editor_document_path: Path | None = None
        self._editor_is_transcript = False
        self._editor_dirty = False
        self._editor_highlight_after: str | None = None
        self.editor_save_state = tk.StringVar(value="Salvo")
        self.editor_save_state_label: ctk.CTkLabel | None = None

        self._eq_smooth: list[float] = [0.0] * 16
        self._eq_peaks: list[float] = [0.0] * 16
        self._eq_peak_hold: list[int] = [0] * 16

        self._build_ui()
        self.summary_provider.trace_add("write", self._on_provider_changed)
        self.pipeline_model.trace_add("write", self._on_model_changed)
        self.processing_profile.trace_add("write", self._on_processing_profile_changed)
        self.recording_output_mode.trace_add("write", self._on_recording_output_mode_changed)
        self._set_widget_mode(True)
        self.after_idle(self._schedule_widget_rounding)
        self._refresh_provider_hint()
        self._refresh_timer()
        self._eq_timer()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Map>", self._restore_borderless_after_minimize, add="+")
        # A remap can discard the native clipping region on some Windows/DPI
        # combinations, so restore it whenever the shell becomes visible.
        self.bind("<Map>", lambda _event: self._schedule_widget_rounding(), add="+")
        self.bind("<Configure>", lambda _event: self._schedule_widget_rounding(), add="+")
        if enable_tray:
            self._tray_available = self._tray.start()
        if start_hidden and self._tray_available:
            # Aguarda o primeiro ciclo do Tk para não mostrar um flash da janela
            # quando o atalho de inicialização do Windows for executado.
            self.after(120, self._hide_to_tray)
        # The installer sets up both providers before starting the app. If that
        # step was interrupted, recover it in the background after first paint.
        self.after(700, self._check_provider_login)
        self.after(1600, self._check_for_updates)
        self.after(1000, self._resume_interrupted_jobs)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background=_COLORS["bg"])
        style.configure("Panel.TLabelframe", background=_COLORS["surface"], foreground=_COLORS["text"], bordercolor=_COLORS["border"], relief="flat")
        style.configure("Panel.TLabelframe.Label", background=_COLORS["surface"], foreground=_COLORS["text"], font=("Segoe UI", 10, "bold"))
        style.configure("App.TRadiobutton", background=_COLORS["surface"], foreground=_COLORS["text"], font=("Segoe UI", 10))
        style.map("App.TRadiobutton", background=[("active", _COLORS["surface"])], foreground=[("active", _COLORS["text"])])
        style.configure("Status.TLabel", background=_COLORS["bg"], foreground=_COLORS["text"], font=("Segoe UI", 12, "bold"))
        style.configure("Timer.TLabel", background=_COLORS["bg"], foreground=_COLORS["text"], font=("Cascadia Mono", 23, "bold"))
        style.configure("DiskWarn.TLabel", background=_COLORS["bg"], font=("Segoe UI", 10), foreground=_COLORS["warning"])
        style.configure("PipelineInfo.TLabel", background=_COLORS["bg"], font=("Segoe UI", 10, "bold"), foreground="#BFC7FF")
        style.configure("TEntry", fieldbackground=_COLORS["surface_alt"], foreground=_COLORS["text"], bordercolor=_COLORS["border"], insertcolor=_COLORS["text"])
        style.configure("TCombobox", fieldbackground=_COLORS["surface_alt"], background=_COLORS["surface_alt"], foreground=_COLORS["text"], arrowcolor=_COLORS["muted"], bordercolor=_COLORS["border"], padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", _COLORS["surface_alt"])], foreground=[("readonly", _COLORS["text"])])
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=_COLORS["surface_alt"], background=_COLORS["accent"], bordercolor=_COLORS["surface_alt"])

        container = ctk.CTkFrame(
            self,
            fg_color=_COLORS["surface"],
            corner_radius=22,
        )
        container.pack(fill=tk.BOTH, expand=True)
        self._window_surface = container

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill=tk.X, padx=20, pady=(16, 8))
        self._header = header
        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        eyebrow_row = ctk.CTkFrame(title_block, fg_color="transparent")
        eyebrow_row.pack(anchor=tk.W)
        eyebrow = ctk.CTkLabel(
            eyebrow_row, text="Voice", font=("Segoe UI", 15, "bold"),
            text_color="#EEF3FF", anchor="w",
        )
        eyebrow.pack(side=tk.LEFT)
        notes_label = ctk.CTkLabel(
            eyebrow_row, text="Notes", font=("Segoe UI", 15, "bold"),
            text_color="#A99AF4", anchor="w",
        )
        notes_label.pack(side=tk.LEFT, padx=(4, 0))
        beta_label = ctk.CTkLabel(
            eyebrow_row, text="BETA", font=("Segoe UI", 8, "bold"),
            text_color="#B7AAFF", fg_color="#29254B", corner_radius=6,
            width=38, height=20,
        )
        beta_label.pack(side=tk.LEFT, padx=(8, 0))
        drag_label = ctk.CTkLabel(
            eyebrow_row, text="· mover", font=("Segoe UI", 9),
            text_color=_COLORS["brand_muted"], anchor="w",
        )
        drag_label.pack(side=tk.LEFT, padx=(7, 0))
        title = ctk.CTkLabel(
            title_block, text="Gravador", font=("Segoe UI", 20, "bold"),
            text_color=_COLORS["text"], anchor="w",
        )
        title.pack(anchor=tk.W, pady=(8, 6))
        self._header_title = title
        drag_hint = ctk.CTkLabel(title_block, text="", height=1, anchor="w")
        drag_hint.pack(anchor=tk.W)
        self._header_drag_hint = drag_hint
        self._make_draggable(
            header, title_block, eyebrow_row, eyebrow, notes_label, beta_label,
            drag_label, title, drag_hint,
        )

        window_controls = ctk.CTkFrame(header, fg_color="transparent")
        window_controls.pack(side=tk.RIGHT, anchor=tk.N)
        self.close_button = ctk.CTkButton(
            window_controls, text="Encerrar", command=self._on_close, width=64, height=32,
            corner_radius=10, fg_color="transparent", hover_color="#3A1D2A",
            text_color=_COLORS["muted"], font=("Segoe UI", 10, "bold"),
        )
        self.close_button.pack(side=tk.RIGHT, padx=(6, 0))
        self.hide_button = ctk.CTkButton(
            window_controls, text="Ocultar", command=self._hide_to_tray, width=64, height=32,
            corner_radius=10, fg_color="transparent", hover_color=_COLORS["surface_alt"],
            text_color=_COLORS["muted"], font=("Segoe UI", 10, "bold"),
        )
        self.hide_button.pack(side=tk.RIGHT, padx=(4, 0))
        self.minimize_button = ctk.CTkButton(
            window_controls, text="Minimizar", command=self._minimize_widget, width=76, height=32,
            corner_radius=10, fg_color="transparent", hover_color=_COLORS["surface_alt"],
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.minimize_button.pack(side=tk.RIGHT, padx=(4, 0))
        navigation = ctk.CTkFrame(container, fg_color="#0D1525", corner_radius=10)
        navigation.pack(fill=tk.X, padx=20, pady=(4, 8))
        self._page_buttons: dict[str, ctk.CTkButton] = {}
        for page, label, command in [
            ("record", "Gravar", self._show_recording_page),
            ("file", "Arquivo", self._show_file_import),
            ("youtube", "YouTube", self._toggle_youtube),
            ("library", "Biblioteca", self._toggle_library),
            ("settings", "Ajustes", self._toggle_settings),
        ]:
            button = ctk.CTkButton(
                navigation, text=label, command=command, width=78, height=30, corner_radius=8,
                fg_color="transparent", hover_color="#22324F", text_color=_COLORS["muted"],
                font=("Segoe UI", 10, "bold"),
            )
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
            self._page_buttons[page] = button
        self.record_page_button = self._page_buttons["record"]
        self.file_page_button = self._page_buttons["file"]
        self.youtube_page_button = self._page_buttons["youtube"]
        self.library_button = self._page_buttons["library"]
        self.settings_button = self._page_buttons["settings"]

        # Pages with many controls must scroll inside the widget instead of
        # forcing the borderless window beyond the visible work area.  The
        # header and navigation remain fixed, so switching destinations never
        # hides the window's lower rounded corners below the screen edge.
        content = ctk.CTkScrollableFrame(
            container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_fg_color="transparent",
            scrollbar_button_color="#263550",
            scrollbar_button_hover_color="#34476B",
        )
        content.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 4))
        content._parent_canvas.bind(
            "<Configure>",
            lambda _event: self._schedule_content_scrollbar(),
            add="+",
        )

        status_card = ctk.CTkFrame(content, fg_color=_COLORS["surface_alt"], corner_radius=16)
        status_card.pack(fill=tk.X, padx=20, pady=(4, 8))
        status_row = ctk.CTkFrame(status_card, fg_color="transparent")
        status_row.pack(fill=tk.X, padx=14, pady=(10, 0))
        ctk.CTkLabel(
            status_row, text="STATUS", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            status_row, textvariable=self.elapsed, font=("Cascadia Mono", 21, "bold"),
            text_color=_COLORS["text"], anchor="e",
        ).pack(side=tk.RIGHT)
        ctk.CTkLabel(
            status_card, textvariable=self.status, font=("Segoe UI", 14, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(1, 3))
        ctk.CTkLabel(
            status_card, textvariable=self.recording_limit_hint, font=("Segoe UI", 9),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(0, 6))

        meter_card = ctk.CTkFrame(status_card, fg_color="#0C1423", corner_radius=10)
        meter_card.pack(fill=tk.X, padx=12, pady=(0, 10))
        self._eq_canvas = tk.Canvas(
            meter_card, height=22, bg="#0C1423", highlightthickness=0, bd=0,
        )
        self._eq_canvas.pack(fill=tk.X, padx=8, pady=3)
        self._eq_canvas.bind("<Configure>", lambda _: self._redraw_eq())

        self.device_info_label = ctk.CTkLabel(
            content, textvariable=self.device_info_text, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w",
        )

        self._container = content
        capture_card = ctk.CTkFrame(content, fg_color="#141E32", corner_radius=14)
        capture_card.pack(fill=tk.X, padx=20, pady=(8, 8))
        source_row = ctk.CTkFrame(capture_card, fg_color="transparent")
        source_row.pack(fill=tk.X, padx=14, pady=(10, 8))
        self._source_buttons: list[ctk.CTkRadioButton] = []
        for text, value in [
            ("Microfone + sistema", "both"),
            ("Microfone", "microphone"),
            ("Sistema", "system"),
        ]:
            button = ctk.CTkRadioButton(
                source_row, text=text, variable=self.mode, value=value,
                font=("Segoe UI", 10, "bold"), text_color=_COLORS["text"],
                fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
                border_color="#5C6D91", radiobutton_width=18, radiobutton_height=18,
            )
            button.pack(side=tk.LEFT, padx=(2, 16))
            self._source_buttons.append(button)

        separator = ctk.CTkFrame(capture_card, height=1, fg_color="#253552")
        separator.pack(fill=tk.X, padx=14)
        output_row = ctk.CTkFrame(capture_card, fg_color="transparent")
        output_row.pack(fill=tk.X, padx=14, pady=(8, 8))
        ctk.CTkLabel(
            output_row, text="SALVAR EM", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], width=100, anchor="w",
        ).pack(side=tk.LEFT)
        self.output_entry = ctk.CTkEntry(
            output_row, textvariable=self.output_dir, height=34, corner_radius=9,
            fg_color="#0D1525", border_color="#2A3A58", text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.output_browse_button = ctk.CTkButton(
            output_row, text="Alterar", command=self._choose_output_dir, width=70, height=34,
            corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.output_browse_button.pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkFrame(capture_card, height=1, fg_color="#253552").pack(fill=tk.X, padx=14)
        timer_row = ctk.CTkFrame(capture_card, fg_color="transparent")
        timer_row.pack(fill=tk.X, padx=14, pady=(8, 8))
        ctk.CTkLabel(
            timer_row, text="PARAR APÓS", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], width=100, anchor="w",
        ).pack(side=tk.LEFT)
        self.recording_limit_entry = ctk.CTkEntry(
            timer_row, textvariable=self.recording_limit_value, placeholder_text="Sem limite",
            width=98, height=34, corner_radius=9, fg_color="#0D1525",
            border_color="#2A3A58", text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.recording_limit_entry.pack(side=tk.LEFT)
        self.recording_limit_selector = ctk.CTkComboBox(
            timer_row, variable=self.recording_limit_unit, values=["minutos", "horas"],
            state="readonly", width=106, height=34, corner_radius=9, fg_color="#0D1525",
            border_color="#2A3A58", button_color="#263550", button_hover_color="#34476B",
            text_color=_COLORS["text"], dropdown_fg_color="#162136",
            dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.recording_limit_selector.pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkFrame(capture_card, height=1, fg_color="#253552").pack(fill=tk.X, padx=14)
        recording_output_row = ctk.CTkFrame(capture_card, fg_color="transparent")
        recording_output_row.pack(fill=tk.X, padx=14, pady=(8, 8))
        ctk.CTkLabel(
            recording_output_row, text="DEPOIS DE PARAR", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], width=100, anchor="w",
        ).pack(side=tk.LEFT)
        self.recording_output_selector = ctk.CTkComboBox(
            recording_output_row, variable=self.recording_output_choice,
            values=[label for label, _value in _RECORDING_OUTPUT_OPTIONS], command=self._on_recording_output_choice,
            state="readonly", height=34, corner_radius=9, fg_color="#0D1525",
            border_color="#2A3A58", button_color="#263550", button_hover_color="#34476B",
            text_color=_COLORS["text"], dropdown_fg_color="#162136",
            dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.recording_output_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkFrame(capture_card, height=1, fg_color="#253552").pack(fill=tk.X, padx=14)
        preferences_row = ctk.CTkFrame(capture_card, fg_color="transparent")
        preferences_row.pack(fill=tk.X, padx=14, pady=(8, 10))
        profile_field = ctk.CTkFrame(preferences_row, fg_color="transparent")
        profile_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(
            profile_field, text="PERFIL", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.profile_selector = ctk.CTkComboBox(
            profile_field, variable=self.processing_profile, values=list(_PROCESSING_PROFILES),
            state="readonly", height=34, corner_radius=9,
            fg_color="#0D1525", border_color="#2A3A58", button_color="#263550",
            button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.profile_selector.pack(fill=tk.X)
        summary_format_field = ctk.CTkFrame(preferences_row, fg_color="transparent")
        summary_format_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        ctk.CTkLabel(
            summary_format_field, text="FORMATO DO RESUMO", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.template_selector = ctk.CTkComboBox(
            summary_format_field, variable=self.summary_template, values=_SUMMARY_TEMPLATE_LABELS,
            state="readonly", height=34, corner_radius=9,
            fg_color="#0D1525", border_color="#2A3A58", button_color="#263550",
            button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.template_selector.pack(fill=tk.X)

        # Botões principais: uma ação primária e uma ação de parada secundária.
        # Keep the recording controls outside the scrolling page area.  The
        # primary action remains visible even when the recording preferences
        # need more vertical space than a compact display can offer.
        self._buttons = ctk.CTkFrame(container, fg_color="transparent")
        self._buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
        self.start_button = ctk.CTkButton(
            self._buttons, text="Iniciar gravação", command=self._start_recording,
            height=42, corner_radius=13, fg_color=_COLORS["accent"],
            hover_color=_COLORS["accent_hover"], text_color="#FFFFFF",
            font=("Segoe UI", 14, "bold"),
        )
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = ctk.CTkButton(
            self._buttons, text="Parar", command=self._stop_recording,
            state=tk.DISABLED, width=90, height=42, corner_radius=13,
            fg_color="#27344D", hover_color="#3A4865", border_width=1,
            border_color=_COLORS["border"], text_color=_COLORS["text"],
            font=("Segoe UI", 13, "bold"),
        )
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))

        # Configurações ocupam a mesma cápsula, preservando o cabeçalho e os
        # controles de janela para que a navegação nunca "desapareça".
        self._settings_panel = ctk.CTkFrame(
            content, fg_color="#0C1423", corner_radius=16,
        )
        ctk.CTkLabel(
            self._settings_panel, text="CONFIGURAÇÕES", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["accent"], anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(18, 2))
        ctk.CTkLabel(
            self._settings_panel, text="Preferências usadas na próxima gravação ou importação.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(0, 8))
        settings_nav = ctk.CTkFrame(self._settings_panel, fg_color="#111A2C", corner_radius=9)
        settings_nav.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._settings_section_buttons: dict[str, ctk.CTkButton] = {}
        for section, label in [("provider", "Provider e API"), ("transcription", "Transcrição"), ("speakers", "Falantes")]:
            button = ctk.CTkButton(
                settings_nav, text=label, command=lambda key=section: self._show_settings_section(key),
                width=110, height=32, corner_radius=7, fg_color="transparent", hover_color="#22324F",
                text_color=_COLORS["muted"], font=("Segoe UI", 9, "bold"),
            )
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
            self._settings_section_buttons[section] = button
        self._settings_sections = {
            key: ctk.CTkFrame(self._settings_panel, fg_color="transparent")
            for key in ("provider", "transcription", "speakers")
        }

        def settings_card(parent: tk.Misc, title_text: str, detail: str) -> ctk.CTkFrame:
            card = ctk.CTkFrame(parent, fg_color="#111A2C", corner_radius=12)
            card.pack(fill=tk.X, padx=14, pady=(0, 12))
            ctk.CTkLabel(card, text=title_text, font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=14, pady=(12, 0))
            ctk.CTkLabel(
                card, text=detail, font=("Segoe UI", 10), text_color=_COLORS["muted"],
                anchor="w", justify=tk.LEFT, wraplength=448,
            ).pack(fill=tk.X, padx=14, pady=(2, 10))
            return card

        processing_card = settings_card(self._settings_sections["provider"], "Resumo", "Escolha quem cria o resumo.")
        provider_row = ctk.CTkFrame(processing_card, fg_color="transparent")
        provider_row.pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkLabel(
            provider_row, text="Provider do resumo", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(side=tk.LEFT)
        self.provider_selector = ctk.CTkComboBox(
            provider_row, variable=self.summary_provider, values=_SUMMARY_PROVIDER_LABELS,
            state="readonly", width=150, height=34, corner_radius=9,
            fg_color="#0D1525", border_color="#2A3A58", button_color="#263550",
            button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.provider_selector.pack(side=tk.RIGHT)
        ctk.CTkLabel(
            processing_card, textvariable=self.provider_hint, font=("Segoe UI", 9),
            text_color="#C9D3FF", anchor="w", wraplength=470,
        ).pack(fill=tk.X, padx=14, pady=(0, 9))
        self.provider_login_button = ctk.CTkButton(
            processing_card, text="Conectar conta no navegador", command=self._start_provider_login,
            height=32, corner_radius=8, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.provider_setup_button = ctk.CTkButton(
            processing_card, text="Tentar instalar providers", command=self._prepare_local_providers,
            height=32, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )

        self.new_provider_button = ctk.CTkButton(
            processing_card, text="+ Novo Provider", command=self._toggle_api_provider_form,
            height=34, corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.new_provider_button.pack(fill=tk.X, padx=14, pady=(0, 10))

        self.api_card = ctk.CTkFrame(processing_card, fg_color="#0D1525", corner_radius=10)
        ctk.CTkLabel(self.api_card, text="PROVIDER POR TOKEN", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(10, 2))
        ctk.CTkLabel(self.api_card, text="Compatível com OpenAI ou endpoint JSON personalizado.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(0, 5))
        ctk.CTkLabel(self.api_card, text="Tipo de integração", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(4, 1))
        ctk.CTkComboBox(
            self.api_card, variable=self.api_protocol,
            values=["openai_compatible", "custom_json"], state="readonly", height=30,
            corner_radius=7, fg_color="#080C16", border_color="#2A3A58",
            button_color="#263550", button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X, padx=10, pady=(0, 3))
        for label, variable, secret in [
            ("Nome", self.api_provider_name, False),
            ("URL-base (ou URL completa no modo custom_json)", self.api_base_url, False),
            ("Modelo", self.api_model, False),
            ("Token", self.api_token, True),
        ]:
            ctk.CTkLabel(self.api_card, text=label, font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(4, 1))
            ctk.CTkEntry(self.api_card, textvariable=variable, show="•" if secret else "", height=30, corner_radius=7, fg_color="#080C16", border_color="#2A3A58", text_color=_COLORS["text"]).pack(fill=tk.X, padx=10, pady=(0, 3))
        self.api_advanced_button = ctk.CTkButton(
            self.api_card, text="Opções avançadas", command=self._toggle_api_advanced,
            height=28, corner_radius=7, fg_color="transparent", hover_color="#1B2943",
            text_color="#C9D3FF", font=("Segoe UI", 9, "bold"),
        )
        self.api_advanced_button.pack(fill=tk.X, padx=10, pady=(5, 3))
        self.api_advanced_card = ctk.CTkFrame(self.api_card, fg_color="#080C16", corner_radius=7)
        for label, variable in [
            ("Cabeçalho de autenticação", self.api_auth_header),
            ("Prefixo do token", self.api_auth_prefix),
            ("Caminho da resposta", self.api_response_path),
        ]:
            ctk.CTkLabel(self.api_advanced_card, text=label, font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=8, pady=(5, 1))
            ctk.CTkEntry(self.api_advanced_card, textvariable=variable, height=28, corner_radius=6, fg_color="#0D1525", border_color="#2A3A58", text_color=_COLORS["text"]).pack(fill=tk.X, padx=8, pady=(0, 2))
        ctk.CTkLabel(self.api_advanced_card, text="Corpo JSON: usado somente em custom_json.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=8, pady=(5, 1))
        self.api_request_template = ctk.CTkTextbox(self.api_advanced_card, height=56, corner_radius=6, fg_color="#0D1525", border_color="#2A3A58", border_width=1, text_color=_COLORS["text"], font=("Consolas", 9))
        self.api_request_template.insert("1.0", self.api_request_template_default)
        self.api_request_template.pack(fill=tk.X, padx=8, pady=(0, 8))
        ctk.CTkButton(self.api_card, text="Salvar provider por token", command=self._save_api_provider, height=32, corner_radius=8, fg_color="#244462", hover_color="#315A80", text_color=_COLORS["text"], font=("Segoe UI", 10, "bold")).pack(fill=tk.X, padx=10, pady=(6, 10))

        update_card = settings_card(
            self._settings_sections["provider"], "Atualizações", "Confira a versão instalada e instale uma nova versão quando ela estiver disponível.",
        )
        update_status = ctk.CTkFrame(
            update_card, fg_color="#0D1525", corner_radius=8,
            border_width=1, border_color="#2A3A58",
        )
        update_status.pack(fill=tk.X, padx=14, pady=(0, 9))
        ctk.CTkLabel(
            update_status, text="ESTADO DA ATUALIZAÇÃO", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(8, 1))
        ctk.CTkLabel(
            update_status, textvariable=self.update_hint, font=("Segoe UI", 10), text_color="#C9D3FF",
            anchor="w", justify=tk.LEFT, wraplength=448,
        ).pack(fill=tk.X, padx=10, pady=(0, 8))
        update_actions = ctk.CTkFrame(update_card, fg_color="transparent")
        update_actions.pack(fill=tk.X, padx=14, pady=(0, 12))
        self.update_apply_button = ctk.CTkButton(
            update_actions, text="Atualizar agora", command=self._apply_update, state=tk.DISABLED,
            width=124, height=34, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], text_color_disabled="#72809A", font=("Segoe UI", 10, "bold"),
        )
        self.update_apply_button.pack(side=tk.RIGHT)
        self.update_check_button = ctk.CTkButton(
            update_actions, text="Verificar agora", command=self._check_for_updates,
            width=142, height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 10, "bold"),
        )
        self.update_check_button.pack(side=tk.RIGHT, padx=(0, 6))

        support_card = settings_card(
            self._settings_sections["provider"], "Curtiu o Voice Notes?", "Se ele te salvou em uma reunião, aula ou ideia de última hora, um apoio ajuda a manter o projeto vivo.",
        )
        ctk.CTkButton(
            support_card, text="Apoiar o projeto", command=self._open_pix_support,
            height=32, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(fill=tk.X, padx=14, pady=(0, 12))

        transcription_card = settings_card(self._settings_sections["transcription"], "Transcrição", "Idioma e qualidade do texto transcrito.")
        self._api_form_anchor = self.new_provider_button
        transcript_row = ctk.CTkFrame(transcription_card, fg_color="transparent")
        transcript_row.pack(fill=tk.X, padx=14, pady=(0, 12))
        model_field = ctk.CTkFrame(transcript_row, fg_color="transparent")
        model_field.pack(fill=tk.X)
        ctk.CTkLabel(model_field, text="Modelo Whisper", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
        ctk.CTkComboBox(
            model_field, variable=self.pipeline_model, values=self._available_models,
            state="readonly", height=34, corner_radius=9, fg_color="#0D1525",
            border_color="#2A3A58", button_color="#263550", button_hover_color="#34476B",
            text_color=_COLORS["text"], dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X)
        model_note = ctk.CTkFrame(model_field, height=25, fg_color="#0D1525", corner_radius=7)
        model_note.pack(fill=tk.X, pady=(6, 0))
        model_note.pack_propagate(False)
        ctk.CTkLabel(model_note, textvariable=self.model_description, text_color="#C9D3FF", font=("Segoe UI", 9), anchor="w").pack(fill=tk.BOTH, padx=8)
        language_field = ctk.CTkFrame(transcript_row, fg_color="transparent")
        language_field.pack(fill=tk.X, pady=(12, 0))
        ctk.CTkLabel(language_field, text="Idioma", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
        ctk.CTkComboBox(
            language_field, variable=self.pipeline_language, values=_LANG_LABELS,
            state="readonly", height=34, corner_radius=9, fg_color="#0D1525",
            border_color="#2A3A58", button_color="#263550", button_hover_color="#34476B",
            text_color=_COLORS["text"], dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X)

        speakers_card = settings_card(self._settings_sections["speakers"], "Falantes", "Opcional: identifica Pessoa 1, Pessoa 2 e assim por diante.")
        diarization_row = ctk.CTkFrame(speakers_card, fg_color="transparent")
        diarization_row.pack(fill=tk.X, padx=14, pady=(0, 12))
        ctk.CTkCheckBox(
            diarization_row, text="Separar falantes (Pessoa 1, Pessoa 2)", variable=self.diarize_speakers,
            fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            diarization_row, text="Ativa automaticamente quando houver token salvo do Hugging Face.",
            text_color=_COLORS["muted"], font=("Segoe UI", 9), anchor="w",
        ).pack(anchor=tk.W, pady=(3, 8))
        ctk.CTkLabel(
            diarization_row, text="TOKEN DO HUGGING FACE", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.huggingface_token_entry = ctk.CTkEntry(
            diarization_row, textvariable=self.huggingface_token, show="•",
            placeholder_text="Token de leitura do Hugging Face", height=32, corner_radius=8,
            fg_color="#0D1525", border_color="#2A3A58", text_color=_COLORS["text"],
        )
        self.huggingface_token_entry.pack(fill=tk.X)
        token_actions = ctk.CTkFrame(diarization_row, fg_color="transparent")
        token_actions.pack(fill=tk.X, pady=(8, 0))
        self.huggingface_token_visibility_button = ctk.CTkButton(
            token_actions, text="Mostrar", command=self._toggle_huggingface_token_visibility,
            width=76, height=29, corner_radius=7, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.huggingface_token_visibility_button.pack(side=tk.LEFT)
        ctk.CTkButton(
            token_actions, text="Copiar", command=self._copy_huggingface_token,
            width=68, height=29, corner_radius=7, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ctk.CTkButton(
            token_actions, text="Salvar token", command=self._save_huggingface_token,
            width=94, height=29, corner_radius=7, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT)

        self._file_panel = ctk.CTkFrame(
            content, fg_color="#111A2C", corner_radius=16,
            border_width=1, border_color="#253552",
        )
        ctk.CTkLabel(
            self._file_panel, text="IMPORTAR ARQUIVO", font=("Segoe UI", 11, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 1))
        ctk.CTkLabel(
            self._file_panel, text="Selecione um áudio já gravado para transcrever e resumir.",
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 10))
        self.process_button = ctk.CTkButton(
            self._file_panel, text="Escolher arquivo de áudio", command=self._process_existing_mp3,
            height=42, corner_radius=10, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 11, "bold"),
        )
        self.process_button.pack(fill=tk.X, padx=14, pady=(0, 8))
        self.text_import_button = ctk.CTkButton(
            self._file_panel, text="Colar ou abrir transcrição", command=self._toggle_text_import,
            height=38, corner_radius=10, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 11, "bold"),
        )
        self.text_import_button.pack(fill=tk.X, padx=14, pady=(0, 8))
        self._text_import_panel = ctk.CTkFrame(self._file_panel, fg_color="#0D1525", corner_radius=10)
        ctk.CTkLabel(
            self._text_import_panel, text="TRANSCRIÇÃO PRONTA", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 2))
        self.import_text_editor = ctk.CTkTextbox(
            self._text_import_panel, height=100, corner_radius=8, fg_color="#080C16",
            border_width=1, border_color="#2A3A58", text_color=_COLORS["text"], font=("Consolas", 10), wrap="word",
        )
        self.import_text_editor.pack(fill=tk.X, padx=12, pady=(0, 7))
        text_import_actions = ctk.CTkFrame(self._text_import_panel, fg_color="transparent")
        text_import_actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.import_text_load_button = ctk.CTkButton(
            text_import_actions, text="Abrir .txt/.md", command=self._load_text_import,
            width=104, height=30, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.import_text_load_button.pack(side=tk.LEFT)
        self.import_text_save_button = ctk.CTkButton(
            text_import_actions, text="Salvar", command=self._save_imported_text,
            width=72, height=30, corner_radius=8, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.import_text_save_button.pack(side=tk.RIGHT)
        self.import_text_summary_button = ctk.CTkButton(
            text_import_actions, text="Salvar e gerar resumo", command=self._save_imported_text_and_regenerate,
            height=30, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 9, "bold"),
        )
        self.import_text_summary_button.pack(side=tk.RIGHT, padx=(0, 6))
        ctk.CTkFrame(self._file_panel, height=1, fg_color="#253552").pack(fill=tk.X, padx=14, pady=(6, 10))
        ctk.CTkLabel(
            self._file_panel, text="JÁ TENHO UMA TRANSCRIÇÃO", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(0, 4))
        self.retry_summary_button = ctk.CTkButton(
            self._file_panel,
            text="Abrir transcrição salva para resumir",
            command=self._retry_summary_from_transcription,
            height=42,
            corner_radius=10,
            fg_color="#244462",
            hover_color="#315A80",
            text_color=_COLORS["text"],
            font=("Segoe UI", 11, "bold"),
        )
        self.retry_summary_button.pack(fill=tk.X, padx=14, pady=(0, 3))
        ctk.CTkLabel(
            self._file_panel,
            text="O texto colado, aberto ou corrigido entra na Biblioteca e não transcreve o áudio de novo.",
            font=("Segoe UI", 9),
            text_color=_COLORS["muted"],
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(0, 12))

        # YouTube is a dedicated page. It deliberately does not share the
        # configuration page, because this is an action-specific workflow.
        self._youtube_panel = ctk.CTkFrame(
            content, fg_color="#111A2C", corner_radius=16,
            border_width=1, border_color="#253552",
        )
        ctk.CTkLabel(self._youtube_panel, text="IMPORTAR DO YOUTUBE", font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=16, pady=(16, 1))
        ctk.CTkLabel(self._youtube_panel, text="Baixe o áudio de um vídeo autorizado e escolha como processar.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(0, 14))
        ctk.CTkLabel(self._youtube_panel, text="LINK DO VÍDEO", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(0, 3))
        self.youtube_url_entry = ctk.CTkEntry(
            self._youtube_panel, textvariable=self.youtube_url,
            placeholder_text="https://www.youtube.com/watch?v=...", height=34, corner_radius=9,
            fg_color="#080C16", border_color="#2A3A58", text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_url_entry.pack(fill=tk.X, padx=16)
        ctk.CTkLabel(self._youtube_panel, text="O QUE FAZER", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 3))
        self.youtube_mode_selector = ctk.CTkComboBox(
            self._youtube_panel, variable=self.youtube_mode,
            values=["Transcrição e resumo", "Só transcrição", "Só resumo"], state="readonly",
            height=32, corner_radius=8, fg_color="#080C16", border_color="#2A3A58",
            button_color="#263550", button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_mode_selector.pack(fill=tk.X, padx=16)
        ctk.CTkLabel(self._youtube_panel, text="PERFIL", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 3))
        self.youtube_profile_selector = ctk.CTkComboBox(
            self._youtube_panel, variable=self.processing_profile, values=list(_PROCESSING_PROFILES), state="readonly",
            height=32, corner_radius=8, fg_color="#080C16", border_color="#2A3A58",
            button_color="#263550", button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_profile_selector.pack(fill=tk.X, padx=16)
        ctk.CTkLabel(self._youtube_panel, text="FORMATO DO RESUMO", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 3))
        self.youtube_template_selector = ctk.CTkComboBox(
            self._youtube_panel, variable=self.summary_template, values=_SUMMARY_TEMPLATE_LABELS,
            state="readonly", height=32, corner_radius=8, fg_color="#080C16", border_color="#2A3A58",
            button_color="#263550", button_hover_color="#34476B", text_color=_COLORS["text"],
            dropdown_fg_color="#162136", dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_template_selector.pack(fill=tk.X, padx=16)
        self.youtube_process_button = ctk.CTkButton(
            self._youtube_panel, text="Baixar áudio e processar", command=self._process_youtube,
            height=42, corner_radius=10, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 11, "bold"),
        )
        self.youtube_process_button.pack(fill=tk.X, padx=16, pady=(12, 4))
        ctk.CTkLabel(self._youtube_panel, textvariable=self.youtube_hint, font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=17, pady=(0, 12))

        # Biblioteca local: permanece dentro do widget para não fragmentar a tarefa
        # entre janelas pequenas. Ela indexa as pastas já criadas pelo pipeline.
        self._library_panel = ctk.CTkFrame(
            content, fg_color="#111A2C", corner_radius=14,
            border_width=1, border_color="#2A3A58",
        )
        library_header = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_header.pack(fill=tk.X, padx=14, pady=(12, 7))
        ctk.CTkLabel(
            library_header, text="BIBLIOTECA", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        self.library_refresh_button = ctk.CTkButton(
            library_header, text="Atualizar", command=self._refresh_library, width=78, height=28,
            corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.library_refresh_button.pack(side=tk.RIGHT)
        queue_row = ctk.CTkFrame(self._library_panel, fg_color="#0D1525", corner_radius=8)
        queue_row.pack(fill=tk.X, padx=14, pady=(0, 7))
        ctk.CTkLabel(
            queue_row, textvariable=self.queue_hint, font=("Segoe UI", 10, "bold"),
            text_color="#C9D3FF", anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 4), pady=7)
        self.retry_queue_button = ctk.CTkButton(
            queue_row, text="Retomar", command=self._retry_pending_jobs, width=70, height=26,
            corner_radius=7, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.retry_queue_button.pack(side=tk.RIGHT, padx=5, pady=4)
        self.library_search_entry = ctk.CTkEntry(
            self._library_panel, textvariable=self.library_search,
            placeholder_text="Buscar por título ou pasta", height=34, corner_radius=9,
            fg_color="#0D1525", border_color="#2A3A58", text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.library_search_entry.pack(fill=tk.X, padx=14, pady=(0, 7))
        self.library_search.trace_add("write", lambda *_: self._render_library_list())
        library_list_area = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_list_area.pack(fill=tk.X, padx=14, pady=(0, 7))
        self.library_listbox = tk.Listbox(
            library_list_area, height=6, activestyle="none", selectmode=tk.SINGLE,
            bg="#0D1525", fg=_COLORS["text"], selectbackground="#384A7A",
            selectforeground="#FFFFFF", highlightthickness=1, highlightbackground="#2A3A58",
            relief=tk.FLAT, font=("Segoe UI", 10), exportselection=False,
        )
        self.library_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_list_scrollbar = ctk.CTkScrollbar(
            library_list_area, command=self.library_listbox.yview, width=12,
            fg_color="transparent", button_color="#263550", button_hover_color="#34476B",
        )
        self.library_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.library_listbox.configure(yscrollcommand=self.library_list_scrollbar.set)
        self.library_listbox.bind("<<ListboxSelect>>", self._on_library_select)
        ctk.CTkLabel(
            self._library_panel, textvariable=self.library_detail,
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
            wraplength=500, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=16, pady=(0, 8))
        library_documents = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_documents.pack(fill=tk.X, padx=14, pady=(0, 7))
        self.library_edit_button = ctk.CTkButton(
            library_documents, text="Abrir transcrição", command=self._edit_selected_transcript,
            height=34, corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_edit_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_open_summary_button = ctk.CTkButton(
            library_documents, text="Abrir resumo", command=self._open_selected_summary,
            height=34, corner_radius=9, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_open_summary_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        library_actions = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_actions.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.library_summary_button = ctk.CTkButton(
            library_actions, text="Gerar resumo", command=self._regenerate_selected_summary,
            height=34, corner_radius=9, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 10, "bold"),
        )
        self.library_summary_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_open_button = ctk.CTkButton(
            library_actions, text="Abrir pasta", command=self._open_selected_folder,
            height=34, corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_open_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        library_exports = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_exports.pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkButton(
            library_exports, text="Exportar DOCX", command=lambda: self._export_selected_document("docx"),
            height=30, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkButton(
            library_exports, text="Exportar PDF", command=lambda: self._export_selected_document("pdf"),
            height=30, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        self._library_editor = ctk.CTkFrame(self._library_panel, fg_color="#0D1525", corner_radius=10)
        ctk.CTkLabel(
            self._library_editor, textvariable=self.library_editor_title, font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 4))
        self.transcript_editor = ctk.CTkTextbox(
            self._library_editor, height=90, corner_radius=8, fg_color="#080C16",
            border_width=1, border_color="#2A3A58", text_color=_COLORS["text"],
            font=("Consolas", 10), wrap="word",
        )
        self.transcript_editor.pack(fill=tk.X, padx=12, pady=(0, 8))
        editor_actions = ctk.CTkFrame(self._library_editor, fg_color="transparent")
        editor_actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.library_suggest_names_button = ctk.CTkButton(
            editor_actions, text="Sugerir nomes", command=self._suggest_speaker_names,
            width=92, height=32, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.library_suggest_names_button.pack(side=tk.LEFT)
        ctk.CTkButton(
            editor_actions, text="Cancelar", command=self._close_transcript_editor,
            width=82, height=32, corner_radius=8, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        self.library_save_button = ctk.CTkButton(
            editor_actions, text="Salvar", command=self._save_open_document,
            width=66, height=32, corner_radius=8, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_save_button.pack(side=tk.RIGHT, padx=(0, 7))
        self.library_regenerate_button = ctk.CTkButton(
            editor_actions, text="Salvar e gerar resumo", command=self._save_transcript_and_regenerate,
            height=32, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 10, "bold"),
        )
        self.library_regenerate_button.pack(side=tk.RIGHT, padx=(0, 7))

        # Barra de progresso do pipeline
        self.progressbar = ctk.CTkProgressBar(
            content, height=4, corner_radius=2, fg_color="#1C2941",
            progress_color=_COLORS["accent"], mode="indeterminate",
        )
        self.progressbar.set(0)

        # Do not put a widget, icon, or overlay in the lower-right corner.
        # The root detects that small corner area directly, so the rounded
        # capsule remains visually uninterrupted.
        self.bind_all("<ButtonPress-1>", self._maybe_start_window_resize, add="+")
        self.bind_all("<B1-Motion>", self._resize_window, add="+")
        self.bind_all("<ButtonRelease-1>", self._stop_window_resize, add="+")
        self.bind_all("<Motion>", self._update_resize_cursor, add="+")

        # Modo compacto: uma etiqueta sempre visível, sem a barra ou os campos
        # do widget completo. Ação e estado continuam acessíveis sem precisar
        # interromper uma reunião para abrir a janela principal.
        self._compact_surface = ctk.CTkFrame(
            self, fg_color="#101827", corner_radius=18,
            border_width=1, border_color="#34486C",
        )
        compact_main = ctk.CTkFrame(self._compact_surface, fg_color="transparent")
        compact_main.pack(fill=tk.BOTH, expand=True, padx=12, pady=9)
        self._compact_main = compact_main
        self._compact_indicator = ctk.CTkLabel(
            compact_main, text="", width=10, height=10, corner_radius=5,
            fg_color="#55D6A0",
        )
        self._compact_indicator.pack(side=tk.LEFT, padx=(0, 8))
        compact_text = ctk.CTkFrame(compact_main, fg_color="transparent")
        compact_text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=1)
        self._compact_status_label = ctk.CTkLabel(
            compact_text, textvariable=self._compact_status,
            font=("Segoe UI", 10, "bold"), text_color=_COLORS["text"], anchor="w",
        )
        self._compact_status_label.pack(fill=tk.BOTH, expand=True)
        self._compact_meter = tk.Canvas(
            compact_main, width=86, height=28, bg="#101827", highlightthickness=0, bd=0,
        )
        self._compact_meter.pack(side=tk.LEFT, padx=(10, 12))
        self._compact_meter.bind("<Configure>", lambda _: self._redraw_eq())
        self.compact_start_button = ctk.CTkButton(
            compact_main, text="Iniciar", command=self._start_recording,
            width=66, height=32, corner_radius=9, fg_color=_COLORS["accent"],
            hover_color=_COLORS["accent_hover"], text_color="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
        )
        self.compact_start_button.pack(side=tk.LEFT, padx=(0, 6))
        self.compact_stop_button = ctk.CTkButton(
            compact_main, text="Parar", command=self._stop_recording,
            width=60, height=32, corner_radius=9, fg_color="#3C2A3B",
            hover_color="#55384E", text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.compact_stop_button.pack(side=tk.LEFT)
        for widget in (self._compact_surface, compact_main, self._compact_indicator, compact_text, self._compact_status_label, self._compact_meter):
            widget.bind("<ButtonPress-1>", self._start_compact_drag, add="+")
            widget.bind("<B1-Motion>", self._drag_compact_widget, add="+")
            widget.bind("<ButtonRelease-1>", self._stop_compact_drag, add="+")

        # Each destination owns one direct page in the shared scrollable area.
        # The outer widget remains compact and fully visible; long forms scroll
        # within this area instead of extending past the desktop work area.
        self._page_layouts: dict[str, list[tuple[tk.Misc, dict[str, object]]]] = {
            "record": [
                (status_card, {"fill": tk.X, "padx": 20, "pady": (4, 8)}),
                (self.device_info_label, {"fill": tk.X, "padx": 22, "pady": (0, 4)}),
                (capture_card, {"fill": tk.X, "padx": 20, "pady": (8, 8)}),
                (self._buttons, {"side": tk.BOTTOM, "fill": tk.X, "padx": 20, "pady": (0, 10)}),
            ],
            "file": [
                (self._file_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
            ],
            "youtube": [
                (self._youtube_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
            ],
            "library": [
                (self._library_panel, {"fill": tk.BOTH, "expand": True, "padx": 20, "pady": (12, 10)}),
            ],
            "settings": [
                (self._settings_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
            ],
        }
        self._current_page = "record"
        self.device_info_text.trace_add("write", self._on_device_info_changed)
        self._show_page("record")

        self._widget_hidden: tuple[tk.Misc, ...] = ()

    def _refresh_provider_hint(self, *_: object) -> None:
        provider = self.summary_provider.get()
        if provider == "API por token":
            self.provider_hint.set("Resumo por API · configure URL, modelo e token em Ajustes")
            return
        self.provider_hint.set(f"Resumo por {provider}  ·  altere em Ajustes")

    def _on_provider_changed(self, *_: object) -> None:
        self._refresh_provider_hint()
        self.after_idle(self._check_provider_login)

    def _on_model_changed(self, *_: object) -> None:
        model = self.pipeline_model.get()
        self.model_description.set(
            _WHISPER_MODEL_DESCRIPTIONS.get(model, "Modelo Whisper selecionado")
        )

    def _on_processing_profile_changed(self, *_: object) -> None:
        template, model, separate_speakers = _PROCESSING_PROFILES.get(
            self.processing_profile.get(), (None, None, None)
        )
        if template is not None:
            self.summary_template.set(template)
        if model is not None and model in self._available_models:
            self.pipeline_model.set(model)
        if separate_speakers is not None:
            # Do not force a diarization attempt when no authorized token exists.
            self.diarize_speakers.set(bool(separate_speakers and self.huggingface_token.get().strip()))

    def _on_recording_output_choice(self, label: str) -> None:
        """Keep the compact display label separate from the pipeline value."""
        self.recording_output_mode.set(_RECORDING_OUTPUT_CODES[label])

    def _on_recording_output_mode_changed(self, *_: object) -> None:
        hints = {
            "audio": "Áudio salvo sem iniciar transcrição ou resumo.",
            "transcription": "Áudio salvo e enviado apenas para transcrição.",
            "both": "Áudio salvo, depois transcrição e resumo.",
        }
        self.recording_output_hint.set(hints.get(self.recording_output_mode.get(), hints["both"]))

    def _check_provider_login(self) -> None:
        """Reflect provider readiness without ever opening a command prompt."""
        provider = _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex")
        if provider == "api":
            from record_transcript_resume.api_provider import has_token
            self.provider_login_button.pack_forget()
            self.provider_setup_button.pack_forget()
            self.provider_hint.set(
                "Resumo por API · token configurado" if has_token()
                else "Cadastre URL, modelo e token em Ajustes para usar a API."
            )
            return
        if self._provider_status_check_running:
            return
        self._provider_status_check_running = True
        threading.Thread(target=self._provider_status_check_worker, args=(provider,), daemon=True).start()

    def _provider_status_check_worker(self, provider: str) -> None:
        from record_transcript_resume.synthesis import provider_login_status

        try:
            status = provider_login_status(provider)
        except Exception as exc:
            from record_transcript_resume.log import log

            log(f"GUI: falha ao verificar login do Codex: {exc}")
            self.after(0, self._on_provider_status_checked, provider, None)
            return
        self.after(0, self._on_provider_status_checked, provider, status)

    def _on_provider_status_checked(self, provider: str, status: object | None) -> None:
        self._provider_status_check_running = False
        if provider != _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex") or status is None:
            return

        if not getattr(status, "installed", False):
            self.provider_login_button.pack_forget()
            if not self._provider_setup_running and not getattr(self, "_provider_setup_attempted", False):
                self._prepare_local_providers(automatic=True)
            elif getattr(self, "_provider_setup_attempted", False):
                from record_transcript_resume.provider_setup import provider_setup_log_path

                self.provider_hint.set(f"{self.summary_provider.get()} ainda não está disponível. Detalhes: {provider_setup_log_path()}")
                self._show_provider_setup_button("Tentar instalar providers")
            else:
                self.provider_hint.set(f"Preparando {self.summary_provider.get()} automaticamente. Isso pode levar alguns minutos.")
            return
        source = "cópia local do Voice Notes" if getattr(status, "source", "system") == "voice_notes" else "instalação do sistema"
        if getattr(status, "authenticated", False):
            self.provider_login_button.pack_forget()
            self.provider_hint.set(f"Resumo por {self.summary_provider.get()} · conta conectada · {source}")
            self.provider_setup_button.pack_forget()
            return
        self.provider_hint.set(f"{self.summary_provider.get()} está instalado ({source}); conecte sua conta pelo navegador para ativar os resumos.")
        self.provider_login_button.pack(fill=tk.X, padx=14, pady=(0, 10), before=self.new_provider_button)
        self.provider_setup_button.pack_forget()

    def _show_provider_setup_button(self, text: str) -> None:
        self.provider_setup_button.configure(text=text)
        self.provider_setup_button.pack(fill=tk.X, padx=14, pady=(0, 10), before=self.new_provider_button)

    def _prepare_local_providers(self, automatic: bool = False) -> None:
        """Install the app-owned CLI copy without replacing any system CLI."""
        if self._provider_setup_running:
            return
        self._provider_setup_running = True
        self._provider_setup_attempted = True
        self.provider_setup_button.pack_forget()
        action = "automaticamente" if automatic else "em uma cópia local"
        self.provider_hint.set(f"Preparando {self.summary_provider.get()} {action}. Isso pode levar alguns minutos.")
        threading.Thread(target=self._provider_setup_worker, daemon=True).start()

    def _provider_setup_worker(self) -> None:
        """Recover a missed installer setup without showing PowerShell or cmd.exe."""
        from record_transcript_resume.log import log
        from record_transcript_resume.provider_setup import provider_setup_log_path, start_provider_setup

        try:
            process = start_provider_setup()
            exit_code = process.wait()
            if exit_code == 0:
                message = "Providers instalados automaticamente. Conecte sua conta para gerar resumos."
            else:
                log_path = provider_setup_log_path()
                message = f"Não foi possível preparar os providers automaticamente. Detalhes: {log_path}"
            log(f"GUI: instalação automática dos providers concluída (code={exit_code})")
        except Exception as exc:
            log(f"GUI: falha ao instalar providers automaticamente: {exc}")
            message = "Não foi possível preparar os providers automaticamente. Tente novamente ao abrir o app."
        self.after(0, self._on_provider_setup_finished, message)

    def _on_provider_setup_finished(self, message: str) -> None:
        self._provider_setup_running = False
        self.provider_hint.set(message)
        self.after(400, self._check_provider_login)

    def _start_provider_login(self) -> None:
        """Request browser authentication only when the person chooses it."""
        provider = _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex")
        if provider == "api":
            return
        try:
            from record_transcript_resume.synthesis import start_provider_login

            start_provider_login(provider)
        except OSError as exc:
            from record_transcript_resume.log import log

            log(f"GUI: não foi possível iniciar login de {provider}: {exc}")
            self.provider_hint.set(f"Não foi possível abrir a autenticação de {self.summary_provider.get()}.")
            return
        self.provider_hint.set(f"Autenticação de {self.summary_provider.get()} iniciada no navegador. Volte aqui após concluir.")
        self.after(2500, self._check_provider_login)

    def _toggle_huggingface_token_visibility(self) -> None:
        visible = self.huggingface_token_entry.cget("show") == ""
        self.huggingface_token_entry.configure(show="•" if visible else "")
        self.huggingface_token_visibility_button.configure(text="Mostrar" if visible else "Ocultar")

    def _copy_huggingface_token(self) -> None:
        token = self.huggingface_token.get().strip()
        if not token:
            messagebox.showinfo("Token ausente", "Informe ou salve o token do Hugging Face antes de copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(token)
        self.update()
        self.status.set("Token do Hugging Face copiado para a área de transferência.")

    def _open_pix_support(self) -> None:
        """Show an optional Pix support window without interrupting the workflow."""
        existing = self._pix_support_window
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return

        window = ctk.CTkToplevel(self)
        self._pix_support_window = window
        window.title("Apoie o Voice Notes")
        window.resizable(False, False)
        window.transient(self)
        window.configure(fg_color=_COLORS["bg"])
        window.protocol("WM_DELETE_WINDOW", lambda: self._close_pix_support(window))

        card = ctk.CTkFrame(
            window, fg_color=_COLORS["surface"], corner_radius=16,
            border_width=1, border_color=_COLORS["border"],
        )
        card.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        ctk.CTkLabel(
            card, text="Curtiu o Voice Notes?", font=("Segoe UI", 16, "bold"),
            text_color=_COLORS["text"],
        ).pack(padx=20, pady=(20, 5))
        ctk.CTkLabel(
            card, text="Se ele te deu uma mão, você pode mandar um\ncafezinho para o criador. Mas fica tranquilo:\nusar o app continua 100% livre.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], justify=tk.CENTER,
        ).pack(padx=20, pady=(0, 14))

        try:
            from PIL import Image

            image = Image.open(_asset_path("pix-victor-nemeth-jurado.png"))
            qr_code = ctk.CTkImage(light_image=image, dark_image=image, size=(210, 210))
            qr_label = ctk.CTkLabel(card, text="", image=qr_code)
            qr_label.image = qr_code
            qr_label.pack(padx=20, pady=(0, 12))
        except Exception:
            ctk.CTkLabel(
                card, text="QR Code indisponível neste momento.\nUse a chave Pix abaixo.",
                font=("Segoe UI", 10), text_color=_COLORS["warning"], justify=tk.CENTER,
            ).pack(padx=20, pady=(0, 12))

        ctk.CTkLabel(
            card, text="Victor Nemeth Jurado · São Paulo", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["text"],
        ).pack(padx=20, pady=(0, 8))
        pix_key = ctk.CTkEntry(
            card, height=34, width=315, corner_radius=8, fg_color="#0D1525",
            border_color="#2A3A58", text_color=_COLORS["text"], font=("Consolas", 9),
        )
        pix_key.insert(0, _PIX_KEY)
        pix_key.configure(state=tk.DISABLED)
        pix_key.pack(padx=20, pady=(0, 10))
        ctk.CTkButton(
            card, text="Copiar chave Pix", command=self._copy_pix_key,
            height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(fill=tk.X, padx=20, pady=(0, 20))

        window.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - window.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")
        window.lift()
        window.focus_force()

    def _close_pix_support(self, window: ctk.CTkToplevel) -> None:
        if window.winfo_exists():
            window.destroy()
        self._pix_support_window = None

    def _copy_pix_key(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(_PIX_KEY)
        self.update()
        self.status.set("Chave Pix copiada para a área de transferência. Obrigado pelo apoio!")

    def _save_huggingface_token(self) -> None:
        token = self.huggingface_token.get().strip()
        if not token:
            messagebox.showerror("Token ausente", "Informe o token do Hugging Face antes de salvar.")
            return
        try:
            import keyring

            keyring.set_password("Voice Notes", "huggingface-token", token)
        except Exception as exc:
            messagebox.showerror("Não foi possível salvar", f"O token não pôde ser salvo no Cofre de Credenciais do Windows.\n\n{exc}")
            return
        self.huggingface_token.set(token)
        self.diarize_speakers.set(True)
        self.status.set("Token do Hugging Face salvo com segurança.")

    def _check_for_updates(self) -> None:
        if self._update_check_running:
            return
        self._update_check_running = True
        self.update_check_button.configure(state=tk.DISABLED, text="Verificando…")
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _update_check_worker(self) -> None:
        from record_transcript_resume.updates import check_for_updates

        result = check_for_updates()
        self.after(0, self._on_update_checked, result)

    def _on_update_checked(self, result: object) -> None:
        self._update_check_running = False
        self._available_update = result
        self.update_hint.set(str(getattr(result, "message", "Não foi possível verificar atualizações.")))
        available = bool(getattr(result, "available", False))
        self.update_check_button.configure(
            state=tk.NORMAL, text="Verificar agora",
            fg_color="#263550" if available else _COLORS["accent"],
            hover_color="#34476B" if available else _COLORS["accent_hover"],
            text_color=_COLORS["text"] if available else "#FFFFFF",
        )
        self.update_apply_button.configure(
            state=tk.NORMAL if available else tk.DISABLED,
            fg_color=_COLORS["accent"] if available else "#263550",
            hover_color=_COLORS["accent_hover"] if available else "#34476B",
            text_color="#FFFFFF" if available else _COLORS["text"],
        )

    def _apply_update(self) -> None:
        update = getattr(self, "_available_update", None)
        if update is None or not getattr(update, "available", False):
            return
        active_work = self._active_work_description()
        if active_work is not None:
            messagebox.showinfo("Atualização aguardando", f"Conclua a {active_work} antes de atualizar o Voice Notes.")
            return
        if not messagebox.askyesno(
            "Instalar atualização",
            f"A versão {getattr(update, 'version', '')} será baixada e instalada agora. O Voice Notes será reiniciado. Continuar?",
        ):
            return
        self.update_apply_button.configure(state=tk.DISABLED, text="Atualizando…")
        self.update_check_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._apply_update_worker, args=(update,), daemon=True).start()

    def _apply_update_worker(self, update: object) -> None:
        from record_transcript_resume.updates import download_update

        result = download_update(update)
        self.after(0, self._on_update_applied, result)

    def _on_update_applied(self, result: object) -> None:
        self.update_hint.set(str(getattr(result, "message", "Não foi possível atualizar.")))
        self.update_apply_button.configure(text="Atualizar agora")
        self.update_check_button.configure(state=tk.NORMAL)
        if getattr(result, "available", False):
            from record_transcript_resume.updates import start_downloaded_update

            launch_result = start_downloaded_update(result)
            self.update_hint.set(str(getattr(launch_result, "message", "Não foi possível iniciar a atualização.")))
            if getattr(launch_result, "available", False):
                self.after(150, self._close_for_update)
                return
            self.update_apply_button.configure(state=tk.NORMAL)
        else:
            self._check_for_updates()

    def _close_for_update(self) -> None:
        """Exit fully so the installer can replace the executable safely."""
        if self._active_work_description() is not None:
            self.update_hint.set("A atualização foi preparada, mas há uma atividade em andamento.")
            self.update_apply_button.configure(state=tk.NORMAL)
            return
        self._tray.stop()
        self.destroy()

    def _set_widget_mode(self, enabled: bool) -> None:
        if not enabled or self._widget_mode:
            return

        self._widget_mode = True
        for widget in self._widget_hidden:
            widget.pack_forget()
        self.title("Voice Notes (Beta)")
        self.attributes("-topmost", True)
        self.minsize(self._min_widget_width, self._min_widget_height)
        self.geometry(f"560x{self._main_widget_height}")
        self.overrideredirect(True)
        # Releasing anywhere in the widget reliably ends a header drag.  This
        # binding only clears state; it never starts a drag from page controls.
        self.bind("<ButtonRelease-1>", self._stop_window_drag, add="+")
        self.after_idle(self._schedule_widget_rounding)
        self._refresh_provider_hint()

    def _schedule_widget_rounding(self) -> None:
        """Clip the actual Windows window, not an inner frame, to a capsule."""
        if sys.platform != "win32" or self._round_region_after is not None:
            return
        # Page switches cause a burst of geometry work. Apply once on the next
        # frame, then once more after CustomTkinter has updated its scrollable
        # canvas. The second pass matters on high-DPI Windows installations,
        # where the final native client size can arrive after the first event.
        self._round_region_after = self.after(16, self._apply_widget_rounding)
        self.after(160, self._apply_widget_rounding)

    def _apply_widget_rounding(self) -> None:
        self._round_region_after = None
        if sys.platform != "win32" or not self.winfo_exists():
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = self.winfo_id()
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            user32.GetClientRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))
            user32.GetClientRect.restype = wintypes.BOOL
            user32.SetWindowRgn.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL)
            user32.SetWindowRgn.restype = ctypes.c_int
            gdi32.CreateRoundRectRgn.argtypes = (ctypes.c_int,) * 6
            gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
            gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
            gdi32.DeleteObject.restype = wintypes.BOOL

            # GetClientRect is in the exact coordinate space SetWindowRgn
            # expects. winfo_width() can be DPI-virtualized on another PC.
            bounds = wintypes.RECT()
            if not user32.GetClientRect(hwnd, ctypes.byref(bounds)):
                return
            width = bounds.right - bounds.left
            height = bounds.bottom - bounds.top
            if width <= 0 or height <= 0:
                return
            diameter = 36 if self._compact_mode else 44
            region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, diameter, diameter)
            if region:
                # Windows owns the region after a successful SetWindowRgn.
                if not user32.SetWindowRgn(hwnd, region, True):
                    # On failure Windows does not own the GDI region.
                    gdi32.DeleteObject(region)
        except (AttributeError, OSError):
            # The regular rectangular window remains functional on non-Windows
            # or restricted desktop environments.
            pass

    def _make_draggable(self, *widgets: tk.Misc) -> None:
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
            widget.bind("<B1-Motion>", self._drag_window, add="+")

    def _start_window_drag(self, event: tk.Event[tk.Misc]) -> None:
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()
        self._drag_active = True

    def _drag_window(self, event: tk.Event[tk.Misc]) -> None:
        if not self._drag_active:
            return

        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        self.geometry(f"+{x}+{y}")

    def _stop_window_drag(self, _event: tk.Event[tk.Misc]) -> None:
        self._drag_active = False

    def _is_resize_corner(self, event: tk.Event[tk.Misc]) -> bool:
        """Return whether a pointer event is in the invisible resize corner."""
        if self._compact_mode:
            return False
        right = self.winfo_rootx() + self.winfo_width()
        bottom = self.winfo_rooty() + self.winfo_height()
        return (
            event.x_root >= right - self._resize_hit_size
            and event.y_root >= bottom - self._resize_hit_size
            and event.x_root <= right
            and event.y_root <= bottom
        )

    def _update_resize_cursor(self, event: tk.Event[tk.Misc]) -> None:
        """Expose a native cursor hint without adding a visible resize handle."""
        cursor = "size_nw_se" if self._is_resize_corner(event) else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)

    def _maybe_start_window_resize(self, event: tk.Event[tk.Misc]) -> None:
        if self._is_resize_corner(event):
            self._start_window_resize(event)

    def _start_window_resize(self, event: tk.Event[tk.Misc]) -> None:
        self._resize_origin_x = event.x_root
        self._resize_origin_y = event.y_root
        self._resize_origin_width = self.winfo_width()
        self._resize_origin_height = self.winfo_height()
        self._resize_origin_scale = self._widget_scale
        self._resize_aspect_ratio = self._resize_origin_width / max(self._resize_origin_height, 1)
        self._resize_active = True
        self._user_resized_window = True

    def _resize_window(self, event: tk.Event[tk.Misc]) -> None:
        if not self._resize_active or self._compact_mode:
            return
        delta_x = event.x_root - self._resize_origin_x
        delta_y = event.y_root - self._resize_origin_y
        factor_x = (self._resize_origin_width + delta_x) / self._resize_origin_width
        factor_y = (self._resize_origin_height + delta_y) / self._resize_origin_height
        relative_scale = factor_x if abs(factor_x - 1) >= abs(factor_y - 1) else factor_y
        target_scale = min(
            self._maximum_widget_scale,
            max(self._minimum_widget_scale, self._resize_origin_scale * relative_scale),
        )
        base_width = self._resize_origin_width / self._resize_origin_scale
        base_height = self._resize_origin_height / self._resize_origin_scale
        width = round(base_width * target_scale)
        height = round(base_height * target_scale)
        # Keep the bottom edge reachable on compact notebook screens.
        maximum_height = self.winfo_vrootheight() - 24
        if height > maximum_height:
            height = maximum_height
            width = round(height * self._resize_aspect_ratio)
        self._pending_resize_geometry = (width, height, target_scale)
        if self._resize_apply_after is None:
            # CTk must redraw every control for a proportional scale change.
            # A 30 fps cap keeps the drag responsive without layout tearing.
            self._resize_apply_after = self.after(33, self._apply_pending_resize)

    def _apply_pending_resize(self) -> None:
        self._resize_apply_after = None
        target_geometry = self._pending_resize_geometry
        self._pending_resize_geometry = None
        if target_geometry is None or not self._resize_active:
            return
        width, height, target_scale = target_geometry
        self._set_widget_scale(target_scale)
        self._set_resized_widget_geometry(width, height, self.winfo_x(), self.winfo_y())

    def _stop_window_resize(self, _event: tk.Event[tk.Misc]) -> None:
        if not self._resize_active:
            return
        if self._resize_apply_after is not None:
            self.after_cancel(self._resize_apply_after)
            self._resize_apply_after = None
        if self._pending_resize_geometry is not None:
            self._apply_pending_resize()
        self._resize_active = False
        self.after_idle(self._apply_page_minimum)

    def _minimize_widget(self) -> None:
        """Collapse into the fixed, always-on-top recording label."""
        if self._compact_mode:
            return
        self._full_widget_geometry = self.geometry()
        self._full_widget_scale = self._widget_scale
        full_x, full_y = self.winfo_x(), self.winfo_y()
        full_width = self.winfo_width()
        self._compact_mode = True
        self._drag_active = False
        self._resize_active = False
        self._buttons.pack_forget()
        self._window_surface.pack_forget()
        self._set_widget_scale(1.0)
        # Scaling a CTk window temporarily locks its current maximum size.
        # Release that lock before applying the compact geometry.
        self.maxsize(10_000, 10_000)
        self.minsize(self._compact_width, self._compact_height)
        self._compact_surface.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._place_compact_widget(
            *(self._compact_position or (full_x + max(0, (full_width - self._compact_width) // 2), full_y + 12))
        )
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self._refresh_compact_controls()

    def _place_compact_widget(self, x: int, y: int) -> None:
        """Place the movable compact label while keeping it reachable on screen."""
        width, height = self._compact_width, self._compact_height
        left, top = self.winfo_vrootx(), self.winfo_vrooty()
        right = left + self.winfo_vrootwidth()
        bottom = top + self.winfo_vrootheight()
        safe_x = min(max(x, left + 10), max(left + 10, right - width - 10))
        safe_y = min(max(y, top + 10), max(top + 10, bottom - height - 10))
        self._compact_position = (safe_x, safe_y)
        self.geometry(f"{width}x{height}+{safe_x}+{safe_y}")
        self._schedule_widget_rounding()

    def _start_compact_drag(self, event: tk.Event[tk.Misc]) -> None:
        if not self._compact_mode:
            return
        self._compact_drag_origin = (event.x_root, event.y_root)
        self._compact_drag_window_origin = (self.winfo_x(), self.winfo_y())
        self._compact_drag_active = True
        self._compact_drag_moved = False

    def _drag_compact_widget(self, event: tk.Event[tk.Misc]) -> None:
        if not self._compact_drag_active:
            return
        origin_x, origin_y = self._compact_drag_origin
        delta_x, delta_y = event.x_root - origin_x, event.y_root - origin_y
        if abs(delta_x) >= 5 or abs(delta_y) >= 5:
            self._compact_drag_moved = True
        if self._compact_drag_moved:
            window_x, window_y = self._compact_drag_window_origin
            self._place_compact_widget(window_x + delta_x, window_y + delta_y)

    def _stop_compact_drag(self, _event: tk.Event[tk.Misc]) -> None:
        if not self._compact_drag_active:
            return
        restore = not self._compact_drag_moved
        self._compact_drag_active = False
        if restore:
            self._restore_full_widget()

    def _restore_full_widget(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Return from the recording label to the exact full widget state."""
        if not self._compact_mode:
            return
        geometry = self._full_widget_geometry or f"560x{self._main_widget_height}"
        full_scale = self._full_widget_scale
        self._compact_surface.pack_forget()
        # Keep the full widget's silhouette identical to its initial state.
        self._window_surface.pack(fill=tk.BOTH, expand=True)
        if self._current_page == "record":
            self._buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
        self.maxsize(10_000, 10_000)
        self.minsize(self._active_min_width, self._active_min_height)
        self.geometry(geometry)
        self._set_widget_scale(full_scale)
        self._compact_mode = False
        self._schedule_widget_rounding()
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after_idle(self._apply_page_minimum)

    def _refresh_compact_controls(self) -> None:
        """Keep compact status and actions truthful without opening the widget."""
        if not self._compact_mode:
            return
        recording = self._service is not None and self._service.state == RecordingState.RECORDING
        finalizing = self._stop_thread is not None and self._stop_thread.is_alive()
        processing = self._pipeline_thread is not None and self._pipeline_thread.is_alive()
        if recording:
            label, color = f"GRAVANDO  {self.elapsed.get()}", _COLORS["success"]
        elif finalizing:
            label, color = "FINALIZANDO GRAVAÇÃO", _COLORS["warning"]
        elif processing:
            label, color = "PROCESSANDO ÁUDIO", _COLORS["accent"]
        elif "error" in self.status.get().casefold() or "falhou" in self.status.get().casefold():
            label, color = "ATENÇÃO NECESSÁRIA", _COLORS["danger"]
        else:
            label, color = "PRONTO PARA GRAVAR", _COLORS["success"]
        self._compact_status.set(label)
        self._compact_indicator.configure(fg_color=color)
        self.compact_start_button.configure(state=tk.DISABLED if recording or finalizing or processing else tk.NORMAL)
        self.compact_stop_button.configure(state=tk.NORMAL if recording else tk.DISABLED)

    def _hide_to_tray(self) -> None:
        """Remove the widget from the desktop while keeping its tray controls."""
        if not self._tray_available:
            # Keep a reachable window if Windows could not expose the tray icon.
            self.iconify()
            return
        self.withdraw()

    def _show_widget(self) -> None:
        """Restore and focus the widget after a notification-area action."""
        self.deiconify()
        self._restore_full_widget()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()

    def _restore_borderless_after_minimize(self, _event: tk.Event[tk.Misc]) -> None:
        if not self._restore_borderless_on_map:
            return

        self.after_idle(self._restore_borderless)

    def _restore_borderless(self) -> None:
        if self._restore_borderless_on_map and self.state() != "iconic":
            self.overrideredirect(True)
            self._restore_borderless_on_map = False
            self._schedule_widget_rounding()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or ".")
        if selected:
            self.output_dir.set(selected)

    def _set_capture_preferences_state(self, state: str) -> None:
        for button in self._source_buttons:
            button.configure(state=state)
        self.recording_output_selector.configure(state="readonly" if state == tk.NORMAL else state)
        self.output_entry.configure(state=state)
        self.output_browse_button.configure(state=state)
        self.recording_limit_entry.configure(state=state)
        self.recording_limit_selector.configure(state="readonly" if state == tk.NORMAL else state)

    def _set_summary_template_state(self, state: str) -> None:
        combobox_state = "readonly" if state == tk.NORMAL else state
        self.template_selector.configure(state=combobox_state)
        self.youtube_template_selector.configure(state=combobox_state)
        self.profile_selector.configure(state=combobox_state)
        self.youtube_profile_selector.configure(state=combobox_state)

    def _set_navigation_state(self, state: str) -> None:
        for button in self._page_buttons.values():
            button.configure(state=state)

    def _apply_page_minimum(self) -> None:
        """Keep the shell usable without allowing a page to grow it off-screen."""
        if self._compact_mode:
            return
        self.update_idletasks()
        # Geometry is physical pixels. Controls already include widget scale,
        # so keep the shell's minimum size in the same coordinate system.
        scale = max(self._widget_scale, 0.01)
        self._active_min_width = max(
            round(self._min_widget_width * scale),
            self._window_surface.winfo_reqwidth() + 20,
        )
        # A CTkScrollableFrame owns page overflow.  Its requested height is
        # intentionally not promoted to the window minimum: doing that made
        # longer pages push the rounded bottom edge off small notebook screens.
        self._active_min_height = round(self._min_widget_height * scale)
        self.minsize(self._active_min_width, self._active_min_height)
        current_width = self.winfo_width()
        current_height = self.winfo_height()
        if self._user_resized_window:
            width = max(current_width, self._active_min_width)
            height = max(current_height, self._active_min_height)
        else:
            # Before the user takes control, each destination gets a compact
            # preferred size. Closing an editor therefore gives space back
            # instead of leaving the widget unnecessarily large.
            width = max(self._preferred_widget_width, self._active_min_width)
            height = max(self._main_widget_height, self._active_min_height)
        if (width, height) != (current_width, current_height):
            self._set_widget_geometry(width, height, self.winfo_x(), self.winfo_y())
        self._schedule_content_scrollbar()

    def _schedule_content_scrollbar(self) -> None:
        """Show a scrollbar only when the current page actually overflows."""
        if self._content_scrollbar_after is None:
            # Let CustomTkinter finish its canvas scroll-region calculation.
            self._content_scrollbar_after = self.after(24, self._update_content_scrollbar)

    def _update_content_scrollbar(self) -> None:
        self._content_scrollbar_after = None
        try:
            first, last = self._container._parent_canvas.yview()
            if last - first >= 0.999:
                self._container._scrollbar.grid_remove()
            else:
                self._container._scrollbar.grid()
        except tk.TclError:
            # The widget may be closing while a deferred layout pass runs.
            pass

    def _set_widget_geometry(self, width: int, height: int, x: int, y: int) -> None:
        """Apply geometry while keeping an expanded borderless widget reachable."""
        margin = 12
        left = self.winfo_vrootx()
        top = self.winfo_vrooty()
        right = left + self.winfo_vrootwidth()
        bottom = top + self.winfo_vrootheight()
        safe_x = min(max(x, left), max(left, right - width - margin))
        safe_y = min(max(y, top), max(top, bottom - height - margin))
        self.geometry(f"{width}x{height}+{safe_x}+{safe_y}")
        self._schedule_widget_rounding()

    def _set_resized_widget_geometry(self, width: int, height: int, x: int, y: int) -> None:
        """Set physical geometry without CTk's transient scale-time size lock."""
        margin = 12
        left, top = self.winfo_vrootx(), self.winfo_vrooty()
        right = left + self.winfo_vrootwidth()
        bottom = top + self.winfo_vrootheight()
        safe_x = min(max(x, left), max(left, right - width - margin))
        safe_y = min(max(y, top), max(top, bottom - height - margin))
        # CTk.geometry() converts through its window-scaling state. During a
        # live scale that conversion can pin the shell to its previous size.
        # Tk.geometry() works with the actual pixels already measured above.
        tk.Tk.geometry(self, f"{width}x{height}+{safe_x}+{safe_y}")
        self._schedule_widget_rounding()

    def _set_widget_scale(self, scale: float) -> None:
        """Scale controls and shell together without CTk window scaling."""
        if abs(scale - self._widget_scale) < 0.01:
            return
        self._widget_scale = scale
        ctk.set_widget_scaling(scale)
        # CTk briefly locks the toplevel while recalculating widgets. Geometry
        # is applied directly after this call, so only release the native max.
        tk.Tk.maxsize(self, 10_000, 10_000)
        if hasattr(self, "library_listbox"):
            self.library_listbox.configure(font=("Segoe UI", max(8, round(10 * scale))))

    def _show_page(self, page: str) -> None:
        """Show one direct destination in the widget; pages never nest."""
        if page not in self._page_layouts:
            raise ValueError(f"Página desconhecida: {page}")
        if self._library_open and page != "library" and not self._close_transcript_editor():
            return
        # The recording page has its own fixed action bar, so it needs the
        # extra vertical room. Other destinations use this lower inset to keep
        # the scroll canvas clear of the native rounded window corners.
        bottom_inset = 4 if page == "record" else 20
        self._container._parent_frame.pack_configure(pady=(0, bottom_inset))
        for layouts in self._page_layouts.values():
            for widget, _options in layouts:
                widget.pack_forget()
        for widget, options in self._page_layouts[page]:
            # Reserve a row between the two recording cards only when there is
            # actual device information to show.  An empty label previously
            # created an unexplained visual gap in the primary workflow.
            if widget is self.device_info_label and not self.device_info_text.get().strip():
                continue
            widget.pack(**options)
        # Destinations always open at their first field.  Without this reset a
        # tall previous page could leave a newly selected page scrolled to an
        # apparently empty lower section.
        self._container._parent_canvas.yview_moveto(0)

        page_titles = {
            "record": ("Gravar", "Configure a captura e inicie quando estiver pronto."),
            "file": ("Arquivo", "Importe uma gravação já existente"),
            "youtube": ("YouTube", "Importe um vídeo autorizado para transcrever"),
            "library": ("Biblioteca", "Encontre, revise e retome seus resultados"),
            "settings": ("Ajustes", "Defina como o Voice Notes deve processar"),
        }
        title, hint = page_titles[page]
        self._header_title.configure(text=title)
        self._header_drag_hint.configure(text=hint)
        for key, button in self._page_buttons.items():
            active = key == page
            button.configure(
                fg_color="#314B70" if active else "transparent",
                text_color=_COLORS["text"] if active else _COLORS["muted"],
            )
        self._current_page = page
        self._settings_open = page == "settings"
        self._youtube_open = page == "youtube"
        self._library_open = page == "library"
        if page == "library":
            self._refresh_library()
        if page == "settings":
            self._show_settings_section(getattr(self, "_active_settings_section", "provider"))
        self._schedule_widget_rounding()
        self.after_idle(self._apply_page_minimum)

    def _on_device_info_changed(self, *_: object) -> None:
        """Add or remove the device row without leaving a blank spacer."""
        if getattr(self, "_current_page", None) != "record":
            return
        self.after_idle(self._sync_recording_device_row)

    def _sync_recording_device_row(self) -> None:
        try:
            should_show = bool(self.device_info_text.get().strip())
            is_visible = bool(self.device_info_label.winfo_manager())
            if should_show != is_visible:
                self._show_page("record")
        except tk.TclError:
            # The application may be closing while the deferred state refresh
            # is waiting in Tk's event queue.
            return

    def _show_recording_page(self) -> None:
        self._show_page("record")

    def _show_file_import(self) -> None:
        self._show_page("file")

    def _toggle_youtube(self) -> None:
        self._show_page("youtube")

    def _toggle_settings(self) -> None:
        self._show_page("settings")

    def _show_settings_section(self, section: str) -> None:
        if section not in self._settings_sections:
            raise ValueError(f"Seção de ajustes desconhecida: {section}")
        for panel in self._settings_sections.values():
            panel.pack_forget()
        self._settings_sections[section].pack(fill=tk.X, padx=0, pady=(0, 4))
        for key, button in self._settings_section_buttons.items():
            active = key == section
            button.configure(
                fg_color="#314B70" if active else "transparent",
                text_color=_COLORS["text"] if active else _COLORS["muted"],
            )
        self._active_settings_section = section
        if getattr(self, "_current_page", None) == "settings":
            self.after_idle(self._apply_page_minimum)

    def _toggle_api_provider_form(self) -> None:
        """Keep advanced API fields out of sight until the user explicitly needs them."""
        if self._api_provider_open:
            self.api_card.pack_forget()
            self.new_provider_button.configure(text="+ Novo Provider")
        else:
            self.api_card.pack(fill=tk.X, padx=14, pady=(0, 10), before=self._api_form_anchor)
            self.new_provider_button.configure(text="− Ocultar novo provider")
        self._api_provider_open = not self._api_provider_open
        self.after_idle(self._apply_page_minimum)

    def _toggle_api_advanced(self) -> None:
        """Keep uncommon custom-JSON fields out of the standard token flow."""
        if self._api_advanced_open:
            self.api_advanced_card.pack_forget()
            self.api_advanced_button.configure(text="Opções avançadas")
        else:
            self.api_advanced_card.pack(fill=tk.X, padx=10, pady=(2, 5), before=self.api_advanced_button)
            self.api_advanced_button.configure(text="Ocultar opções avançadas")
        self._api_advanced_open = not self._api_advanced_open
        self.after_idle(self._apply_page_minimum)

    def _save_api_provider(self) -> None:
        from record_transcript_resume.api_provider import ApiProviderConfig, save_config
        if not self.api_token.get().strip():
            messagebox.showerror("Token ausente", "Cole o token da API antes de salvar o provider.")
            return
        try:
            save_config(
                ApiProviderConfig(
                    name=self.api_provider_name.get().strip() or "Minha API",
                    protocol=self.api_protocol.get(),
                    base_url=self.api_base_url.get().strip(),
                    model=self.api_model.get().strip(),
                    auth_header=self.api_auth_header.get().strip(),
                    auth_prefix=self.api_auth_prefix.get(),
                    request_template=self.api_request_template.get("1.0", "end").strip(),
                    response_path=self.api_response_path.get().strip(),
                ),
                self.api_token.get(),
            )
        except Exception as exc:
            messagebox.showerror("Não foi possível salvar", str(exc))
            return
        self.api_token.set("")
        self.provider_hint.set(f"Resumo por {self.api_provider_name.get().strip() or 'API'} · token salvo")
        self.summary_provider.set("API por token")
        self._toggle_api_provider_form()
        messagebox.showinfo("Provider salvo", "Provider salvo. O token foi guardado no Cofre de Credenciais do Windows.")

    def _toggle_library(self) -> None:
        self._show_page("library")

    def _refresh_library(self) -> None:
        self._library_items = discover_recordings(Path(self.output_dir.get() or default_output_dir()))
        pending = [job for job in self._job_store.list() if job.status in {"queued", "running", "failed", "needs_attention"}]
        if not pending:
            self.queue_hint.set("Fila vazia")
            self.retry_queue_button.configure(state=tk.DISABLED)
        else:
            failed = sum(job.status in {"failed", "needs_attention"} for job in pending)
            if failed:
                self.queue_hint.set(f"{failed} tarefa(s) exigem atenção")
            else:
                self.queue_hint.set(f"{len(pending)} tarefa(s) aguardando processamento")
            self.retry_queue_button.configure(state=tk.NORMAL)
        self._render_library_list()

    def _retry_pending_jobs(self) -> None:
        resumable: list[ProcessingJob] = []
        for job in self._job_store.list():
            if job.status not in {"queued", "failed", "needs_attention"} or not job.audio_path.is_file():
                continue
            refreshed = self._job_store.update(job.id, status="queued", stage="Na fila", error="")
            if refreshed is not None:
                resumable.append(refreshed)
        if not resumable:
            messagebox.showinfo("Fila", "Não há áudio disponível para retomar. Verifique a pasta da gravação na biblioteca.")
            self._refresh_library()
            return
        known_ids = {job.id for job in self._pending_jobs}
        self._pending_jobs.extend(job for job in resumable if job.id not in known_ids)
        self._run_next_pending_job()
        self._refresh_library()

    def _render_library_list(self) -> None:
        if not hasattr(self, "library_listbox"):
            return
        query = self.library_search.get().strip().casefold()
        self._library_visible_items = [
            item for item in self._library_items
            if not query or query in item.searchable_text
        ]
        self.library_listbox.delete(0, tk.END)
        for item in self._library_visible_items:
            marker = "✓" if item.summary_available else ("•" if item.transcript_path is None and item.summary_path is None else "!")
            stamp = item.modified_at.strftime("%d/%m %H:%M")
            title = item.title.strip()
            if len(title) > 46:
                title = f"{title[:45].rstrip()}…"
            self.library_listbox.insert(tk.END, f"{marker}  {title}  ·  {stamp}")
        if not self._library_visible_items:
            self.library_detail.set("Nenhuma gravação encontrada nesta pasta. Escolha outro local em Salvar em ou grave algo novo.")

    def _selected_library_item(self) -> LibraryItem | None:
        selected = self.library_listbox.curselection()
        if not selected:
            return None
        index = int(selected[0])
        if index >= len(self._library_visible_items):
            return None
        return self._library_visible_items[index]

    def _on_library_select(self, _event: object = None) -> None:
        item = self._selected_library_item()
        if item is None:
            return
        summary_state = (
            "resumo pronto" if item.summary_available
            else "somente áudio salvo" if item.transcript_path is None and item.summary_path is None
            else "resumo pendente ou com falha"
        )
        self.library_detail.set(f"{item.folder.name} · {summary_state}")
        self.last_file.set(str(item.mp3_path or item.folder))

    def _open_selected_folder(self) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        try:
            os.startfile(str(item.folder))
        except AttributeError:
            subprocess.Popen(["explorer", str(item.folder)])
        except OSError as exc:
            messagebox.showerror("Não foi possível abrir", str(exc))

    def _export_selected_document(self, document_format: str) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        source = self._editor_document_path if self._library_editing else (item.summary_path or item.transcript_path)
        if source is None:
            messagebox.showinfo("Documento indisponível", "Esta gravação ainda não possui resumo ou transcrição para exportar.")
            return
        extension = ".docx" if document_format == "docx" else ".pdf"
        selected = filedialog.asksaveasfilename(
            title=f"Exportar {source.stem}",
            initialfile=f"{item.title}{extension}",
            defaultextension=extension,
            filetypes=[("Documento Word", "*.docx")] if document_format == "docx" else [("Documento PDF", "*.pdf")],
        )
        if not selected:
            return
        try:
            if document_format == "docx":
                from record_transcript_resume.exports import export_docx

                destination = export_docx(source, Path(selected))
            else:
                from record_transcript_resume.exports import export_pdf

                destination = export_pdf(source, Path(selected))
        except Exception as exc:
            messagebox.showerror("Não foi possível exportar", str(exc))
            return
        self.status.set(f"Exportado: {destination.name}")

    def _edit_selected_transcript(self) -> None:
        item = self._selected_library_item()
        if item is None or item.transcript_path is None:
            messagebox.showinfo("Transcrição indisponível", "Esta gravação ainda não tem uma transcrição para editar.")
            return
        self._open_library_document(item.transcript_path, "TRANSCRIÇÃO · EDITE, SALVE OU GERE UM NOVO RESUMO", is_transcript=True)

    def _open_selected_summary(self) -> None:
        item = self._selected_library_item()
        if item is None or item.summary_path is None:
            messagebox.showinfo("Resumo indisponível", "Esta gravação ainda não tem um resumo para abrir.")
            return
        self._open_library_document(item.summary_path, "RESUMO · EDITE E SALVE DIRETAMENTE NO APP", is_transcript=False)

    def _open_library_document(self, path: Path, title: str, *, is_transcript: bool) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Não foi possível abrir", str(exc))
            return
        if not self._close_transcript_editor():
            return
        self.library_editor_title.set(title)
        self._editor_document_path = path
        self._editor_is_transcript = is_transcript
        self._editor_dirty = False
        self.editor_save_state.set("Salvo")
        window = ctk.CTkToplevel(self)
        self._library_document_window = window
        window.title("Voice Notes · Documento")
        window.configure(fg_color=_COLORS["bg"])
        window.geometry("860x680")
        window.minsize(640, 500)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_transcript_editor)

        shell = ctk.CTkFrame(window, fg_color=_COLORS["surface"], corner_radius=16)
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            shell, textvariable=self.library_editor_title, font=("Segoe UI", 11, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 3))
        editor_meta = ctk.CTkFrame(shell, fg_color="transparent")
        editor_meta.pack(fill=tk.X, padx=16, pady=(0, 10))
        ctk.CTkLabel(
            editor_meta, text=path.name, font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        self.editor_save_state_label = ctk.CTkLabel(
            editor_meta, textvariable=self.editor_save_state, font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="e",
        )
        self.editor_save_state_label.pack(side=tk.RIGHT)
        self.transcript_editor = ctk.CTkTextbox(
            shell, corner_radius=10, fg_color="#080C16", border_width=1,
            border_color="#2A3A58", text_color=_COLORS["text"], font=("Consolas", 11), wrap="word",
        )
        self.transcript_editor.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        self._library_editing = True
        self.transcript_editor.insert("1.0", content)
        self._configure_markdown_tags()
        self._apply_markdown_highlighting()
        editor_text = self.transcript_editor._textbox
        editor_text.edit_modified(False)
        editor_text.bind("<<Modified>>", self._on_editor_text_modified, add="+")
        editor_actions = ctk.CTkFrame(shell, fg_color="transparent")
        editor_actions.pack(fill=tk.X, padx=16, pady=(0, 14))
        self.library_suggest_names_button = ctk.CTkButton(
            editor_actions, text="Sugerir nomes", command=self._suggest_speaker_names,
            width=110, height=34, corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_suggest_names_button.pack(side=tk.LEFT)
        ctk.CTkButton(
            editor_actions, text="Fechar", command=self._close_transcript_editor,
            width=82, height=34, corner_radius=9, fg_color="#263550", hover_color="#34476B",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        self.library_save_button = ctk.CTkButton(
            editor_actions, text="Salvar", command=self._save_open_document,
            width=76, height=34, corner_radius=9, fg_color="#244462", hover_color="#315A80",
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_save_button.pack(side=tk.RIGHT, padx=(0, 7))
        self.library_regenerate_button = ctk.CTkButton(
            editor_actions, text="Salvar e gerar resumo", command=self._save_transcript_and_regenerate,
            height=34, corner_radius=9, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color="#FFFFFF", font=("Segoe UI", 10, "bold"),
        )
        if is_transcript:
            self.library_regenerate_button.pack(side=tk.RIGHT, padx=(0, 7))
        self.library_suggest_names_button.configure(state=tk.NORMAL if is_transcript else tk.DISABLED)
        window.bind("<Control-s>", self._save_open_document_shortcut, add="+")
        window.after(50, window.focus_force)

    def _configure_markdown_tags(self) -> None:
        """Make Markdown structure scannable while retaining editable source."""
        editor = self.transcript_editor._textbox
        editor.tag_configure("markdown_h1", foreground="#C7BDFF", font=("Consolas", 14, "bold"), spacing1=12, spacing3=6)
        editor.tag_configure("markdown_h2", foreground="#9FC7FF", font=("Consolas", 12, "bold"), spacing1=10, spacing3=4)
        editor.tag_configure("markdown_h3", foreground="#B8C8E8", font=("Consolas", 11, "bold"), spacing1=8, spacing3=3)
        editor.tag_configure("markdown_bold", foreground="#FFFFFF", font=("Consolas", 11, "bold"))
        editor.tag_configure("markdown_bullet", foreground="#B8C8E8")

    def _schedule_markdown_highlighting(self) -> None:
        if self._editor_highlight_after is not None:
            self.after_cancel(self._editor_highlight_after)
        self._editor_highlight_after = self.after(140, self._apply_markdown_highlighting)

    def _apply_markdown_highlighting(self) -> None:
        self._editor_highlight_after = None
        if not getattr(self, "_library_editing", False):
            return
        editor = self.transcript_editor._textbox
        tags = ("markdown_h1", "markdown_h2", "markdown_h3", "markdown_bold", "markdown_bullet")
        for tag in tags:
            editor.tag_remove(tag, "1.0", tk.END)
        line_count = int(editor.index("end-1c").split(".")[0])
        for number in range(1, line_count + 1):
            start = f"{number}.0"
            end = f"{number}.end"
            line = editor.get(start, end)
            if line.startswith("# "):
                editor.tag_add("markdown_h1", start, end)
            elif line.startswith("## "):
                editor.tag_add("markdown_h2", start, end)
            elif line.startswith("### "):
                editor.tag_add("markdown_h3", start, end)
            elif re.match(r"^\s*(?:[-*+] |\d+\. )", line):
                editor.tag_add("markdown_bullet", start, end)
            for match in re.finditer(r"\*\*[^*]+\*\*", line):
                editor.tag_add("markdown_bold", f"{number}.{match.start()}", f"{number}.{match.end()}")

    def _set_editor_save_state(self, state: str) -> None:
        states = {
            "dirty": ("Alterações não salvas", _COLORS["warning"]),
            "saving": ("Salvando…", "#9FC7FF"),
            "saved_now": ("Salvo agora", _COLORS["success"]),
            "saved": ("Salvo", _COLORS["muted"]),
            "error": ("Não foi possível salvar", _COLORS["danger"]),
        }
        text, color = states[state]
        self.editor_save_state.set(text)
        if self.editor_save_state_label is not None:
            self.editor_save_state_label.configure(text_color=color)
        if hasattr(self, "library_save_button"):
            self.library_save_button.configure(
                text="Salvando…" if state == "saving" else "Salvar",
                state=tk.DISABLED if state == "saving" else tk.NORMAL,
            )

    def _on_editor_text_modified(self, *_: object) -> None:
        if not getattr(self, "_library_editing", False):
            return
        editor = self.transcript_editor._textbox
        if not editor.edit_modified():
            return
        editor.edit_modified(False)
        self._editor_dirty = True
        self._set_editor_save_state("dirty")
        self._schedule_markdown_highlighting()

    def _save_open_document_shortcut(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        self._save_open_document()
        return "break"

    def _close_transcript_editor(self) -> bool:
        if not getattr(self, "_library_editing", False):
            return True
        if self._editor_dirty and not messagebox.askyesno(
            "Alterações não salvas",
            "Este documento tem alterações não salvas. Fechar mesmo assim?",
        ):
            return False
        if self._editor_highlight_after is not None:
            self.after_cancel(self._editor_highlight_after)
            self._editor_highlight_after = None
        window = self._library_document_window
        self._library_document_window = None
        if window is not None and window.winfo_exists():
            window.destroy()
        self._library_editor.pack_forget()
        self._editor_document_path = None
        self._editor_is_transcript = False
        self._editor_dirty = False
        self.editor_save_state_label = None
        self._library_editing = False
        self.after_idle(self._apply_page_minimum)
        return True

    def _save_open_document(self) -> bool:
        path = self._editor_document_path
        if path is None:
            messagebox.showerror("Documento indisponível", "Abra uma transcrição ou resumo antes de salvar.")
            return False
        content = self.transcript_editor.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showerror("Documento vazio", "Escreva ou mantenha algum conteúdo antes de salvar.")
            return False
        self._set_editor_save_state("saving")
        self.update_idletasks()
        try:
            path.write_text(content + "\n", encoding="utf-8")
        except OSError as exc:
            self._set_editor_save_state("error")
            messagebox.showerror("Não foi possível salvar", str(exc))
            return False
        self._editor_dirty = False
        self.transcript_editor._textbox.edit_modified(False)
        self._set_editor_save_state("saved_now")
        self.status.set("Documento salvo")
        self._refresh_library()
        self.after(3500, self._settle_editor_saved_state)
        return True

    def _settle_editor_saved_state(self) -> None:
        if getattr(self, "_library_editing", False) and not self._editor_dirty:
            self._set_editor_save_state("saved")

    def _save_transcript_and_regenerate(self) -> None:
        transcript_path = self._editor_document_path
        if transcript_path is None or not self._editor_is_transcript:
            messagebox.showerror("Transcrição indisponível", "Selecione uma transcrição válida na biblioteca.")
            return
        if not self._save_open_document():
            return
        self._close_transcript_editor()
        self._start_summary_retry(transcript_path)

    def _suggest_speaker_names(self) -> None:
        if not self._editor_is_transcript:
            return
        from record_transcript_resume.speaker_names import apply_speaker_names, suggest_speaker_names

        content = self.transcript_editor.get("1.0", "end-1c")
        suggestions = suggest_speaker_names(content)
        if not suggestions:
            messagebox.showinfo(
                "Nenhum nome confirmado",
                "Ainda não encontrei uma autoapresentação explícita, como “eu sou João”. "
                "Por segurança, o app não tenta adivinhar nomes pela voz.",
            )
            return
        details = "\n".join(f"• {item.speaker} → {item.name} ({item.reason})" for item in suggestions)
        if not messagebox.askyesno("Aplicar sugestões de nomes", f"Encontrei estas sugestões:\n\n{details}\n\nAplicar no texto aberto?"):
            return
        self.transcript_editor.delete("1.0", tk.END)
        self.transcript_editor.insert("1.0", apply_speaker_names(content, suggestions))
        self.status.set("Sugestões aplicadas · salve para confirmar")

    def _regenerate_selected_summary(self) -> None:
        item = self._selected_library_item()
        if item is None or item.transcript_path is None:
            messagebox.showinfo("Transcrição indisponível", "Esta gravação ainda não tem transcrição para resumir.")
            return
        self._start_summary_retry(item.transcript_path)

    def _start_recording(self) -> None:
        try:
            limit_seconds = self._recording_timer_seconds(
                self.recording_limit_value.get(), self.recording_limit_unit.get()
            )
        except ValueError as exc:
            messagebox.showerror("Tempo inválido", str(exc))
            return
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
            messagebox.showerror("Insufficient disk space", str(exc))
            self.status.set("Insufficient disk space")
            return
        except RecordingError as exc:
            messagebox.showerror("Could not start recording", str(exc))
            self.status.set("Error starting recording")
            return
        except OSError as exc:
            messagebox.showerror("Invalid folder", str(exc))
            self.status.set("Error in output folder")
            return

        self._service = service
        self._started_at = time.monotonic()
        self._recording_deadline = self._started_at + limit_seconds if limit_seconds else None
        self._last_output = output_path
        self.status.set("Recording")
        if limit_seconds:
            self.recording_limit_hint.set(f"Parada automática em {self._format_duration(limit_seconds)}")
        else:
            self.recording_limit_hint.set("Sem parada automática")
        self.last_file.set(str(output_path))
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._refresh_compact_controls()
        self.process_button.configure(state=tk.DISABLED)
        self.retry_summary_button.configure(state=tk.DISABLED)
        self.youtube_process_button.configure(state=tk.DISABLED)
        self.provider_selector.configure(state=tk.DISABLED)
        self._set_summary_template_state(tk.DISABLED)
        self._set_navigation_state(tk.DISABLED)
        self._set_capture_preferences_state(tk.DISABLED)
        self._update_device_info()

    def _stop_recording(self, automatic: bool = False) -> None:
        from record_transcript_resume.log import log
        if self._service is None or self._service.state != RecordingState.RECORDING:
            log("GUI: _stop_recording skipped (service None or not recording)")
            return
        log("GUI: _stop_recording chamado — iniciando worker thread")
        self._started_at = None
        self._recording_deadline = None
        self.stop_button.configure(state=tk.DISABLED)
        self.status.set("Tempo concluído · finalizando..." if automatic else "Finalizing...")
        self.recording_limit_hint.set("Sem parada automática")
        self._refresh_compact_controls()
        self._stop_thread = threading.Thread(target=self._stop_recording_worker, daemon=True)
        self._stop_thread.start()

    def _stop_recording_worker(self) -> None:
        from record_transcript_resume.log import log
        log("GUI: _stop_recording_worker iniciado")
        assert self._service is not None
        try:
            output_path = self._service.stop()
        except RecordingError as exc:
            log(f"GUI: service.stop() lancou RecordingError: {exc}")
            self.after(0, self._show_stop_error, str(exc))
            return
        except Exception as exc:
            log(f"GUI: service.stop() lancou excecao inesperada: {type(exc).__name__}: {exc}")
            self.after(0, self._show_stop_error, f"Unexpected error while finalizing: {exc}")
            return
        log(f"GUI: service.stop() OK -> {output_path.name}")
        self.after(0, self._show_completed, output_path)
        log("GUI: after(_show_completed) agendado")

    def _show_stop_error(self, message: str) -> None:
        self.status.set("Error finalizing")
        self.device_info_text.set("")
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.NORMAL)
        self.retry_summary_button.configure(state=tk.NORMAL)
        self.provider_selector.configure(state="readonly")
        self._set_summary_template_state(tk.NORMAL)
        self._set_navigation_state(tk.NORMAL)
        self._set_capture_preferences_state(tk.NORMAL)
        self.recording_limit_hint.set("Sem parada automática")
        messagebox.showerror("Error finalizing", f"{message}\n\n{_log_hint()}")

    def _show_completed(self, output_path: Path) -> None:
        from record_transcript_resume.log import log
        log(f"GUI: _show_completed chamado -> {output_path.name}")
        self.stop_button.configure(state=tk.DISABLED)
        self.device_info_text.set("")
        self._started_at = None
        self._recording_deadline = None
        self.recording_limit_hint.set("Sem parada automática")
        self._last_output = output_path
        self.last_file.set(str(output_path))
        if not output_path.is_file():
            self._show_stop_error(
                "A gravação foi finalizada, mas o arquivo de áudio não foi encontrado na pasta escolhida. "
                "Nenhum processamento será iniciado."
            )
            return
        self.status.set("Áudio salvo com segurança. Preparando a próxima etapa…")
        self._refresh_library()
        output_mode = self.recording_output_mode.get()
        if output_mode == "audio":
            self.status.set("Áudio salvo com segurança. Nenhum processamento foi solicitado.")
            self._restore_after_processing()
            return
        lang_label = self.pipeline_language.get()
        lang_code = _LANG_CODES.get(lang_label, "pt")
        model_size = self.pipeline_model.get()
        provider = _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex")
        summary_template = _SUMMARY_TEMPLATE_CODES.get(self.summary_template.get(), "meeting")
        log(
            f"GUI: áudio preservado antes do pipeline | file={output_path.name} "
            f"mode={output_mode} lang={lang_code} model={model_size} provider={provider}"
        )
        self._queue_pipeline(output_path, lang_code, model_size, provider, summary_template, output_mode=output_mode)

    def _update_device_info(self) -> None:
        if self._service is None:
            self.device_info_text.set("")
            return
        info = self._service.device_info
        parts: list[str] = []
        if "microphone" in info:
            parts.append(f"Mic: {info['microphone']}")
        if "system" in info:
            parts.append(f"System: {info['system']}")
        self.device_info_text.set("  |  ".join(parts) if parts else "")

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _process_youtube(self) -> None:
        """Download authorized YouTube audio off the Tk thread, then queue it."""
        url = self.youtube_url.get().strip()
        if not url:
            messagebox.showerror("Link ausente", "Cole o link de um vídeo do YouTube antes de continuar.")
            return
        from record_transcript_resume.youtube import is_supported_youtube_url
        if not is_supported_youtube_url(url):
            messagebox.showerror("Link inválido", "Use um link válido do youtube.com ou youtu.be.")
            return
        self.youtube_process_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.DISABLED)
        self.retry_summary_button.configure(state=tk.DISABLED)
        self.status.set("Baixando áudio do YouTube...")
        self.youtube_hint.set("Baixando e convertendo para MP3…")
        self.progressbar.pack(fill=tk.X, padx=20, pady=(4, 0))
        self.progressbar.start()
        self._pipeline_thread = threading.Thread(
            target=self._youtube_download_worker,
            args=(url, self.youtube_mode.get(), self.summary_template.get()),
            daemon=True,
        )
        self._pipeline_thread.start()

    def _youtube_download_worker(self, url: str, selected_mode: str, selected_template: str) -> None:
        from record_transcript_resume.log import log
        from record_transcript_resume.youtube import download_audio

        mode_by_label = {
            "Transcrição e resumo": "both",
            "Só transcrição": "transcription",
            "Só resumo": "summary",
        }
        output_mode = mode_by_label.get(selected_mode, "both")
        destination = Path(self.output_dir.get()).expanduser()
        try:
            audio_path = download_audio(
                url,
                destination,
                on_status=lambda message: self.after(0, self.status.set, message),
            )
        except Exception as exc:
            log(f"GUI: download do YouTube falhou: {type(exc).__name__}: {exc}")
            self.after(0, self._on_youtube_download_error, str(exc))
            return
        self.after(0, self._on_youtube_download_done, audio_path, output_mode, selected_template)

    def _on_youtube_download_done(self, audio_path: Path, output_mode: str, selected_template: str) -> None:
        self.youtube_hint.set("Áudio pronto. Iniciando processamento…")
        self._queue_pipeline(
            audio_path,
            _LANG_CODES.get(self.pipeline_language.get(), "pt"),
            self.pipeline_model.get(),
            _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex"),
            _SUMMARY_TEMPLATE_CODES.get(selected_template, "meeting"),
            output_mode=output_mode,
            output_dir=Path(self.output_dir.get()),
        )

    def _on_youtube_download_error(self, message: str) -> None:
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set("Não foi possível baixar o áudio")
        self.youtube_hint.set("Não foi possível baixar. Verifique o link e tente novamente.")
        self._restore_after_processing()
        messagebox.showerror("Download do YouTube não concluído", f"{message}\n\n{_log_hint()}")

    def _process_existing_mp3(self) -> None:
        path = filedialog.askopenfilename(
            title="Importar áudio para transcrever",
            filetypes=[
                ("Arquivos de áudio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma"),
                ("MP3", "*.mp3"),
                ("Todos os arquivos", "*.*"),
            ],
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if not path:
            return
        mp3_path = Path(path)
        label = self.pipeline_language.get()
        lang_code = _LANG_CODES.get(label, "pt")
        model_size = self.pipeline_model.get()
        provider = _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex")
        summary_template = _SUMMARY_TEMPLATE_CODES.get(self.summary_template.get(), "meeting")
        self._queue_pipeline(mp3_path, lang_code, model_size, provider, summary_template)

    def _toggle_text_import(self) -> None:
        if self._text_import_open:
            self._text_import_panel.pack_forget()
            self.text_import_button.configure(text="Colar ou abrir transcrição")
        else:
            self._text_import_panel.pack(fill=tk.X, padx=14, pady=(0, 8), before=self.retry_summary_button)
            self.text_import_button.configure(text="Ocultar editor de transcrição")
        self._text_import_open = not self._text_import_open
        self.after_idle(self._apply_page_minimum)

    def _load_text_import(self) -> None:
        selected = filedialog.askopenfilename(
            title="Abrir transcrição para resumir",
            filetypes=[("Texto e Markdown", "*.txt *.md"), ("Todos os arquivos", "*.*")],
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="utf-8-sig")
            except OSError as exc:
                messagebox.showerror("Não foi possível abrir", str(exc))
                return
        except OSError as exc:
            messagebox.showerror("Não foi possível abrir", str(exc))
            return
        self.import_text_title.set(path.stem)
        self.import_text_editor.delete("1.0", tk.END)
        self.import_text_editor.insert("1.0", content)

    def _save_imported_text(self) -> Path | None:
        from record_transcript_resume.documents import create_imported_transcript

        text = self.import_text_editor.get("1.0", "end-1c")
        try:
            transcript_path = create_imported_transcript(
                text,
                Path(self.output_dir.get() or default_output_dir()),
                self.import_text_title.get(),
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Não foi possível salvar a transcrição", str(exc))
            return None
        self.last_file.set(str(transcript_path.parent))
        self.status.set("Transcrição salva na Biblioteca")
        self.import_text_title.set("")
        self.import_text_editor.delete("1.0", tk.END)
        self._refresh_library()
        return transcript_path

    def _save_imported_text_and_regenerate(self) -> None:
        transcript_path = self._save_imported_text()
        if transcript_path is None:
            return
        self._toggle_text_import()
        self._start_summary_retry(transcript_path)

    def _queue_pipeline(
        self,
        mp3_path: Path,
        language: str,
        model_size: str,
        provider: str,
        summary_template: str,
        output_mode: str = "both",
        output_dir: Path | None = None,
    ) -> None:
        """Persist the job before doing any expensive work."""
        if not mp3_path.is_file():
            messagebox.showerror("Áudio não encontrado", f"Não foi possível encontrar:\n{mp3_path}")
            return
        job = self._job_store.enqueue(
            mp3_path, output_dir or mp3_path.parent, language, model_size, provider, summary_template, output_mode,
        )
        self._start_queued_job(job)

    def _start_queued_job(self, job: ProcessingJob) -> None:
        self.start_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.DISABLED)
        self.retry_summary_button.configure(state=tk.DISABLED)
        self.provider_selector.configure(state=tk.DISABLED)
        self._set_summary_template_state(tk.DISABLED)
        self._set_navigation_state(tk.DISABLED)
        self._set_capture_preferences_state(tk.DISABLED)
        self.status.set("1/3 · Preparando processamento")
        self.last_file.set(job.mp3_path)
        self._start_pipeline(
            job.audio_path,
            language=job.language,
            model_size=job.model_size,
            provider=job.provider,
            summary_template=job.summary_template,
            output_mode=job.output_mode,
            output_dir=Path(job.output_dir),
            job_id=job.id,
        )

    def _resume_interrupted_jobs(self) -> None:
        """Resume audio that was safely queued before a restart or update."""
        jobs = self._job_store.recoverable()
        if not jobs:
            return
        self._pending_jobs.extend(jobs)
        self.status.set(f"Retomando {len(jobs)} tarefa(s) pendente(s)...")
        self._run_next_pending_job()

    def _run_next_pending_job(self) -> None:
        if self._pipeline_thread is not None and self._pipeline_thread.is_alive():
            return
        if not self._pending_jobs:
            return
        self._start_queued_job(self._pending_jobs.pop(0))

    def _retry_summary_from_transcription(self) -> None:
        """Choose a saved transcription and regenerate only its summary."""
        current = Path(self.last_file.get()) if self.last_file.get() not in {"", "-"} else None
        initial_dir = str(current if current is not None and current.is_dir() else Path(self.output_dir.get() or Path.home()))
        selected = filedialog.askopenfilename(
            title="Selecione transcription.md ou summary.md",
            filetypes=[("Arquivos Markdown", "*.md"), ("Todos os arquivos", "*.*")],
            initialdir=initial_dir,
        )
        if not selected:
            return

        selected_path = Path(selected)
        transcript_path = (
            selected_path.with_name("transcription.md")
            if selected_path.name.lower() == "summary.md"
            else selected_path
        )
        if transcript_path.name.lower() != "transcription.md" or not transcript_path.is_file():
            messagebox.showerror(
                "Transcrição não encontrada",
                "Selecione transcription.md ou summary.md de uma gravação do Voice Notes.",
            )
            return

        self._start_summary_retry(transcript_path)

    def _start_summary_retry(self, transcript_path: Path) -> None:
        """Regenerate a saved summary, preserving the audio and transcription."""
        provider = _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex")
        summary_template = _SUMMARY_TEMPLATE_CODES.get(self.summary_template.get(), "meeting")
        self.start_button.configure(state=tk.DISABLED)
        self.process_button.configure(state=tk.DISABLED)
        self.retry_summary_button.configure(state=tk.DISABLED)
        self.youtube_process_button.configure(state=tk.DISABLED)
        self.provider_selector.configure(state=tk.DISABLED)
        self._set_summary_template_state(tk.DISABLED)
        self._set_navigation_state(tk.DISABLED)
        self.status.set("Preparando nova tentativa de resumo...")
        self.last_file.set(str(transcript_path.parent))
        self.progressbar.pack(fill=tk.X, padx=20, pady=(4, 0))
        self.progressbar.start()
        self._pipeline_thread = threading.Thread(
            target=self._retry_summary_worker,
            args=(transcript_path, provider, summary_template),
            daemon=True,
        )
        self._pipeline_thread.start()

    def _retry_summary_worker(self, transcript_path: Path, provider: str, summary_template: str) -> None:
        from record_transcript_resume.log import log
        from record_transcript_resume.pipeline import retry_summary

        log(f"GUI: retrying summary | file={transcript_path} provider={provider}")
        try:
            summary_path = retry_summary(
                transcript_path,
                provider=provider,  # type: ignore[arg-type]
                summary_template=summary_template,  # type: ignore[arg-type]
                on_status=lambda message: self.after(0, self.status.set, message),
            )
        except Exception as exc:
            log(f"GUI: summary retry failed: {type(exc).__name__}: {exc}")
            self.after(0, self._on_summary_retry_error, str(exc))
            return
        self.after(0, self._on_summary_retry_done, summary_path)

    def _on_summary_retry_done(self, summary_path: Path) -> None:
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set("Resumo atualizado com sucesso")
        self.last_file.set(str(summary_path.parent))
        self._restore_after_processing()
        self._refresh_library()

    def _on_summary_retry_error(self, message: str) -> None:
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set("Não foi possível gerar o resumo")
        self._restore_after_processing()
        messagebox.showerror(
            "Nova tentativa não concluída",
            f"{message}\n\nA transcrição foi preservada. Você pode corrigir o login ou trocar o provider e tentar novamente.\n\n{_log_hint()}",
        )

    def _restore_after_processing(self) -> None:
        """Restore controls after a pipeline or summary-only operation."""
        self.start_button.configure(state=tk.NORMAL)
        self.process_button.configure(state=tk.NORMAL)
        self.retry_summary_button.configure(state=tk.NORMAL)
        self.youtube_process_button.configure(state=tk.NORMAL)
        self.provider_selector.configure(state="readonly")
        self._set_summary_template_state(tk.NORMAL)
        self._set_navigation_state(tk.NORMAL)
        self._set_capture_preferences_state(tk.NORMAL)

    def _start_pipeline(
        self,
        mp3_path: Path,
        language: str | None,
        model_size: str = "small",
        provider: str = "codex",
        summary_template: str = "meeting",
        output_mode: str = "both",
        output_dir: Path | None = None,
        job_id: str | None = None,
    ) -> None:
        from record_transcript_resume.log import log, log_exception
        log(f"GUI: _start_pipeline | file={mp3_path.name} lang={language} model={model_size} provider={provider}")
        try:
            if job_id is not None:
                self._job_store.update(job_id, status="running", stage="1/3 · Preparando")
            self.progressbar.pack(fill=tk.X, padx=20, pady=(4, 0))
            self.progressbar.start()
            log("GUI: progressbar iniciada")

            def on_status(msg: str) -> None:
                from record_transcript_resume.log import log
                log(f"GUI: pipeline status -> {msg}")
                stage = self._pipeline_stage_label(msg)
                if job_id is not None:
                    self._job_store.update(job_id, status="running", stage=stage, error="")
                self.after(0, self.status.set, stage)

            self._pipeline_thread = threading.Thread(
                target=self._pipeline_worker,
                args=(mp3_path, output_dir or mp3_path.parent, language or "pt", model_size, provider, summary_template, output_mode, self.diarize_speakers.get(), self.huggingface_token.get(), job_id, on_status),
                daemon=True,
            )
            self._pipeline_thread.start()
            log("GUI: pipeline thread iniciada")
        except Exception as exc:
            log_exception("GUI: ERRO em _start_pipeline", exc)
            self.progressbar.stop()
            self.progressbar.pack_forget()
            self._restore_after_processing()
            self.status.set("Pipeline error")
            if job_id is not None:
                self._job_store.update(job_id, status="failed", stage="Falhou ao iniciar", error=str(exc))
            messagebox.showerror("Pipeline error", f"{exc}\n\n{_log_hint()}")

    @staticmethod
    def _pipeline_stage_label(message: str) -> str:
        normalized = message.casefold()
        if "transcrib" in normalized:
            return "1/3 · Transcrevendo áudio"
        if "summary" in normalized or "resumo" in normalized or "synthes" in normalized:
            return "2/3 · Criando resumo"
        return message

    def _pipeline_worker(
        self,
        mp3_path: Path,
        output_dir: Path,
        language: str,
        model_size: str,
        provider: str,
        summary_template: str,
        output_mode: str,
        diarize_speakers: bool,
        huggingface_token: str,
        job_id: str | None,
        on_status: object,
    ) -> None:
        import json
        import os
        import subprocess
        import sys
        import threading
        from record_transcript_resume.log import log

        log(f"GUI: _pipeline_worker started | {mp3_path.name} model={model_size} provider={provider}")

        env = os.environ.copy()
        if diarize_speakers:
            if not huggingface_token.strip():
                self.after(0, self._on_pipeline_error, "Informe o token gratuito do Hugging Face em Ajustes para separar falantes.", job_id)
                return
            try:
                import keyring
                keyring.set_password("Voice Notes", "huggingface-token", huggingface_token.strip())
            except Exception:
                pass
            env["VOICE_NOTES_HF_TOKEN"] = huggingface_token.strip()
        pipeline_args = [str(mp3_path), str(output_dir), language, model_size, provider, summary_template, "1" if diarize_speakers else "0", output_mode]
        if getattr(sys, "frozen", False):
            # In the installed application, run the frozen executable again in
            # worker mode so native transcription crashes stay isolated.
            cmd = [sys.executable, "--pipeline-worker", *pipeline_args]
        else:
            # Development mode executes the module from the source tree.
            src_dir = str(Path(__file__).resolve().parent.parent)
            existing_pp = env.get("PYTHONPATH", "")
            if src_dir not in existing_pp.split(os.pathsep):
                env["PYTHONPATH"] = src_dir + (os.pathsep + existing_pp if existing_pp else "")
            cmd = [sys.executable, "-m", "record_transcript_resume._pipeline_proc", *pipeline_args]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                **hidden_process_kwargs(),
            )
        except Exception as exc:
            log(f"GUI: falha ao lancar subprocess do pipeline: {exc}")
            self.after(0, self._on_pipeline_error, str(exc), job_id)
            return

        def _drain_stderr() -> None:
            for line in proc.stderr:
                stripped = line.rstrip()
                if stripped:
                    log(f"GUI: pipeline stderr: {stripped[:200]}")

        threading.Thread(target=_drain_stderr, daemon=True).start()

        result_event = None
        error_msg = None

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "status":
                if callable(on_status):
                    on_status(event.get("msg", ""))
            elif etype == "done":
                result_event = event
            elif etype == "error":
                error_msg = event.get("msg", "Erro desconhecido")

        proc.wait()

        if result_event is not None:
            from record_transcript_resume.pipeline import PipelineResult
            result = PipelineResult(
                folder=Path(result_event["folder"]),
                mp3_path=Path(result_event["mp3"]),
                transcript_path=Path(result_event["transcript"]) if result_event.get("transcript") else None,
                summary_path=Path(result_event["summary"]) if result_event.get("summary") else None,
            )
            log(f"GUI: pipeline concluido -> {result.folder.name}")
            self.after(0, self._on_pipeline_done, result, job_id)
        elif error_msg is not None:
            log(f"GUI: pipeline retornou erro: {error_msg}")
            self.after(0, self._on_pipeline_error, error_msg, job_id)
        elif proc.returncode != 0:
            log(f"GUI: subprocess do pipeline encerrou com crash (code={proc.returncode})")
            self.after(0, self._on_pipeline_error,
                       f"Pipeline encerrou inesperadamente (codigo={proc.returncode}). Verifique o log.", job_id)
        else:
            log("GUI: subprocess do pipeline encerrou sem resultado")
            self.after(0, self._on_pipeline_error, "Pipeline encerrou sem resultado.", job_id)

    def _on_pipeline_done(self, result: object, job_id: str | None = None) -> None:
        from record_transcript_resume.log import log
        from record_transcript_resume.pipeline import PipelineResult
        assert isinstance(result, PipelineResult)
        log(f"GUI: _on_pipeline_done | folder={result.folder.name}")
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set(f"3/3 · Concluído: {result.folder.name}")
        self.last_file.set(str(result.folder))
        if job_id is not None:
            self._job_store.update(job_id, status="completed", stage="3/3 · Concluído", error="")
        self._restore_after_processing()
        self._refresh_library()
        self._run_next_pending_job()

    def _on_pipeline_error(self, message: str, job_id: str | None = None) -> None:
        from record_transcript_resume.log import log
        log(f"GUI: _on_pipeline_error | {message[:120]}")
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set("Processamento falhou — áudio preservado")
        if job_id is not None:
            self._job_store.update(job_id, status="failed", stage="Falhou — tente novamente", error=message)
        self._restore_after_processing()
        self._refresh_library()
        self._run_next_pending_job()
        saved_audio = self._last_output
        if job_id is not None:
            failed_job = next((job for job in self._job_store.list() if job.id == job_id), None)
            if failed_job is not None:
                saved_audio = failed_job.audio_path
        location = f"\n\nSeu áudio foi preservado em:\n{saved_audio}" if saved_audio else ""
        messagebox.showerror("Processamento não concluído", f"{message}{location}\n\n{_log_hint()}")

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
        # The same signal is rendered in both modes; the compact version is
        # deliberately denser so it remains legible without becoming a panel.
        # The full-size meter can receive its first Configure event while the
        # compact surface is still being built.
        for canvas in (self._eq_canvas, getattr(self, "_compact_meter", None)):
            if canvas is None:
                continue
            canvas.delete("all")
            width, height = canvas.winfo_width(), canvas.winfo_height()
            if width < 2 or height < 2:
                continue
            bars = 16 if canvas is self._eq_canvas else 10
            gap = 3 if bars == 16 else 2
            bar_width = max(2, (width - gap * (bars + 1)) // bars)
            max_height = height - 9
            baseline = height - 4
            canvas.create_line(4, baseline, width - 4, baseline, fill="#263653", width=1)
            for index in range(bars):
                source_index = min(15, round(index * 15 / max(1, bars - 1)))
                x0 = gap + index * (bar_width + gap)
                x1 = x0 + bar_width
                level = self._eq_smooth[source_index]
                bar_height = int(level * max_height)
                canvas.create_rectangle(x0, baseline - 2, x1, baseline, fill="#263653", outline="")
                if bar_height > 0:
                    canvas.create_rectangle(x0, baseline - bar_height, x1, baseline, fill=_COLORS["accent"], outline="")
                peak_y = baseline - int(self._eq_peaks[source_index] * max_height) - 1
                if self._eq_peaks[source_index] > 0.02:
                    canvas.create_rectangle(x0, peak_y, x1, peak_y + 2, fill="#E9ECFF", outline="")

    # ── Timer / disco ─────────────────────────────────────────────────────────

    @staticmethod
    def _recording_timer_seconds(raw_value: str, unit: str) -> int:
        """Convert the optional recording limit entered in the widget to seconds."""
        value = raw_value.strip().replace(",", ".")
        if not value:
            return 0
        try:
            amount = float(value)
        except ValueError as exc:
            raise ValueError("Informe um número de minutos ou horas.") from exc
        if amount <= 0:
            raise ValueError("O tempo de gravação deve ser maior que zero.")

        multiplier = 3600 if unit == "horas" else 60
        return max(1, round(amount * multiplier))

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        hours, remainder = divmod(max(0, int(total_seconds)), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _refresh_timer(self) -> None:
        if self._started_at is not None:
            seconds = int(time.monotonic() - self._started_at)
            minutes, remainder = divmod(seconds, 60)
            self.elapsed.set(f"{minutes:02d}:{remainder:02d}")
            if self._recording_deadline is not None:
                remaining = max(0, round(self._recording_deadline - time.monotonic()))
                self.recording_limit_hint.set(
                    f"Parada automática em {self._format_duration(remaining)}"
                )
                if remaining == 0:
                    # Clear first so a future interface refresh cannot request a
                    # second stop while the finalization worker starts.
                    self._recording_deadline = None
                    self.after_idle(lambda: self._stop_recording(automatic=True))
        else:
            self.elapsed.set("00:00")

        self._check_backend_alive()
        self._check_disk_space()
        self._refresh_compact_controls()
        self.after(500, self._refresh_timer)

    def _check_backend_alive(self) -> None:
        if self._service is None or self._service.state != RecordingState.RECORDING:
            return
        if self._service.is_backend_alive:
            return
        # Thread morreu durante a gravação — acionar stop imediatamente
        if self._stop_thread is not None and self._stop_thread.is_alive():
            return  # stop já em andamento
        self.stop_button.configure(state=tk.DISABLED)
        self._recording_deadline = None
        self.recording_limit_hint.set("Sem parada automática")
        self.status.set("Capture failed...")
        self._stop_thread = threading.Thread(target=self._stop_recording_worker, daemon=True)
        self._stop_thread.start()

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
            self.disk_warning.set(f"Warning: low disk space — {free_mb} MB available.")
        else:
            self.disk_warning.set("")

    def _active_work_description(self) -> str | None:
        """Return the operation that must not be accidentally interrupted."""
        if self._service is not None and self._service.state == RecordingState.RECORDING:
            return "gravação"
        if self._stop_thread is not None and self._stop_thread.is_alive():
            return "finalização da gravação"
        if self._pipeline_thread is not None and self._pipeline_thread.is_alive():
            return "transcrição ou resumo"
        return None

    def _on_close(self) -> None:
        from record_transcript_resume.log import log
        state = self._service.state if self._service is not None else "sem_service"
        log(f"GUI: _on_close chamado | state={state}")
        active_work = self._active_work_description()
        if active_work is not None:
            # Closing the visible widget must never silently abandon an active
            # recording or AI job. The notification-area icon remains available
            # to restore it, including when this originates from the tray menu.
            self.status.set(f"{active_work.capitalize()} continua em segundo plano.")
            self._hide_to_tray()
            self._tray.notify(
                "Voice Notes continua processando",
                f"A {active_work} continua em segundo plano. Use o ícone da bandeja para acompanhar.",
            )
            log(f"GUI: fechamento protegido; {active_work} continua em segundo plano")
            return
        log("GUI: destroy() chamado")
        self._tray.stop()
        self.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audio recorder graphical interface.")
    parser.add_argument("--widget", action="store_true", help="Compatibility option; the application is always a widget.")
    parser.add_argument(
        "--start-hidden",
        action="store_true",
        help="Start in the Windows notification area instead of showing the widget.",
    )
    parser.add_argument("--pipeline-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("pipeline_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.pipeline_worker:
        from record_transcript_resume._pipeline_proc import main as pipeline_main

        return pipeline_main(args.pipeline_args)
    app = RecorderApp(start_hidden=args.start_hidden)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
