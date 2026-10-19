from __future__ import annotations

import shutil
import subprocess
import threading
import time
import queue
import tkinter as tk
import argparse
import os
import re
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

import customtkinter as ctk

from record_transcript_resume.errors import DiskSpaceError, RecordingError
from record_transcript_resume.paths import default_output_dir
from record_transcript_resume.preferences import (
    load_color_theme, load_library_directory, load_summary_provider,
    save_color_theme, save_library_directory, save_summary_provider,
)
from record_transcript_resume.themes import (
    DEFAULT_THEME, THEME_LABELS, THEMES, ThemeColor, configure_widget_defaults,
    theme_color, theme_colors,
)
from record_transcript_resume.recording import MIN_FREE_BYTES, RecordingConfig, RecordingService, RecordingState
from record_transcript_resume.transcription import available_models
from record_transcript_resume.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig
from record_transcript_resume.jobs import JobStore, ProcessingJob
from record_transcript_resume.library import (
    BrowserEntry, LibraryItem, LibraryMetadataStore, browse_directory, discover_recordings,
)
from record_transcript_resume.synthesis import SUMMARY_TEMPLATE_LABELS, profile_prompt_seed, prompt_preview
from record_transcript_resume.windows_process import hidden_process_kwargs

def _log_hint() -> str:
    from record_transcript_resume.log import _log_path
    return f"Log técnico completo: {_log_path()}"


_LANGUAGES = [
    ("Portuguese (BR)", "pt"),
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("Auto-detect", None),
]
_LANG_LABELS = [label for label, _ in _LANGUAGES]
_LANG_CODES = {label: code for label, code in _LANGUAGES}
_SUMMARY_PROVIDERS = [("Codex", "codex"), ("Claude Code", "claude")]
_SUMMARY_PROVIDER_CODES = dict(_SUMMARY_PROVIDERS)
_SUMMARY_PROVIDER_LABELS = [label for label, _ in _SUMMARY_PROVIDERS]
_SUMMARY_TEMPLATE_CODES = {label: code for code, label in SUMMARY_TEMPLATE_LABELS.items()}
_SUMMARY_TEMPLATE_LABELS = list(_SUMMARY_TEMPLATE_CODES)
_SUMMARY_TEMPLATE_NAMES_BY_CODE = {code: label for label, code in _SUMMARY_TEMPLATE_CODES.items()}
_WHISPER_MODEL_DESCRIPTIONS = {
    "tiny": "Mais rápido · menor precisão",
    "base": "Rápido · qualidade básica",
    "small": "Equilibrado · recomendado",
    "medium": "Mais preciso · mais lento",
    "large-v3": "Máxima precisão · mais pesado",
}
_PROCESSING_PROFILES = {
    "Resumo padrão": ("Reunião", "small", False),
    "Reunião de trabalho": ("Reunião", "small", True),
    "Aula": ("Aula", "medium", False),
    "Entrevista": ("Entrevista", "medium", True),
    "Call comercial": ("Call comercial", "small", True),
    "Brainstorm": ("Brainstorm", "small", True),
    "Resumo executivo": ("Resumo executivo", "small", True),
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
_PLAYER_PLAY_ICON = "▶"
_PLAYER_PAUSE_ICON = "⏸"
_PIX_KEY = "f608aca6-81f0-4c41-a77f-347777f75b0e"

_BUTTON_HELP: dict[str, str] = {
    "×": "Fecha a janela. Se houver uma tarefa ativa, o app continua na bandeja.",
    "Ocultar": "Esconde a janela; o app continua acessível pela bandeja do Windows.",
    "Minimizar": "Mostra o controle compacto de gravação.",
    "Tela cheia": "Expande o app para ocupar o monitor inteiro.",
    "Modo foco": "Volta à janela de tamanho fixo do modo foco.",
    "Restaurar": "Volta à janela de tamanho fixo do modo foco.",
    "Encerrar": "Fecha a janela. Se houver uma tarefa ativa, o app continua na bandeja.",
    "Fechar": "Fecha esta janela sem alterar os arquivos.",
    "Gravar": "Abre as opções para capturar voz e som do computador.",
    "Arquivo": "Abre a importação de um áudio ou vídeo existente.",
    "Biblioteca": "Mostra os arquivos e pastas da Biblioteca.",
    "Processos": "Mostra a fila, o andamento e os erros de processamento.",
    "YouTube": "Abre a importação de um vídeo autorizado do YouTube.",
    "Ajustes": "Abre as configurações de transcrição, resumo e provedores.",
    "Aparência": "Escolhe e salva o tema de cores do aplicativo.",
    "●  Violeta atual": "Usa o tema violeta original do Voice Notes.",
    "●  Oceano": "Usa superfícies azul-petróleo com realces ciano.",
    "●  Floresta": "Usa superfícies verdes com realces de folha.",
    "●  Ameixa": "Usa superfícies ameixa com realces rosados.",
    "●  Âmbar": "Usa superfícies quentes com realces âmbar.",
    "●  Vinho": "Usa superfícies neutras com realces vinho discretos.",
    "●  Machine Red": "Usa Machine Red e Glacier Blue nos realces e textos.",
    "●  Claro": "Usa uma paleta clara com texto escuro.",
    "●  Grafite": "Usa cinzas neutros e destaques prateados.",
    "Alterar": "Escolhe onde as próximas gravações serão salvas.",
    "Alterar pasta": "Escolhe onde as próximas gravações serão salvas.",
    "Iniciar gravação": "Começa a gravar com as opções selecionadas.",
    "Iniciar": "Começa a gravar com as opções selecionadas.",
    "Parar": "Encerra a gravação atual e salva o áudio.",
    "Abrir Biblioteca": "Abre a Biblioteca para encontrar gravações e resultados.",
    "Ver Biblioteca": "Abre a Biblioteca para encontrar gravações e resultados.",
    "Abrir": "Abre o arquivo, a pasta ou o item indicado nesta tela.",
    "Ver Processos": "Abre a lista de processamentos e seus resultados.",
    "Verificação": "Mostra os testes de instalação e funcionamento.",
    "Provider e API": "Configura as contas e os provedores de IA usados nos resumos.",
    "Resumos": "Configura os formatos e perfis de resumo.",
    "Transcrição": "Configura o modelo e as opções de transcrição.",
    "Falantes": "Configura a identificação de falantes.",
    "Verificar agora": "Executa esta verificação agora.",
    "Testar modelo selecionado": "Verifica se o modelo local de transcrição funciona.",
    "Testar modelo": "Verifica se o modelo local de transcrição funciona.",
    "Testar Codex": "Verifica se o Codex está instalado e responde neste computador.",
    "Testar Claude": "Verifica se o Claude está instalado e responde neste computador.",
    "Conectar conta no navegador": "Abre o navegador para conectar a conta do provedor.",
    "Tentar instalar providers": "Tenta instalar os programas necessários para os provedores de IA.",
    "+ Novo Provider": "Adiciona a configuração de um novo provedor de IA.",
    "Opções avançadas": "Mostra ou oculta configurações adicionais.",
    "Opções avançadas ▾": "Mostra configurações adicionais deste processamento.",
    "Opções avançadas ▴": "Oculta configurações adicionais deste processamento.",
    "Salvar provider": "Salva a configuração do provedor de IA.",
    "Testar": "Executa um teste de conexão com este provedor.",
    "Atualizar agora": "Inicia a instalação da atualização disponível.",
    "Apoiar o projeto": "Mostra como apoiar o desenvolvimento do app.",
    "Ver prompt": "Mostra o texto de instruções usado neste perfil de resumo.",
    "Ver prompt-base": "Mostra as instruções usadas como base para este resumo.",
    "+ Novo perfil": "Cria um perfil personalizado para gerar resumos.",
    "Mostrar": "Mostra o token salvo no campo.",
    "Esconder": "Oculta o token exibido no campo.",
    "Copiar": "Copia o token para a área de transferência.",
    "Copiar chave Pix": "Copia a chave Pix para apoiar o projeto.",
    "Copiar detalhes": "Copia os detalhes do erro para a área de transferência.",
    "Copiar prompt": "Copia as instruções deste perfil de resumo.",
    "Copiar texto": "Copia o texto aberto para a área de transferência.",
    "Salvar token": "Salva o token usado para identificar falantes.",
    "Escolher áudio ou vídeo": "Seleciona um arquivo local para transcrever ou resumir.",
    "Escolher arquivo": "Seleciona um arquivo local para transcrever ou resumir.",
    "Importar áudio": "Escolhe um arquivo de áudio para adicionar ou processar.",
    "Colar ou abrir transcrição": "Abre as opções para importar um texto já transcrito.",
    "Voltar para arquivo": "Volta às opções para importar e processar áudio ou vídeo.",
    "Abrir .txt/.md": "Carrega uma transcrição de um arquivo de texto.",
    "Salvar": "Salva as alterações feitas nesta janela.",
    "Salvar e gerar resumo": "Salva a transcrição e inicia a geração do resumo.",
    "Abrir transcrição salva para resumir": "Escolhe uma transcrição existente para gerar um resumo.",
    "Baixar áudio e processar": "Baixa o áudio do vídeo informado e inicia o processamento.",
    "Atualizar": "Recarrega os dados exibidos nesta tela.",
    "Escolher pasta": "Escolhe qual pasta a Biblioteca deve mostrar.",
    "Trocar pasta": "Escolhe qual pasta a Biblioteca deve mostrar.",
    "Pasta de Gravar": "Mostra na Biblioteca a pasta usada pelas novas gravações.",
    "Retomar": "Continua os processamentos interrompidos que podem ser retomados.",
    "Todas as etiquetas  ▾": "Filtra as gravações por etiqueta.",
    "Todas  ▾": "Filtra as gravações pelo estado do áudio e dos resultados.",
    "Mais recentes  ▾": "Escolhe a ordem de exibição das gravações.",
    "Ouvir áudio": "Abre o áudio selecionado para reprodução.",
    "Transcrever + resumir": "Cria transcrição e resumo para o áudio selecionado.",
    "Ler / editar": "Abre o documento selecionado para leitura e edição.",
    "Gerar resumo": "Cria um resumo a partir da transcrição selecionada.",
    "Gerar nova versão": "Gera uma nova versão do resumo com as opções atuais.",
    "Refazer resumo": "Gera novamente o resumo a partir da transcrição existente.",
    "☆ Favoritar": "Marca o item selecionado como favorito.",
    "★ Favorito": "Remove o item selecionado dos favoritos.",
    "Editar título e etiquetas": "Organiza o item selecionado com um título e etiquetas.",
    "Título e etiquetas": "Organiza o item selecionado com um título e etiquetas.",
    "Editar": "Abre o item selecionado para edição.",
    "Remover": "Remove o item selecionado desta lista.",
    "Abrir pasta": "Abre a pasta selecionada no Explorador de Arquivos.",
    "Exportar DOCX": "Exporta o documento selecionado para Word (.docx).",
    "Exportar PDF": "Exporta o documento selecionado para PDF.",
    "DOCX": "Exporta o documento selecionado para Word (.docx).",
    "PDF": "Exporta o documento selecionado para PDF.",
    "Nomear falantes": "Atribui nomes aos falantes identificados na transcrição.",
    "Cancelar": "Fecha esta ação sem aplicar alterações.",
    "←": "Volta à pasta visitada anteriormente na Biblioteca.",
    "↑": "Abre a pasta que contém a pasta atual.",
    "+ Nova pasta": "Cria uma subpasta dentro da pasta exibida.",
    "Mover pasta": "Move a pasta selecionada para outro diretório.",
    "Renomear": "Renomeia a pasta selecionada.",
    "Processar áudio": "Cria transcrição e resumo para o áudio selecionado.",
    "Abrir no player": "Abre o áudio selecionado no player padrão do Windows.",
    "Abrir documento": "Abre o documento selecionado para leitura.",
    "Abrir arquivo": "Abre o arquivo selecionado com o programa padrão do Windows.",
    "Todos": "Mostra todos os processamentos.",
    "Em andamento": "Mostra os processamentos em execução.",
    "Aguardando": "Mostra os processamentos que ainda não começaram.",
    "Exigem atenção": "Mostra os processamentos com falha ou aviso.",
    "Concluídos": "Mostra os processamentos finalizados.",
    "Tentar novamente": "Tenta executar de novo o processamento selecionado.",
    "Tentar de novo": "Tenta executar de novo este processamento.",
    "Ver aviso": "Mostra os detalhes do aviso deste processamento.",
    "Ver erro": "Mostra os detalhes do erro deste processamento.",
    "Ver erro completo": "Mostra os detalhes do erro do processamento selecionado.",
    "Remover da lista": "Remove o processamento selecionado da lista, sem apagar o áudio.",
    "Processar arquivo": "Inicia a transcrição ou o resumo do arquivo escolhido.",
    "Cancelar processamento": "Solicita o cancelamento do processamento em execução.",
    "Aplicar ao texto": "Substitui os nomes dos falantes no texto aberto.",
}


def _saved_huggingface_token() -> str:
    try:
        import keyring
        return keyring.get_password("Voice Notes", "huggingface-token") or ""
    except Exception:
        return os.environ.get("HF_TOKEN", "")


def _diarization_enabled_by_default(token: str) -> bool:
    """Keep the slower speaker separation opt-in, even when a token is saved."""
    return False


_ACTIVE_THEME_NAME = DEFAULT_THEME
_COLORS = theme_colors(DEFAULT_THEME)


def _theme_color(color: str) -> str:
    """Resolve existing hard-coded UI colors against the active palette."""
    return theme_color(color, _ACTIVE_THEME_NAME)


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
                    pystray.MenuItem(
                        "Iniciar reunião", self._start_meeting,
                        enabled=lambda _item: self._app._tray_can_start_meeting(),
                    ),
                    pystray.MenuItem(
                        "Parar gravação", self._stop_meeting,
                        enabled=lambda _item: self._app._tray_can_stop_meeting(),
                    ),
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

    def _start_meeting(self, *_: object) -> None:
        self._app.after(0, self._app._start_recording_from_tray)

    def _stop_meeting(self, *_: object) -> None:
        self._app.after(0, self._app._stop_recording_from_tray)

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

    def refresh(self) -> None:
        """Refresh dynamic tray actions after recording state changes."""
        icon = self._icon
        if icon is not None:
            try:
                icon.update_menu()  # type: ignore[attr-defined]
            except Exception:
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
        global _ACTIVE_THEME_NAME
        self._theme_name = load_color_theme()
        _ACTIVE_THEME_NAME = self._theme_name
        _COLORS.update(theme_colors(self._theme_name))
        configure_widget_defaults(ctk.ThemeManager.theme, self._theme_name)
        super().__init__(fg_color=_COLORS["surface"])
        self.title("Voice Notes (Beta)")
        try:
            self.iconbitmap(default=str(_asset_path("voice-notes.ico")))
        except tk.TclError:
            # The icon is optional when running the source on a non-Windows host.
            pass
        # Focus and compact are fixed-size modes. The full-screen layout keeps
        # using the monitor bounds; manual corner resizing is deliberately off.
        self._min_widget_width = min(760, max(520, self.winfo_screenwidth() - 40))
        self._min_widget_height = min(620, max(500, self.winfo_screenheight() - 80))
        self._active_min_width = self._min_widget_width
        self._active_min_height = self._min_widget_height
        # Keep the primary workflow fully visible on a typical desktop while
        # preserving enough room for the taskbar on smaller displays.
        self._main_widget_height = min(920, max(self._min_widget_height, self.winfo_screenheight() - 80))
        self._preferred_widget_width = min(760, max(self._min_widget_width, self.winfo_screenwidth() - 40))
        self._user_resized_window = False
        self._resize_hit_size = 28
        self._resize_apply_after: str | None = None
        self._pending_resize_geometry: tuple[int, int] | None = None
        self._round_region_after: str | None = None
        self._content_scrollbar_after: str | None = None
        self._reachability_after: str | None = None
        self._window_repaint_after: str | None = None
        self.geometry(f"{self._preferred_widget_width}x{self._main_widget_height}")
        self.minsize(self._min_widget_width, self._min_widget_height)
        self.maxsize(self._preferred_widget_width, self._main_widget_height)
        self.resizable(False, False)
        # Do not rely on chroma-key transparency for the outer silhouette.
        # It leaks a rectangular background below rounded CTk frames on resize.
        self.configure(fg_color=_COLORS["surface"])

        self._service: RecordingService | None = None
        self._started_at: float | None = None
        self._last_output: Path | None = None
        self._stop_thread: threading.Thread | None = None
        self._pipeline_thread: threading.Thread | None = None
        self._youtube_download_thread: threading.Thread | None = None
        self._pipeline_process: object | None = None
        self._active_job_id: str | None = None
        self._processing_cancel_requested = False
        self._pipeline_has_speaker_separation = False
        self._pipeline_output_mode = "both"
        self._job_store = JobStore()
        self._library_metadata = LibraryMetadataStore()
        self._library_items: list[LibraryItem] = []
        self._browser_directory: Path | None = None
        self._library_render_after: str | None = None
        self._library_render_signature: tuple[object, ...] | None = None
        self._recent_render_signature: tuple[LibraryItem, ...] | None = None
        self._responsive_labels: list[ctk.CTkLabel] = []
        self._responsive_wrap_after: str | None = None
        self._last_responsive_width = 0
        self._last_responsive_height = 0
        self._desktop_style_original: dict[tk.Misc, tuple[object, int | None]] = {}
        self._desktop_style_applied: dict[tk.Misc, tuple[object, int | None]] = {}
        self._library_open = False
        self._library_editing = False
        self._library_document_window: ctk.CTkToplevel | None = None
        self._youtube_open = False
        self._widget_mode = False
        self._maximized = False
        self._restore_geometry = ""
        self._restore_bounds: tuple[int, int, int, int] | None = None
        self._maximized_content_width = 1880
        self._desktop_layout = False
        self._page_layout_desktop: dict[str, bool] = {}
        self._restore_borderless_on_map = False
        self._drag_active = False
        self._resize_active = False
        self._settings_open = False
        self._compact_mode = False
        self._full_widget_geometry = ""
        self._full_widget_bounds: tuple[int, int, int, int] | None = None
        self._compact_position: tuple[int, int] | None = None
        self._compact_drag_active = False
        self._compact_drag_moved = False
        self._compact_width = min(584, max(380, self.winfo_screenwidth() - 20))
        self._compact_height = 64
        self._provider_setup_running = False
        self._provider_setup_attempted = False
        self._provider_status_check_running = False
        self._update_check_running = False
        self._ui_actions: queue.SimpleQueue[tuple[Callable[..., object], tuple[object, ...]]] = queue.SimpleQueue()
        self._pix_support_window: ctk.CTkToplevel | None = None
        self._tray = _TrayController(self)
        self._tray_available = False

        self.output_dir = tk.StringVar(value=str(default_output_dir()))
        saved_library_directory = load_library_directory()
        self._library_directory_manual = bool(saved_library_directory)
        self.library_dir = tk.StringVar(value=saved_library_directory or self.output_dir.get())
        self.mode = tk.StringVar(value="both")
        self.status = tk.StringVar(value="Pronto para gravar")
        self.elapsed = tk.StringVar(value="00:00")
        self._compact_status = tk.StringVar(value="PRONTO")
        self.recording_limit_value = tk.StringVar(value="")
        self.recording_limit_unit = tk.StringVar(value="minutos")
        self.recording_limit_hint = tk.StringVar(value="Sem parada automática")
        self.recording_output_mode = tk.StringVar(value="audio")
        self.recording_output_choice = tk.StringVar(value=_RECORDING_OUTPUT_LABELS["audio"])
        self.recording_output_hint = tk.StringVar(
            value="O áudio será salvo. Você poderá processá-lo depois pela Biblioteca."
        )
        self._recording_processing_options: dict[str, object] = {}
        self._recording_deadline: float | None = None
        self._processing_started_at: float | None = None
        self._processing_activity = ""
        self._processing_feedback = tk.StringVar(value="")
        self.last_file = tk.StringVar(value="-")
        self.disk_warning = tk.StringVar(value="")
        self.pipeline_language = tk.StringVar(value=_LANG_LABELS[0])
        self._available_models = available_models()
        self.pipeline_model = tk.StringVar(value="small")
        self.model_description = tk.StringVar(value=_WHISPER_MODEL_DESCRIPTIONS["small"])
        self.transcription_source = tk.StringVar(value="Whisper local")
        self.transcription_source_hint = tk.StringVar(value="Processa o áudio neste computador com o modelo Whisper selecionado.")
        # Importing an existing file is an independent workflow. Its choices
        # stay visible in the Arquivo page and are snapshotted into the job,
        # instead of silently inheriting recording settings.
        self.file_pipeline_language = tk.StringVar(value=self.pipeline_language.get())
        self.file_pipeline_model = tk.StringVar(value=self.pipeline_model.get())
        self.file_transcription_source = tk.StringVar(value=self.transcription_source.get())
        self.file_diarize_speakers = tk.BooleanVar(value=False)
        self.file_output_mode = tk.StringVar(value="Transcrição e resumo")
        self._focus_file_path: Path | None = None
        self.youtube_url = tk.StringVar(value="")
        self.youtube_mode = tk.StringVar(value="Transcrição e resumo")
        self.youtube_hint = tk.StringVar(value="Use somente conteúdo próprio ou autorizado.")
        self.summary_provider = tk.StringVar(value="Codex")
        from record_transcript_resume.api_provider import ApiProviderConfig, load_configs
        self._api_provider_configs = load_configs()
        self._api_provider_labels: dict[str, str] = {}
        self._preferred_summary_provider_code = load_summary_provider()
        self._restore_summary_provider_choice()
        self._editing_api_provider_id: str | None = None
        api_defaults = ApiProviderConfig()
        self.api_provider_name = tk.StringVar(value=api_defaults.name)
        self.api_protocol = tk.StringVar(value=api_defaults.protocol)
        self.api_base_url = tk.StringVar(value=api_defaults.base_url)
        self.api_model = tk.StringVar(value=api_defaults.model)
        self.api_transcription_model = tk.StringVar(value=api_defaults.transcription_model)
        self.api_auth_header = tk.StringVar(value=api_defaults.auth_header)
        self.api_auth_prefix = tk.StringVar(value=api_defaults.auth_prefix)
        self.api_response_path = tk.StringVar(value=api_defaults.response_path)
        self.api_request_template_default = api_defaults.request_template
        self.api_token = tk.StringVar(value="")
        self.api_token_hint = tk.StringVar(value="O token será guardado no Cofre de Credenciais do Windows.")
        self._api_provider_open = False
        self._api_advanced_open = False
        self.summary_template = tk.StringVar(value="Reunião")
        self.processing_profile = tk.StringVar(value="Resumo padrão")
        self.file_summary_provider = tk.StringVar(value=self.summary_provider.get())
        self.file_processing_profile = tk.StringVar(value=self.processing_profile.get())
        from record_transcript_resume.summary_profiles import load_profiles
        self._summary_profiles = load_profiles()
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
        self.library_filter = tk.StringVar(value="Todas")
        self.library_tag_filter = tk.StringVar(value="Todas as etiquetas")
        self.library_sort = tk.StringVar(value="Mais recentes")
        self.library_detail = tk.StringVar(value="Selecione uma gravação para ver as ações disponíveis.")
        self.library_count = tk.StringVar(value="")
        self.queue_hint = tk.StringVar(value="Fila vazia")
        self._provider_test_running: set[str] = set()
        self._provider_test_status = {
            "codex": tk.StringVar(value="Ainda não testado"),
            "claude": tk.StringVar(value="Ainda não testado"),
        }
        self._provider_test_labels: dict[str, ctk.CTkLabel] = {}
        self._provider_test_buttons: dict[str, ctk.CTkButton] = {}
        self._local_transcription_test_running = False
        self.local_transcription_test_status = tk.StringVar(value="Ainda não testado")
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
        self._button_tooltip_after: str | None = None
        self._button_tooltip_target: tk.Misc | None = None
        self._button_tooltip_popup: tk.Toplevel | None = None
        self._button_tooltip_label: tk.Label | None = None
        self._install_button_tooltips()
        self.output_dir.trace_add("write", self._on_output_directory_changed)
        self._bind_responsive_wraps(self)
        self.summary_provider.trace_add("write", self._on_provider_changed)
        self.pipeline_model.trace_add("write", self._on_model_changed)
        self.transcription_source.trace_add("write", self._on_transcription_source_changed)
        self.processing_profile.trace_add("write", self._on_processing_profile_changed)
        self.recording_output_mode.trace_add("write", self._on_recording_output_mode_changed)
        self._set_widget_mode(True)
        self.after_idle(self._schedule_widget_rounding)
        self._refresh_provider_hint()
        self._refresh_timer()
        self._eq_timer()
        self.after(80, self._drain_ui_actions)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Map>", self._restore_borderless_after_minimize, add="+")
        self.bind("<Escape>", self._cancel_processing_shortcut, add="+")
        # A remap can discard the native clipping region on some Windows/DPI
        # combinations, so restore it whenever the shell becomes visible.
        self.bind("<Map>", lambda _event: self._schedule_widget_rounding(), add="+")
        self.bind("<Configure>", self._schedule_widget_rounding, add="+")
        self.bind("<Configure>", self._schedule_responsive_wraps, add="+")
        self.bind("<Configure>", self._sync_window_controls, add="+")
        self.bind("<Configure>", self._schedule_window_reachability, add="+")
        self.bind("<Map>", self._schedule_window_reachability, add="+")
        self.bind("<F11>", self._toggle_maximized, add="+")
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

    def _post_to_ui(self, callback: Callable[..., object], *args: object) -> None:
        """Send a worker result to Tk without calling Tk from that worker."""
        self._ui_actions.put((callback, args))

    def _drain_ui_actions(self) -> None:
        try:
            for _ in range(100):
                try:
                    callback, args = self._ui_actions.get_nowait()
                except queue.Empty:
                    break
                callback(*args)
        finally:
            if self.winfo_exists():
                self.after(80, self._drain_ui_actions)

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
        style.configure("PipelineInfo.TLabel", background=_COLORS["bg"], font=("Segoe UI", 10, "bold"), foreground=_theme_color("#BFC7FF"))
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
        self._title_block = title_block
        eyebrow_row = ctk.CTkFrame(title_block, fg_color="transparent")
        eyebrow_row.pack(anchor=tk.W)
        eyebrow = ctk.CTkLabel(
            eyebrow_row, text="Voice", font=("Segoe UI", 15, "bold"),
            text_color=_theme_color("#EEF3FF"), anchor="w",
        )
        eyebrow.pack(side=tk.LEFT)
        notes_label = ctk.CTkLabel(
            eyebrow_row, text="Notes", font=("Segoe UI", 15, "bold"),
            text_color=_theme_color("#A99AF4"), anchor="w",
        )
        notes_label.pack(side=tk.LEFT, padx=(4, 0))
        beta_label = ctk.CTkLabel(
            eyebrow_row, text="BETA", font=("Segoe UI", 8, "bold"),
            text_color=_theme_color("#B7AAFF"), fg_color=_theme_color("#29254B"), corner_radius=6,
            width=38, height=20,
        )
        beta_label.pack(side=tk.LEFT, padx=(8, 0))
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
            title, drag_hint,
        )

        window_controls = ctk.CTkFrame(header, fg_color="transparent")
        window_controls.pack(side=tk.RIGHT, anchor=tk.N)
        self._window_controls = window_controls
        self.close_button = ctk.CTkButton(
            window_controls, text="Encerrar", command=self._on_close, width=64, height=32,
            corner_radius=10, fg_color="transparent", hover_color=_theme_color("#3A1D2A"),
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
        self.maximize_button = ctk.CTkButton(
            window_controls, text="Tela cheia", command=self._toggle_maximized, width=82, height=32,
            corner_radius=10, fg_color="transparent", hover_color=_COLORS["surface_alt"],
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.maximize_button.pack(side=tk.RIGHT, padx=(4, 0))
        workspace = ctk.CTkFrame(container, fg_color="transparent")
        workspace.pack(fill=tk.BOTH, expand=True)
        self._workspace = workspace
        self._wide_shell = False
        navigation = ctk.CTkFrame(workspace, fg_color=_theme_color("#0D1525"), corner_radius=10)
        navigation.pack(fill=tk.X, padx=20, pady=(4, 8))
        self._navigation = navigation
        self._nav_heading = ctk.CTkLabel(
            navigation, text="ESPAÇO DE TRABALHO", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        )
        self._page_buttons: dict[str, ctk.CTkButton] = {}
        for index, (page, label, command) in enumerate([
            ("record", "Gravar", self._show_recording_page),
            ("file", "Arquivo", self._show_file_import),
            ("library", "Biblioteca", self._toggle_library),
            ("processing", "Processos", self._show_processing_page),
            ("youtube", "YouTube", self._toggle_youtube),
            ("settings", "Ajustes", self._toggle_settings),
        ]):
            button = ctk.CTkButton(
                navigation, text=label, command=command, width=78, height=30, corner_radius=8,
                fg_color="transparent", hover_color=_theme_color("#22324F"), text_color=_COLORS["muted"],
                font=("Segoe UI", 12, "bold"),
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            self._page_buttons[page] = button
            navigation.grid_columnconfigure(index, weight=1)
        self._navigation_columns = 6
        navigation.bind("<Configure>", lambda event: self._layout_navigation(event.width), add="+")
        self.record_page_button = self._page_buttons["record"]
        self.file_page_button = self._page_buttons["file"]
        self.youtube_page_button = self._page_buttons["youtube"]
        self.library_button = self._page_buttons["library"]
        self.processing_button = self._page_buttons["processing"]
        self.settings_button = self._page_buttons["settings"]

        main_shell = ctk.CTkFrame(workspace, fg_color="transparent")
        main_shell.pack(fill=tk.BOTH, expand=True)
        self._main_shell = main_shell

        # Pages with many controls must scroll inside the widget instead of
        # forcing the borderless window beyond the visible work area.  The
        # header and navigation remain fixed, so switching destinations never
        # hides the window's lower rounded corners below the screen edge.
        content = ctk.CTkScrollableFrame(
            main_shell,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_fg_color="transparent",
            scrollbar_button_color=_theme_color("#263550"),
            scrollbar_button_hover_color=_theme_color("#34476B"),
        )
        content.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 4))
        content._parent_canvas.bind(
            "<Configure>",
            lambda _event: self._schedule_content_scrollbar(),
            add="+",
        )

        status_card = ctk.CTkFrame(
            content, fg_color=_COLORS["surface_alt"], corner_radius=12,
            border_width=1, border_color=_theme_color("#2A3A58"),
        )
        status_card.pack(fill=tk.X, padx=20, pady=(4, 8))
        status_row = ctk.CTkFrame(status_card, fg_color="transparent")
        status_row.pack(fill=tk.X, padx=14, pady=(9, 8))
        self._status_indicator = ctk.CTkLabel(
            status_row, text="", width=9, height=9, corner_radius=5,
            fg_color=_theme_color("#55D6A0"),
        )
        self._status_indicator.pack(side=tk.LEFT, padx=(0, 9))
        ctk.CTkLabel(
            status_row, textvariable=self.status, font=("Segoe UI", 13, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(
            status_row, textvariable=self.elapsed, font=("Cascadia Mono", 17, "bold"),
            text_color=_COLORS["text"], anchor="e",
        ).pack(side=tk.RIGHT)
        self._recording_limit_status = ctk.CTkLabel(
            status_card, textvariable=self.recording_limit_hint, font=("Segoe UI", 9),
            text_color=_COLORS["muted"], anchor="w",
        )
        self.recording_limit_hint.trace_add("write", self._sync_recording_status_details)

        meter_card = ctk.CTkFrame(status_card, fg_color=_theme_color("#0C1423"), corner_radius=10)
        self._meter_card = meter_card
        self._eq_canvas = tk.Canvas(
            meter_card, height=22, bg=_theme_color("#0C1423"), highlightthickness=0, bd=0,
        )
        self._eq_canvas.pack(fill=tk.X, padx=8, pady=3)
        self._eq_canvas.bind("<Configure>", lambda _: self._redraw_eq())

        self.device_info_label = ctk.CTkLabel(
            content, textvariable=self.device_info_text, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w",
        )

        self._container = content
        capture_card = ctk.CTkFrame(content, fg_color="transparent")
        self._record_capture_card = capture_card
        capture_card.pack(fill=tk.X, padx=20, pady=(8, 8))
        source_section = ctk.CTkFrame(capture_card, fg_color=_theme_color("#141E32"), corner_radius=12)
        self._record_source_section = source_section
        source_section.pack(fill=tk.X, pady=(0, 10))
        ctk.CTkLabel(
            source_section, text="1  O que gravar", font=("Segoe UI", 17, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(13, 2))
        ctk.CTkLabel(
            source_section, text="Combine sua voz com o som do computador, se precisar.",
            font=("Segoe UI", 13), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16)
        source_row = ctk.CTkFrame(source_section, fg_color="transparent")
        source_row.pack(fill=tk.X, padx=16, pady=(12, 15))
        self._source_choice_cards: list[ctk.CTkFrame] = []
        self._source_choice_descriptions: list[ctk.CTkLabel] = []
        self._source_buttons: list[ctk.CTkRadioButton] = []
        for text, value, description in [
            ("Microfone + sistema", "both", "Sua voz e o som do computador"),
            ("Microfone", "microphone", "Apenas sua voz"),
            ("Sistema", "system", "Apenas o som do computador"),
        ]:
            choice = ctk.CTkFrame(source_row, fg_color="transparent", corner_radius=9)
            button = ctk.CTkRadioButton(
                choice, text=text, variable=self.mode, value=value,
                font=("Segoe UI", 13, "bold"), text_color=_COLORS["text"],
                fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
                border_color=_theme_color("#5C6D91"), radiobutton_width=18, radiobutton_height=18,
            )
            button.pack(anchor=tk.W, padx=14, pady=(11, 2))
            detail = ctk.CTkLabel(
                choice, text=description, font=("Segoe UI", 12),
                text_color=_COLORS["muted"], anchor="w",
            )
            detail.pack(fill=tk.X, padx=14, pady=(0, 10))
            self._source_choice_cards.append(choice)
            self._source_choice_descriptions.append(detail)
            self._source_buttons.append(button)
        self._layout_source_choices()

        save_section = ctk.CTkFrame(capture_card, fg_color=_theme_color("#141E32"), corner_radius=12)
        self._record_save_section = save_section
        ctk.CTkLabel(
            save_section, text="3  Onde salvar", font=("Segoe UI", 17, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(13, 2))
        ctk.CTkLabel(
            save_section, text="O áudio é salvo antes de qualquer processamento.",
            font=("Segoe UI", 13), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16)
        output_row = ctk.CTkFrame(save_section, fg_color="transparent")
        output_row.pack(fill=tk.X, padx=16, pady=(12, 8))
        ctk.CTkLabel(
            output_row, text="Pasta", font=("Segoe UI", 13, "bold"),
            text_color=_COLORS["text"], width=90, anchor="w",
        ).pack(side=tk.LEFT)
        self.output_entry = ctk.CTkEntry(
            output_row, textvariable=self.output_dir, height=34, corner_radius=9,
            fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
            font=("Segoe UI", 13),
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.output_browse_button = ctk.CTkButton(
            output_row, text="Alterar", command=self._choose_output_dir, width=70, height=34,
            corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 12, "bold"),
        )
        self.output_browse_button.pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkLabel(
            save_section,
            text="Cada gravação terá uma pasta própria para o áudio e os documentos.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 9))
        timer_row = ctk.CTkFrame(save_section, fg_color="transparent")
        timer_row.pack(fill=tk.X, padx=16, pady=(0, 15))
        ctk.CTkLabel(
            timer_row, text="Parar após", font=("Segoe UI", 13, "bold"),
            text_color=_COLORS["text"], width=90, anchor="w",
        ).pack(side=tk.LEFT)
        self.recording_limit_entry = ctk.CTkEntry(
            timer_row, textvariable=self.recording_limit_value, placeholder_text="Sem limite",
            width=98, height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Segoe UI", 13),
        )
        self.recording_limit_entry.pack(side=tk.LEFT)
        self.recording_limit_selector = ctk.CTkComboBox(
            timer_row, variable=self.recording_limit_unit, values=["minutos", "horas"],
            state="readonly", width=106, height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"),
            dropdown_text_color=_COLORS["text"], font=("Segoe UI", 13),
        )
        self.recording_limit_selector.pack(side=tk.LEFT, padx=(8, 0))
        result_section = ctk.CTkFrame(capture_card, fg_color=_theme_color("#141E32"), corner_radius=12)
        self._record_result_section = result_section
        result_section.pack(fill=tk.X, pady=(0, 10))
        ctk.CTkLabel(
            result_section, text="2  Depois de parar", font=("Segoe UI", 17, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(13, 2))
        ctk.CTkLabel(
            result_section, text="Escolha o que o Voice Notes fará automaticamente.",
            font=("Segoe UI", 13), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16)
        recording_output_row = ctk.CTkFrame(result_section, fg_color="transparent")
        recording_output_row.pack(fill=tk.X, padx=16, pady=(12, 8))
        ctk.CTkLabel(
            recording_output_row, text="Resultado", font=("Segoe UI", 13, "bold"),
            text_color=_COLORS["text"], width=90, anchor="w",
        ).pack(side=tk.LEFT)
        self.recording_output_selector = ctk.CTkComboBox(
            recording_output_row, variable=self.recording_output_choice,
            values=[label for label, _code in _RECORDING_OUTPUT_OPTIONS],
            command=self._on_recording_output_choice, state="readonly", height=38,
            corner_radius=8, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 13),
        )
        self.recording_output_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(
            result_section, textvariable=self.recording_output_hint,
            font=("Segoe UI", 13), text_color=_theme_color("#C9D3FF"), anchor="w", wraplength=700,
        ).pack(fill=tk.X, padx=16, pady=(0, 13))
        self._recording_summary_preferences = ctk.CTkFrame(result_section, fg_color="transparent")
        preferences_row = ctk.CTkFrame(self._recording_summary_preferences, fg_color="transparent")
        preferences_row.pack(fill=tk.X, padx=16, pady=(0, 10))
        profile_field = ctk.CTkFrame(preferences_row, fg_color="transparent")
        profile_field.pack(fill=tk.X)
        ctk.CTkLabel(
            profile_field, text="Formato do resumo", font=("Segoe UI", 11, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.profile_selector = ctk.CTkComboBox(
            profile_field, variable=self.processing_profile, values=self._summary_profile_options(),
            state="readonly", height=34, corner_radius=9,
            fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"),
            button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 12),
        )
        self.profile_selector.pack(fill=tk.X)

        meeting_instructions_field = ctk.CTkFrame(self._recording_summary_preferences, fg_color="transparent")
        meeting_instructions_field.pack(fill=tk.X, padx=16, pady=(0, 14))
        ctk.CTkLabel(
            meeting_instructions_field, text="Instruções para este resumo (opcional)",
            font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.meeting_instructions_editor = ctk.CTkTextbox(
            meeting_instructions_field, height=58, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_width=1, border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
            font=("Segoe UI", 12), wrap="word",
        )
        self.meeting_instructions_editor.pack(fill=tk.X)
        ctk.CTkLabel(
            meeting_instructions_field,
            text="Ex.: priorize decisões, riscos e próximos passos. Será usada somente no próximo processamento.",
            font=("Segoe UI", 10), text_color=_COLORS["brand_muted"], anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))
        save_section.pack(fill=tk.X)

        # A janela estreita mantém as ações fixas durante a rolagem. Em telas
        # largas, as mesmas ações aparecem logo depois das opções de gravação.
        self._buttons = ctk.CTkFrame(main_shell, fg_color="transparent")
        self._buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
        self.start_button = ctk.CTkButton(
            self._buttons, text="Iniciar gravação", command=self._start_recording,
            height=42, corner_radius=13, fg_color=_COLORS["accent"],
            hover_color=_COLORS["accent_hover"], text_color=_COLORS["accent_text"],
            font=("Segoe UI", 14, "bold"),
        )
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = ctk.CTkButton(
            self._buttons, text="Parar", command=self._stop_recording,
            state=tk.DISABLED, width=90, height=42, corner_radius=13,
            fg_color=_theme_color("#27344D"), hover_color=_theme_color("#3A4865"), border_width=1,
            border_color=_COLORS["border"], text_color=_COLORS["text"],
            font=("Segoe UI", 13, "bold"),
        )
        self._inline_buttons = ctk.CTkFrame(content, fg_color="transparent")
        self.inline_start_button = ctk.CTkButton(
            self._inline_buttons, text="Iniciar gravação", command=self._start_recording,
            width=220, height=44, corner_radius=13, fg_color=_COLORS["accent"],
            hover_color=_COLORS["accent_hover"], text_color=_COLORS["accent_text"],
            font=("Segoe UI", 14, "bold"),
        )
        self.inline_start_button.pack(side=tk.LEFT)
        self.inline_stop_button = ctk.CTkButton(
            self._inline_buttons, text="Parar", command=self._stop_recording,
            state=tk.DISABLED, width=90, height=44, corner_radius=13,
            fg_color=_theme_color("#27344D"), hover_color=_theme_color("#3A4865"), border_width=1,
            border_color=_COLORS["border"], text_color=_COLORS["text"],
            font=("Segoe UI", 13, "bold"),
        )
        ctk.CTkLabel(
            self._inline_buttons, text="Você pode parar a qualquer momento.",
            font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT, padx=(18, 0))

        self._record_recent_panel = ctk.CTkFrame(
            content, fg_color=_theme_color("#111B2D"), corner_radius=12,
            border_width=1, border_color=_theme_color("#283750"),
        )
        recent_header = ctk.CTkFrame(self._record_recent_panel, fg_color="transparent")
        recent_header.pack(fill=tk.X, padx=18, pady=(12, 6))
        recent_heading = ctk.CTkFrame(recent_header, fg_color="transparent")
        recent_heading.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(
            recent_heading, text="Gravações recentes", font=("Segoe UI", 17, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X)
        ctk.CTkLabel(
            recent_heading, text="Continue um trabalho ou encontre o áudio salvo.",
            font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X)
        ctk.CTkButton(
            recent_header, text="Abrir Biblioteca", command=self._toggle_library,
            width=120, height=34, corner_radius=9, fg_color=_theme_color("#263550"),
            hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.RIGHT)
        recent_body = ctk.CTkFrame(self._record_recent_panel, fg_color="transparent")
        recent_body.pack(fill=tk.X, padx=18, pady=(0, 10))
        self._record_recent_list = ctk.CTkFrame(recent_body, fg_color="transparent")
        self._record_recent_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        activity = ctk.CTkFrame(recent_body, fg_color=_theme_color("#162239"), corner_radius=10, width=350)
        activity.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
        activity.pack_propagate(False)
        ctk.CTkLabel(
            activity, text="Processamentos", font=("Segoe UI", 15, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(18, 4))
        ctk.CTkLabel(
            activity, textvariable=self.queue_hint, font=("Segoe UI", 13),
            text_color=_theme_color("#C9D3FF"), anchor="w", wraplength=310,
        ).pack(fill=tk.X, padx=16)
        ctk.CTkLabel(
            activity, text="Acompanhe a fila, retome falhas e consulte os detalhes de cada etapa.",
            font=("Segoe UI", 12), text_color=_COLORS["muted"],
            anchor="w", justify=tk.LEFT, wraplength=310,
        ).pack(fill=tk.X, padx=16, pady=(10, 0))
        ctk.CTkButton(
            activity, text="Ver Processos", command=self._show_processing_page,
            height=36, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=16)

        # Configurações ocupam a mesma cápsula, preservando o cabeçalho e os
        # controles de janela para que a navegação nunca "desapareça".
        self._settings_panel = ctk.CTkFrame(
            content, fg_color=_theme_color("#0C1423"), corner_radius=16,
        )
        self._settings_kicker = ctk.CTkLabel(
            self._settings_panel, text="CONFIGURAÇÕES", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["accent"], anchor="w",
        )
        self._settings_kicker.pack(fill=tk.X, padx=18, pady=(18, 2))
        self._settings_description = ctk.CTkLabel(
            self._settings_panel, text="Preferências usadas na próxima gravação ou importação.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
        )
        self._settings_description.pack(fill=tk.X, padx=18, pady=(0, 8))
        settings_nav = ctk.CTkFrame(self._settings_panel, fg_color=_theme_color("#111A2C"), corner_radius=9)
        settings_nav.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._settings_navigation = settings_nav
        self._settings_section_buttons: dict[str, ctk.CTkButton] = {}
        settings_sections = [
            ("verification", "Verificação"), ("provider", "Provider e API"),
            ("profiles", "Resumos"), ("transcription", "Transcrição"), ("speakers", "Falantes"),
            ("appearance", "Aparência"),
        ]
        for index, (section, label) in enumerate(settings_sections):
            button = ctk.CTkButton(
                settings_nav, text=label, command=lambda key=section: self._show_settings_section(key),
                width=110, height=32, corner_radius=7, fg_color="transparent", hover_color=_theme_color("#22324F"),
                text_color=_COLORS["muted"], font=("Segoe UI", 9, "bold"),
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            self._settings_section_buttons[section] = button
            settings_nav.grid_columnconfigure(index, weight=1)
        self._settings_navigation_columns = len(settings_sections)
        settings_nav.bind("<Configure>", lambda event: self._layout_settings_navigation(event.width), add="+")
        self._settings_sections = {
            key: ctk.CTkFrame(self._settings_panel, fg_color="transparent")
            for key in ("verification", "provider", "profiles", "transcription", "speakers", "appearance")
        }

        def settings_card(parent: tk.Misc, title_text: str, detail: str) -> ctk.CTkFrame:
            card = ctk.CTkFrame(parent, fg_color=_theme_color("#111A2C"), corner_radius=12)
            card.pack(fill=tk.X, padx=14, pady=(0, 12))
            ctk.CTkLabel(card, text=title_text, font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=14, pady=(12, 0))
            ctk.CTkLabel(
                card, text=detail, font=("Segoe UI", 10), text_color=_COLORS["muted"],
                anchor="w", justify=tk.LEFT, wraplength=448,
            ).pack(fill=tk.X, padx=14, pady=(2, 10))
            return card

        appearance_card = settings_card(
            self._settings_sections["appearance"], "Tema de cores",
            "Escolha uma paleta para todas as telas. A mudança é imediata e fica salva para a próxima vez que abrir o Voice Notes.",
        )
        self._theme_choice_grid = ctk.CTkFrame(appearance_card, fg_color="transparent")
        self._theme_choice_grid.pack(fill=tk.X, padx=14, pady=(0, 12))
        self._theme_choice_buttons: dict[str, ctk.CTkButton] = {}
        for theme_name, theme_label in THEME_LABELS.items():
            palette = THEMES[theme_name]
            button = ctk.CTkButton(
                self._theme_choice_grid,
                text=f"●  {theme_label}",
                command=lambda selected=theme_name: self._select_color_theme(selected),
                height=36, corner_radius=8, border_width=1,
                fg_color=palette["surface_button"],
                hover_color=palette["surface_button_hover"],
                border_color=palette["accent"] if theme_name == self._theme_name else palette["border"],
                text_color=palette["text"], font=("Segoe UI", 10, "bold"),
            )
            self._theme_choice_buttons[theme_name] = button
        self._theme_choice_grid.bind(
            "<Configure>", lambda event: self._layout_theme_choices(event.width), add="+",
        )
        self._theme_choice_detail = ctk.CTkLabel(
            appearance_card, text=self._theme_detail_text(self._theme_name),
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
        )
        self._theme_choice_detail.pack(fill=tk.X, padx=14, pady=(0, 12))

        verification = self._settings_sections["verification"]
        readiness_card = settings_card(
            verification, "Verificar instalação",
            "Confira a pasta de saída, as fontes de áudio e as contas conectadas sem enviar gravações.",
        )
        self.installation_check_status = {
            key: tk.StringVar(value="Ainda não verificado")
            for key in ("output", "microphone", "system", "codex", "claude")
        }
        for key, label in [
            ("output", "Pasta de saída"), ("microphone", "Microfone"),
            ("system", "Áudio do sistema"), ("codex", "Conta Codex"),
            ("claude", "Conta Claude"),
        ]:
            row = ctk.CTkFrame(readiness_card, fg_color="transparent")
            row.pack(fill=tk.X, padx=14, pady=(0, 5))
            ctk.CTkLabel(row, text=label, width=120, anchor="w", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            ctk.CTkLabel(
                row, textvariable=self.installation_check_status[key], anchor="w",
                text_color=_COLORS["muted"], font=("Segoe UI", 9),
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.installation_check_button = ctk.CTkButton(
            readiness_card, text="Verificar agora", command=self._start_installation_check,
            height=34, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.installation_check_button.pack(fill=tk.X, padx=14, pady=(5, 12))

        model_card = settings_card(
            verification, "Whisper local",
            "O teste carrega o modelo selecionado e processa um áudio sintético. Na primeira vez, pode baixá-lo.",
        )
        ctk.CTkLabel(model_card, textvariable=self.local_transcription_test_status, anchor="w", text_color=_theme_color("#C9D3FF"), font=("Segoe UI", 9)).pack(fill=tk.X, padx=14, pady=(0, 5))
        self.install_local_test_button = ctk.CTkButton(
            model_card, text="Testar modelo selecionado", command=self._start_local_transcription_test,
            height=32, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.install_local_test_button.pack(fill=tk.X, padx=14, pady=(0, 12))

        provider_test_card = settings_card(
            verification, "Gerar resposta de teste",
            "Cada botão envia apenas um texto sintético curto. Pode consumir uso da conta escolhida.",
        )
        self.install_provider_test_buttons: dict[str, ctk.CTkButton] = {}
        for provider, label in (("codex", "Codex"), ("claude", "Claude")):
            ctk.CTkLabel(provider_test_card, text=label, anchor="w", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, padx=14, pady=(0, 2))
            ctk.CTkLabel(provider_test_card, textvariable=self._provider_test_status[provider], anchor="w", text_color=_theme_color("#C9D3FF"), font=("Segoe UI", 9)).pack(fill=tk.X, padx=14, pady=(0, 3))
            button = ctk.CTkButton(
                provider_test_card, text=f"Testar {label}",
                command=lambda selected=provider: self._start_provider_health_check(selected),
                height=30, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            )
            button.pack(fill=tk.X, padx=14, pady=(0, 10))
            self.install_provider_test_buttons[provider] = button

        processing_card = settings_card(self._settings_sections["provider"], "Resumo", "Escolha quem cria o resumo.")
        provider_row = ctk.CTkFrame(processing_card, fg_color="transparent")
        provider_row.pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkLabel(
            provider_row, text="Provider do resumo", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(side=tk.LEFT)
        self.provider_selector = ctk.CTkComboBox(
            provider_row, variable=self.summary_provider, values=self._summary_provider_options(),
            state="readonly", width=150, height=34, corner_radius=9,
            fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"),
            button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.provider_selector.pack(side=tk.RIGHT)
        ctk.CTkLabel(
            processing_card, textvariable=self.provider_hint, font=("Segoe UI", 9),
            text_color=_theme_color("#C9D3FF"), anchor="w", wraplength=470,
        ).pack(fill=tk.X, padx=14, pady=(0, 9))
        self.provider_login_button = ctk.CTkButton(
            processing_card, text="Conectar conta no navegador", command=self._start_provider_login,
            height=32, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.provider_setup_button = ctk.CTkButton(
            processing_card, text="Tentar instalar providers", command=self._prepare_local_providers,
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )

        self.api_provider_list = ctk.CTkFrame(processing_card, fg_color=_theme_color("#0D1525"), corner_radius=10)
        self.api_provider_list.pack(fill=tk.X, padx=14, pady=(0, 10))

        self.new_provider_button = ctk.CTkButton(
            processing_card, text="+ Novo Provider", command=self._toggle_api_provider_form,
            height=34, corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.new_provider_button.pack(fill=tk.X, padx=14, pady=(0, 10))

        self.api_card = ctk.CTkFrame(processing_card, fg_color=_theme_color("#0D1525"), corner_radius=10)
        self.api_form_title = ctk.CTkLabel(
            self.api_card, text="NOVO PROVIDER POR TOKEN", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        )
        self.api_form_title.pack(fill=tk.X, padx=10, pady=(10, 2))
        ctk.CTkLabel(self.api_card, text="Compatível com OpenAI ou endpoint JSON personalizado.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(0, 5))
        ctk.CTkLabel(self.api_card, text="Tipo de integração", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(4, 1))
        ctk.CTkComboBox(
            self.api_card, variable=self.api_protocol,
            values=["openai_compatible", "custom_json"], state="readonly", height=30,
            corner_radius=7, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X, padx=10, pady=(0, 3))
        for label, variable, secret in [
            ("Nome", self.api_provider_name, False),
            ("URL-base (ou URL completa no modo custom_json)", self.api_base_url, False),
            ("Modelo", self.api_model, False),
            ("Token", self.api_token, True),
        ]:
            ctk.CTkLabel(self.api_card, text=label, font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=10, pady=(4, 1))
            ctk.CTkEntry(self.api_card, textvariable=variable, show="•" if secret else "", height=30, corner_radius=7, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"]).pack(fill=tk.X, padx=10, pady=(0, 3))
        ctk.CTkLabel(
            self.api_card, textvariable=self.api_token_hint, font=("Segoe UI", 9),
            text_color=_COLORS["muted"], anchor="w", wraplength=450,
        ).pack(fill=tk.X, padx=10, pady=(0, 2))
        self.api_advanced_button = ctk.CTkButton(
            self.api_card, text="Opções avançadas", command=self._toggle_api_advanced,
            height=28, corner_radius=7, fg_color="transparent", hover_color=_theme_color("#1B2943"),
            text_color=_theme_color("#C9D3FF"), font=("Segoe UI", 9, "bold"),
        )
        self.api_advanced_button.pack(fill=tk.X, padx=10, pady=(5, 3))
        self.api_advanced_card = ctk.CTkFrame(self.api_card, fg_color=_theme_color("#080C16"), corner_radius=7)
        for label, variable in [
            ("Modelo de transcrição por API", self.api_transcription_model),
            ("Cabeçalho de autenticação", self.api_auth_header),
            ("Prefixo do token", self.api_auth_prefix),
            ("Caminho da resposta", self.api_response_path),
        ]:
            ctk.CTkLabel(self.api_advanced_card, text=label, font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=8, pady=(5, 1))
            ctk.CTkEntry(self.api_advanced_card, textvariable=variable, height=28, corner_radius=6, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"]).pack(fill=tk.X, padx=8, pady=(0, 2))
        ctk.CTkLabel(self.api_advanced_card, text="Corpo JSON: usado somente em custom_json.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=8, pady=(5, 1))
        self.api_request_template = ctk.CTkTextbox(self.api_advanced_card, height=56, corner_radius=6, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), border_width=1, text_color=_COLORS["text"], font=("Consolas", 9))
        self.api_request_template.insert("1.0", self.api_request_template_default)
        self.api_request_template.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.api_save_button = ctk.CTkButton(
            self.api_card, text="Salvar provider", command=self._save_api_provider,
            height=32, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.api_save_button.pack(fill=tk.X, padx=10, pady=(6, 10))
        self._render_api_provider_list()

        provider_test_card = settings_card(
            self._settings_sections["provider"], "Testar Codex e Claude",
            "Cada teste envia um texto sintético curto ao provider e pode consumir uso da sua conta.",
        )
        for provider_code, provider_label in (("codex", "Codex"), ("claude", "Claude Code")):
            row = ctk.CTkFrame(provider_test_card, fg_color="transparent")
            row.pack(fill=tk.X, padx=14, pady=(0, 8))
            ctk.CTkLabel(
                row, text=provider_label, width=94, font=("Segoe UI", 10, "bold"),
                text_color=_COLORS["text"], anchor="w",
            ).pack(side=tk.LEFT)
            status_label = ctk.CTkLabel(
                row, textvariable=self._provider_test_status[provider_code],
                font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
                justify=tk.LEFT, wraplength=300,
            )
            status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
            self._provider_test_labels[provider_code] = status_label
            test_button = ctk.CTkButton(
                row, text="Testar", command=lambda code=provider_code: self._start_provider_health_check(code),
                width=68, height=28, corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            )
            test_button.pack(side=tk.RIGHT)
            self._provider_test_buttons[provider_code] = test_button

        update_card = settings_card(
            self._settings_sections["provider"], "Atualizações", "Confira a versão instalada e instale uma nova versão quando ela estiver disponível.",
        )
        update_status = ctk.CTkFrame(
            update_card, fg_color=_theme_color("#0D1525"), corner_radius=8,
            border_width=1, border_color=_theme_color("#2A3A58"),
        )
        update_status.pack(fill=tk.X, padx=14, pady=(0, 9))
        ctk.CTkLabel(
            update_status, text="ESTADO DA ATUALIZAÇÃO", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(8, 1))
        ctk.CTkLabel(
            update_status, textvariable=self.update_hint, font=("Segoe UI", 10), text_color=_theme_color("#C9D3FF"),
            anchor="w", justify=tk.LEFT, wraplength=448,
        ).pack(fill=tk.X, padx=10, pady=(0, 8))
        update_actions = ctk.CTkFrame(update_card, fg_color="transparent")
        update_actions.pack(fill=tk.X, padx=14, pady=(0, 12))
        self.update_apply_button = ctk.CTkButton(
            update_actions, text="Atualizar agora", command=self._apply_update, state=tk.DISABLED,
            width=124, height=34, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], text_color_disabled=_theme_color("#72809A"), font=("Segoe UI", 10, "bold"),
        )
        self.update_apply_button.pack(side=tk.RIGHT)
        self.update_check_button = ctk.CTkButton(
            update_actions, text="Verificar agora", command=self._check_for_updates,
            width=142, height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        )
        self.update_check_button.pack(side=tk.RIGHT, padx=(0, 6))

        support_card = settings_card(
            self._settings_sections["provider"], "Curtiu o Voice Notes?", "Se ele te salvou em uma reunião, aula ou ideia de última hora, um apoio ajuda a manter o projeto vivo.",
        )
        ctk.CTkButton(
            support_card, text="Apoiar o projeto", command=self._open_pix_support,
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(fill=tk.X, padx=14, pady=(0, 12))

        profiles_card = settings_card(
            self._settings_sections["profiles"], "Formatos e perfis de resumo",
            "Consulte os prompts dos formatos nativos ou crie um perfil salvo com suas próprias instruções.",
        )
        self.summary_profile_list = ctk.CTkFrame(profiles_card, fg_color=_theme_color("#0D1525"), corner_radius=10)
        self.summary_profile_list.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.new_summary_profile_button = ctk.CTkButton(
            profiles_card, text="+ Novo perfil", command=self._open_new_summary_profile_dialog,
            height=34, corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.new_summary_profile_button.pack(fill=tk.X, padx=14, pady=(0, 10))
        self._render_summary_profile_list()

        transcription_card = settings_card(self._settings_sections["transcription"], "Transcrição", "Idioma e qualidade do texto transcrito.")
        self._api_form_anchor = self.new_provider_button
        transcript_row = ctk.CTkFrame(transcription_card, fg_color="transparent")
        transcript_row.pack(fill=tk.X, padx=14, pady=(0, 12))
        model_field = ctk.CTkFrame(transcript_row, fg_color="transparent")
        model_field.pack(fill=tk.X)
        ctk.CTkLabel(model_field, text="Modelo Whisper", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
        ctk.CTkComboBox(
            model_field, variable=self.pipeline_model, values=self._available_models,
            state="readonly", height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X)
        model_note = ctk.CTkFrame(model_field, height=25, fg_color=_theme_color("#0D1525"), corner_radius=7)
        model_note.pack(fill=tk.X, pady=(6, 0))
        model_note.pack_propagate(False)
        ctk.CTkLabel(model_note, textvariable=self.model_description, text_color=_theme_color("#C9D3FF"), font=("Segoe UI", 9), anchor="w").pack(fill=tk.BOTH, padx=8)
        source_field = ctk.CTkFrame(transcript_row, fg_color="transparent")
        source_field.pack(fill=tk.X, pady=(12, 0))
        ctk.CTkLabel(
            source_field, text="Fonte da transcrição", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.transcription_source_selector = ctk.CTkComboBox(
            source_field, variable=self.transcription_source, values=self._transcription_source_options(),
            state="readonly", height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.transcription_source_selector.pack(fill=tk.X)
        ctk.CTkLabel(
            source_field, textvariable=self.transcription_source_hint, text_color=_theme_color("#C9D3FF"),
            font=("Segoe UI", 9), anchor="w", justify=tk.LEFT, wraplength=448,
        ).pack(fill=tk.X, pady=(5, 0))
        language_field = ctk.CTkFrame(transcript_row, fg_color="transparent")
        language_field.pack(fill=tk.X, pady=(12, 0))
        ctk.CTkLabel(language_field, text="Idioma", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
        ctk.CTkComboBox(
            language_field, variable=self.pipeline_language, values=_LANG_LABELS,
            state="readonly", height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(fill=tk.X)
        local_test_card = settings_card(
            self._settings_sections["transcription"], "Teste do Whisper local",
            "Carrega o modelo selecionado e processa um áudio de teste temporário. Na primeira vez, o modelo pode ser baixado; nenhum áudio seu é enviado.",
        )
        local_test_row = ctk.CTkFrame(local_test_card, fg_color="transparent")
        local_test_row.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.local_transcription_test_label = ctk.CTkLabel(
            local_test_row, textvariable=self.local_transcription_test_status,
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
            justify=tk.LEFT, wraplength=300,
        )
        self.local_transcription_test_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.local_transcription_test_button = ctk.CTkButton(
            local_test_row, text="Testar modelo", command=self._start_local_transcription_test,
            width=108, height=30, corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.local_transcription_test_button.pack(side=tk.RIGHT)

        speakers_card = settings_card(self._settings_sections["speakers"], "Falantes", "Opcional: identifica Pessoa 1, Pessoa 2 e assim por diante.")
        diarization_row = ctk.CTkFrame(speakers_card, fg_color="transparent")
        diarization_row.pack(fill=tk.X, padx=14, pady=(0, 12))
        ctk.CTkCheckBox(
            diarization_row, text="Separar falantes (Pessoa 1, Pessoa 2)", variable=self.diarize_speakers,
            fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            diarization_row, text="Desligado por padrão para processar mais rápido. Ative quando precisar identificar falantes.",
            text_color=_COLORS["muted"], font=("Segoe UI", 9), anchor="w",
        ).pack(anchor=tk.W, pady=(3, 8))
        ctk.CTkLabel(
            diarization_row, text="TOKEN DO HUGGING FACE", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self.huggingface_token_entry = ctk.CTkEntry(
            diarization_row, textvariable=self.huggingface_token, show="•",
            placeholder_text="Token de leitura do Hugging Face", height=32, corner_radius=8,
            fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
        )
        self.huggingface_token_entry.pack(fill=tk.X)
        token_actions = ctk.CTkFrame(diarization_row, fg_color="transparent")
        token_actions.pack(fill=tk.X, pady=(8, 0))
        self.huggingface_token_visibility_button = ctk.CTkButton(
            token_actions, text="Mostrar", command=self._toggle_huggingface_token_visibility,
            width=76, height=29, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.huggingface_token_visibility_button.pack(side=tk.LEFT)
        ctk.CTkButton(
            token_actions, text="Copiar", command=self._copy_huggingface_token,
            width=68, height=29, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ctk.CTkButton(
            token_actions, text="Salvar token", command=self._save_huggingface_token,
            width=94, height=29, corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT)

        self._file_panel = ctk.CTkFrame(
            content, fg_color=_theme_color("#111A2C"), corner_radius=16,
            border_width=1, border_color=_theme_color("#253552"),
        )
        ctk.CTkLabel(
            self._file_panel, text="IMPORTAR ARQUIVO", font=("Segoe UI", 11, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 1))
        ctk.CTkLabel(
            self._file_panel, text="Selecione um áudio ou vídeo. O original permanece no lugar; uma cópia vai para a Biblioteca.",
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w", wraplength=500,
        ).pack(fill=tk.X, padx=16, pady=(0, 10))
        file_settings = ctk.CTkFrame(self._file_panel, fg_color=_theme_color("#0D1525"), corner_radius=10)
        file_settings.pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkLabel(
            file_settings, text="CONFIGURAÇÃO DESTE ARQUIVO", font=("Segoe UI", 9, "bold"),
            text_color=_theme_color("#C9D3FF"), anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 2))
        ctk.CTkLabel(
            file_settings, text="Estas escolhas valem somente para o próximo áudio ou vídeo selecionado.",
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

        def file_setting_label(text: str) -> None:
            ctk.CTkLabel(
                file_settings, text=text, font=("Segoe UI", 9, "bold"),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, padx=12, pady=(0, 3))

        file_setting_label("FONTE DA TRANSCRIÇÃO")
        self.file_transcription_source_selector = ctk.CTkComboBox(
            file_settings, variable=self.file_transcription_source,
            values=self._transcription_source_options(), state="readonly", height=32, corner_radius=8,
            fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"),
            button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.file_transcription_source_selector.pack(fill=tk.X, padx=12, pady=(0, 8))
        file_setting_label("IDIOMA E MODELO")
        file_transcription_row = ctk.CTkFrame(file_settings, fg_color="transparent")
        file_transcription_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.file_language_selector = ctk.CTkComboBox(
            file_transcription_row, variable=self.file_pipeline_language, values=_LANG_LABELS,
            state="readonly", height=32, corner_radius=8, width=200, fg_color=_theme_color("#080C16"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.file_language_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.file_model_selector = ctk.CTkComboBox(
            file_transcription_row, variable=self.file_pipeline_model, values=self._available_models,
            state="readonly", height=32, corner_radius=8, width=132, fg_color=_theme_color("#080C16"),
            border_color=_theme_color("#2A3A58"), button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.file_model_selector.pack(side=tk.LEFT, padx=(8, 0))
        file_setting_label("PROVIDER DO RESUMO")
        self.file_summary_provider_selector = ctk.CTkComboBox(
            file_settings, variable=self.file_summary_provider, values=self._summary_provider_options(),
            state="readonly", height=32, corner_radius=8, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.file_summary_provider_selector.pack(fill=tk.X, padx=12, pady=(0, 7))
        file_setting_label("PERFIL DO RESUMO")
        self.file_profile_selector = ctk.CTkComboBox(
            file_settings, variable=self.file_processing_profile, values=self._summary_profile_options(),
            state="readonly", height=32, corner_radius=8, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.file_profile_selector.pack(fill=tk.X, padx=12, pady=(0, 8))
        ctk.CTkCheckBox(
            file_settings, text="Separar falantes (Pessoa 1, Pessoa 2)", variable=self.file_diarize_speakers,
            fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, padx=12)
        ctk.CTkLabel(
            file_settings, text="Deixe desligado quando houver apenas uma pessoa. Se falhar, a transcrição continuará sem os nomes.",
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w", wraplength=455,
        ).pack(fill=tk.X, padx=12, pady=(3, 10))
        self.process_button = ctk.CTkButton(
            self._file_panel, text="Escolher áudio ou vídeo", command=self._process_existing_media,
            height=42, corner_radius=10, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 11, "bold"),
        )
        self.process_button.pack(fill=tk.X, padx=14, pady=(0, 8))
        self.text_import_button = ctk.CTkButton(
            self._file_panel, text="Colar ou abrir transcrição", command=self._toggle_text_import,
            height=38, corner_radius=10, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 11, "bold"),
        )
        self.text_import_button.pack(fill=tk.X, padx=14, pady=(0, 8))
        self._text_import_panel = ctk.CTkFrame(self._file_panel, fg_color=_theme_color("#0D1525"), corner_radius=10)
        ctk.CTkLabel(
            self._text_import_panel, text="TRANSCRIÇÃO PRONTA", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 2))
        self.import_text_editor = ctk.CTkTextbox(
            self._text_import_panel, height=100, corner_radius=8, fg_color=_theme_color("#080C16"),
            border_width=1, border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Consolas", 10), wrap="word",
        )
        self.import_text_editor.pack(fill=tk.X, padx=12, pady=(0, 7))
        text_import_actions = ctk.CTkFrame(self._text_import_panel, fg_color="transparent")
        text_import_actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.import_text_load_button = ctk.CTkButton(
            text_import_actions, text="Abrir .txt/.md", command=self._load_text_import,
            width=104, height=30, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.import_text_load_button.pack(side=tk.LEFT)
        self.import_text_save_button = ctk.CTkButton(
            text_import_actions, text="Salvar", command=self._save_imported_text,
            width=72, height=30, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.import_text_save_button.pack(side=tk.RIGHT)
        self.import_text_summary_button = ctk.CTkButton(
            text_import_actions, text="Salvar e gerar resumo", command=self._save_imported_text_and_regenerate,
            height=30, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 9, "bold"),
        )
        self.import_text_summary_button.pack(side=tk.RIGHT, padx=(0, 6))
        ctk.CTkFrame(self._file_panel, height=1, fg_color=_theme_color("#253552")).pack(fill=tk.X, padx=14, pady=(6, 10))
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
            fg_color=_theme_color("#244462"),
            hover_color=_theme_color("#315A80"),
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
            content, fg_color=_theme_color("#111A2C"), corner_radius=16,
            border_width=1, border_color=_theme_color("#253552"),
        )
        ctk.CTkLabel(self._youtube_panel, text="IMPORTAR DO YOUTUBE", font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=16, pady=(16, 1))
        ctk.CTkLabel(self._youtube_panel, text="Baixe o áudio de um vídeo autorizado e escolha como processar.", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(0, 14))
        ctk.CTkLabel(self._youtube_panel, text="LINK DO VÍDEO", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(0, 3))
        self.youtube_url_entry = ctk.CTkEntry(
            self._youtube_panel, textvariable=self.youtube_url,
            placeholder_text="https://www.youtube.com/watch?v=...", height=34, corner_radius=9,
            fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_url_entry.pack(fill=tk.X, padx=16)
        ctk.CTkLabel(self._youtube_panel, text="O QUE FAZER", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 3))
        self.youtube_mode_selector = ctk.CTkComboBox(
            self._youtube_panel, variable=self.youtube_mode,
            values=["Transcrição e resumo", "Só transcrição", "Só resumo"], state="readonly",
            height=32, corner_radius=8, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_mode_selector.pack(fill=tk.X, padx=16)
        ctk.CTkLabel(self._youtube_panel, text="FORMATO DO RESUMO", font=("Segoe UI", 9, "bold"), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 3))
        self.youtube_profile_selector = ctk.CTkComboBox(
            self._youtube_panel, variable=self.processing_profile, values=self._summary_profile_options(), state="readonly",
            height=32, corner_radius=8, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        self.youtube_profile_selector.pack(fill=tk.X, padx=16)
        self.youtube_process_button = ctk.CTkButton(
            self._youtube_panel, text="Baixar áudio e processar", command=self._process_youtube,
            height=42, corner_radius=10, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 11, "bold"),
        )
        self.youtube_process_button.pack(fill=tk.X, padx=16, pady=(12, 4))
        self._youtube_hint_label = ctk.CTkLabel(
            self._youtube_panel, textvariable=self.youtube_hint, font=("Segoe UI", 9),
            text_color=_COLORS["muted"], anchor="w",
        )
        self._youtube_hint_label.pack(fill=tk.X, padx=17, pady=(0, 12))

        # Biblioteca local: permanece dentro do widget para não fragmentar a tarefa
        # entre janelas pequenas. Ela indexa as pastas já criadas pelo pipeline.
        self._library_panel = ctk.CTkFrame(
            content, fg_color=_theme_color("#111A2C"), corner_radius=14,
            border_width=1, border_color=_theme_color("#2A3A58"),
        )
        library_header = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        library_header.pack(fill=tk.X, padx=14, pady=(12, 7))
        ctk.CTkLabel(
            library_header, text="BIBLIOTECA", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        self.library_refresh_button = ctk.CTkButton(
            library_header, text="Atualizar", command=self._refresh_library, width=78, height=28,
            corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.library_refresh_button.pack(side=tk.RIGHT)
        library_folder = ctk.CTkFrame(self._library_panel, fg_color=_theme_color("#0D1525"), corner_radius=9)
        library_folder.pack(fill=tk.X, padx=14, pady=(0, 8))
        ctk.CTkLabel(
            library_folder, text="PASTA EXIBIDA", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(9, 3))
        library_folder_row = ctk.CTkFrame(library_folder, fg_color="transparent")
        library_folder_row.pack(fill=tk.X, padx=12, pady=(0, 5))
        self.library_folder_entry = ctk.CTkEntry(
            library_folder_row, textvariable=self.library_dir, state="readonly",
            height=34, corner_radius=8, fg_color=_theme_color("#0A1324"), border_color=_theme_color("#2A3A58"),
            text_color=_COLORS["text"], font=("Segoe UI", 11),
        )
        self.library_folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_choose_button = ctk.CTkButton(
            library_folder_row, text="Escolher pasta", command=self._choose_library_dir,
            width=120, height=34, corner_radius=8, fg_color=_theme_color("#244462"),
            hover_color=_theme_color("#315A80"), text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
        )
        self.library_choose_button.pack(side=tk.LEFT, padx=(8, 0))
        self.library_use_recording_button = ctk.CTkButton(
            library_folder_row, text="Pasta de Gravar", command=self._use_recording_library_dir,
            width=130, height=34, corner_radius=8, fg_color=_theme_color("#263550"),
            hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
            state=tk.NORMAL if self._library_directory_manual else tk.DISABLED,
        )
        self.library_use_recording_button.pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkLabel(
            library_folder,
            text="Trocar esta pasta não altera o destino das novas gravações.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 8))
        queue_row = ctk.CTkFrame(self._library_panel, fg_color=_theme_color("#0D1525"), corner_radius=8)
        queue_row.pack(fill=tk.X, padx=14, pady=(0, 7))
        ctk.CTkLabel(
            queue_row, textvariable=self.queue_hint, font=("Segoe UI", 10, "bold"),
            text_color=_theme_color("#C9D3FF"), anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 4), pady=7)
        self.retry_queue_button = ctk.CTkButton(
            queue_row, text="Retomar", command=self._retry_pending_jobs, width=70, height=26,
            corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.retry_queue_button.pack(side=tk.RIGHT, padx=5, pady=4)
        self._library_queue_row = queue_row
        self.library_summary_progress_text = tk.StringVar(value="")
        self._library_summary_progress = ctk.CTkFrame(
            self._library_panel, fg_color=_theme_color("#17213A"), corner_radius=9,
            border_width=1, border_color=_theme_color("#34476B"),
        )
        ctk.CTkLabel(
            self._library_summary_progress, textvariable=self.library_summary_progress_text,
            font=("Segoe UI", 10, "bold"), text_color=_theme_color("#D8D4FF"), anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(8, 3))
        self.library_summary_progressbar = ctk.CTkProgressBar(
            self._library_summary_progress, height=4, corner_radius=2, mode="indeterminate",
            fg_color=_theme_color("#263550"), progress_color=_COLORS["accent"],
        )
        self.library_summary_progressbar.pack(fill=tk.X, padx=10, pady=(0, 8))
        self._library_columns = ctk.CTkFrame(self._library_panel, fg_color="transparent")
        self._library_columns.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))
        self._library_browser = ctk.CTkFrame(
            self._library_columns, fg_color=_theme_color("#0D1525"), corner_radius=10,
        )
        self._library_browser.pack(fill=tk.BOTH, expand=True)
        self._library_details = ctk.CTkScrollableFrame(
            self._library_columns, fg_color=_theme_color("#17213A"), corner_radius=10,
            scrollbar_button_color=_theme_color("#34476B"), scrollbar_button_hover_color=_theme_color("#405B83"),
        )
        self._library_details.pack(fill=tk.X, pady=(10, 0))
        ctk.CTkLabel(
            self._library_browser, text="BUSCAR POR TÍTULO, ARQUIVO OU ETIQUETA", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(12, 4))
        library_search_row = ctk.CTkFrame(self._library_browser, fg_color="transparent")
        library_search_row.pack(fill=tk.X, padx=14, pady=(0, 7))
        self.library_search_entry = ctk.CTkEntry(
            library_search_row, textvariable=self.library_search,
            placeholder_text="Buscar por título, arquivo ou etiqueta", height=34, corner_radius=9,
            fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.library_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._library_tag_values = ["Todas as etiquetas"]
        self.library_tag_selector = ctk.CTkButton(
            library_search_row, text="Todas as etiquetas  ▾",
            command=lambda: self._show_library_choice_menu(
                self.library_tag_selector, self.library_tag_filter, self._library_tag_values,
            ),
            width=180, height=34, corner_radius=8, fg_color=_theme_color("#1A2A45"),
            hover_color=_theme_color("#304769"), text_color=_COLORS["text"],
            font=("Segoe UI", 10), anchor="w",
        )
        self.library_tag_selector.pack(side=tk.RIGHT, padx=(8, 0))
        self.library_tag_filter.trace_add(
            "write", lambda *_: self.library_tag_selector.configure(text=f"{self.library_tag_filter.get()}  ▾")
        )
        self.library_search.trace_add("write", lambda *_: self._schedule_library_render())
        library_options = ctk.CTkFrame(self._library_browser, fg_color="transparent")
        library_options.pack(fill=tk.X, padx=14, pady=(0, 4))
        filter_group = ctk.CTkFrame(library_options, fg_color="transparent")
        filter_group.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ctk.CTkLabel(
            filter_group, text="MOSTRAR", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self._library_filter_values = ["Todas", "Favoritos", "Resumo pronto", "Resumo pendente", "Só áudio"]
        self.library_filter_selector = ctk.CTkButton(
            filter_group, text=self.library_filter.get(),
            command=lambda: self._show_library_choice_menu(
                self.library_filter_selector, self.library_filter, self._library_filter_values,
            ),
            height=34, corner_radius=8, fg_color=_theme_color("#1A2A45"), hover_color=_theme_color("#304769"),
            text_color=_COLORS["text"], font=("Segoe UI", 10), anchor="w",
        )
        self.library_filter_selector.pack(fill=tk.X)
        sort_group = ctk.CTkFrame(library_options, fg_color="transparent")
        sort_group.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        ctk.CTkLabel(
            sort_group, text="ORDENAR", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))
        self._library_sort_values = ["Mais recentes", "Mais antigos", "Título A–Z", "Favoritos primeiro"]
        self.library_sort_selector = ctk.CTkButton(
            sort_group, text=self.library_sort.get(),
            command=lambda: self._show_library_choice_menu(
                self.library_sort_selector, self.library_sort, self._library_sort_values,
            ),
            height=34, corner_radius=8, fg_color=_theme_color("#1A2A45"), hover_color=_theme_color("#304769"),
            text_color=_COLORS["text"], font=("Segoe UI", 10), anchor="w",
        )
        self.library_sort_selector.pack(fill=tk.X)
        self.library_filter.trace_add(
            "write", lambda *_: self.library_filter_selector.configure(text=f"{self.library_filter.get()}  ▾")
        )
        self.library_sort.trace_add(
            "write", lambda *_: self.library_sort_selector.configure(text=f"{self.library_sort.get()}  ▾")
        )
        self.library_filter_selector.configure(text=f"{self.library_filter.get()}  ▾")
        self.library_sort_selector.configure(text=f"{self.library_sort.get()}  ▾")
        self.library_filter.trace_add("write", lambda *_: self._render_library_list())
        self.library_tag_filter.trace_add("write", lambda *_: self._render_library_list())
        self.library_sort.trace_add("write", lambda *_: self._render_library_list())
        ctk.CTkLabel(
            self._library_browser, textvariable=self.library_count, font=("Segoe UI", 8),
            text_color=_COLORS["muted"], anchor="e",
        ).pack(fill=tk.X, padx=16, pady=(0, 4))
        library_list_area = ctk.CTkFrame(self._library_browser, fg_color="transparent")
        library_list_area.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 7))
        self.library_items_frame = ctk.CTkScrollableFrame(
            library_list_area, height=350, fg_color=_theme_color("#0A1324"), corner_radius=8,
            scrollbar_button_color=_theme_color("#263550"), scrollbar_button_hover_color=_theme_color("#34476B"),
        )
        self.library_items_frame.pack(fill=tk.BOTH, expand=True)
        self._library_rows: list[ctk.CTkFrame] = []
        self._library_row_selectors: list[ctk.CTkLabel] = []
        self._library_empty_panel: ctk.CTkFrame | None = None
        self._library_selected_key = ""
        self.library_detail_title = tk.StringVar(value="Selecione uma gravação")
        ctk.CTkLabel(
            self._library_details, text="DETALHES DA GRAVAÇÃO", font=("Segoe UI", 11, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(10, 5))
        ctk.CTkLabel(
            self._library_details, textvariable=self.library_detail_title,
            font=("Segoe UI", 16, "bold"), text_color=_COLORS["text"], anchor="w",
            wraplength=430, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=16, pady=(0, 4))
        ctk.CTkLabel(
            self._library_details, textvariable=self.library_detail,
            font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
            wraplength=430, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=16, pady=(0, 6))
        self._library_selection_content = ctk.CTkFrame(self._library_details, fg_color="transparent")
        self._library_selection_content.pack(fill=tk.X)
        ctk.CTkLabel(
            self._library_selection_content, text="CONTEÚDO", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 4))
        self._library_file_names: dict[str, tk.StringVar] = {}
        self._library_asset_actions: dict[str, ctk.CTkFrame] = {}
        for kind in ("ÁUDIO", "TRANSCRIÇÃO", "RESUMO"):
            asset = ctk.CTkFrame(
                self._library_selection_content, fg_color=_theme_color("#0D1525"), corner_radius=9,
                border_width=1, border_color=_theme_color("#263550"),
            )
            asset.pack(fill=tk.X, padx=14, pady=(0, 6))
            asset_description = ctk.CTkFrame(asset, fg_color="transparent")
            asset_description.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 4), pady=8)
            ctk.CTkLabel(
                asset_description, text=kind, font=("Segoe UI", 10, "bold"),
                text_color=_theme_color("#AFC2EA"), anchor="w",
            ).pack(fill=tk.X)
            filename = tk.StringVar(value="—")
            self._library_file_names[kind] = filename
            ctk.CTkLabel(
                asset_description, textvariable=filename, font=("Segoe UI", 10),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X)
            actions = ctk.CTkFrame(asset, fg_color="transparent")
            actions.pack(side=tk.RIGHT, padx=(2, 10), pady=9)
            self._library_asset_actions[kind] = actions

        self.library_process_button = ctk.CTkButton(
            self._library_asset_actions["TRANSCRIÇÃO"], text="Transcrever + resumir", command=self._process_selected_library_audio,
            width=155, height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_summary_button = ctk.CTkButton(
            self._library_asset_actions["RESUMO"], text="Gerar resumo", command=self._regenerate_selected_summary,
            width=124, height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_audio_button = ctk.CTkButton(
            self._library_asset_actions["ÁUDIO"], text="Ouvir áudio", command=self._open_selected_audio,
            width=124, height=34, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_edit_button = ctk.CTkButton(
            self._library_asset_actions["TRANSCRIÇÃO"], text="Ler / editar", command=self._edit_selected_transcript,
            width=124, height=34, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_open_summary_button = ctk.CTkButton(
            self._library_asset_actions["RESUMO"], text="Ler / editar", command=self._open_selected_summary,
            width=124, height=34, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )

        library_organization = ctk.CTkFrame(self._library_selection_content, fg_color="transparent")
        library_organization.pack(fill=tk.X, padx=14, pady=(0, 8))
        ctk.CTkLabel(
            library_organization, text="ORGANIZAR", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=2, pady=(0, 5))
        organization_buttons = ctk.CTkFrame(library_organization, fg_color="transparent")
        organization_buttons.pack(fill=tk.X)
        self.library_favorite_button = ctk.CTkButton(
            organization_buttons, text="☆ Favoritar", command=self._toggle_selected_library_favorite,
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_favorite_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_metadata_button = ctk.CTkButton(
            organization_buttons, text="Editar título e etiquetas", command=self._edit_selected_library_metadata,
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_metadata_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        self.library_tags_text = tk.StringVar(value="")
        ctk.CTkLabel(
            library_organization, textvariable=self.library_tags_text, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w", wraplength=420, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=2, pady=(6, 0))
        location_row = ctk.CTkFrame(library_organization, fg_color="transparent")
        location_row.pack(fill=tk.X, pady=(5, 0))
        self.library_location_text = tk.StringVar(value="")
        ctk.CTkLabel(
            location_row, textvariable=self.library_location_text, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.library_open_button = ctk.CTkButton(
            location_row, text="Abrir pasta", command=self._open_selected_folder,
            width=104, height=30, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.library_open_button.pack(side=tk.RIGHT)
        self._library_exports = ctk.CTkFrame(self._library_selection_content, fg_color="transparent")
        self._library_exports.pack(fill=tk.X, padx=14, pady=(0, 8))
        ctk.CTkLabel(
            self._library_exports, text="EXPORTAR DOCUMENTO", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=2, pady=(0, 5))
        export_buttons = ctk.CTkFrame(self._library_exports, fg_color="transparent")
        export_buttons.pack(fill=tk.X)
        self.library_export_docx_button = ctk.CTkButton(
            export_buttons, text="Exportar DOCX", command=lambda: self._export_selected_document("docx"),
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_export_docx_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.library_export_pdf_button = ctk.CTkButton(
            export_buttons, text="Exportar PDF", command=lambda: self._export_selected_document("pdf"),
            height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_export_pdf_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        self.library_preview_text = tk.StringVar(value="")
        self._library_preview = ctk.CTkFrame(self._library_selection_content, fg_color=_theme_color("#0D1525"), corner_radius=10)
        self._library_preview.pack(fill=tk.X, padx=14, pady=(0, 12))
        ctk.CTkLabel(
            self._library_preview, text="PRÉVIA DO DOCUMENTO", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 5))
        ctk.CTkLabel(
            self._library_preview, textvariable=self.library_preview_text, font=("Segoe UI", 11),
            text_color=_COLORS["text"], anchor="w", justify=tk.LEFT, wraplength=410,
        ).pack(fill=tk.X, padx=14, pady=(0, 12))
        self._library_editor = ctk.CTkFrame(self._library_details, fg_color=_theme_color("#0D1525"), corner_radius=10)
        ctk.CTkLabel(
            self._library_editor, textvariable=self.library_editor_title, font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 4))
        self.transcript_editor = ctk.CTkTextbox(
            self._library_editor, height=90, corner_radius=8, fg_color=_theme_color("#080C16"),
            border_width=1, border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
            font=("Consolas", 10), wrap="word",
        )
        self.transcript_editor.pack(fill=tk.X, padx=12, pady=(0, 8))
        editor_actions = ctk.CTkFrame(self._library_editor, fg_color="transparent")
        editor_actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.library_suggest_names_button = ctk.CTkButton(
            editor_actions, text="Nomear falantes", command=self._open_speaker_names_dialog,
            width=92, height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.library_suggest_names_button.pack(side=tk.LEFT)
        ctk.CTkButton(
            editor_actions, text="Cancelar", command=self._close_transcript_editor,
            width=82, height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        self.library_save_button = ctk.CTkButton(
            editor_actions, text="Salvar", command=self._save_open_document,
            width=66, height=32, corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_save_button.pack(side=tk.RIGHT, padx=(0, 7))
        self.library_regenerate_button = ctk.CTkButton(
            editor_actions, text="Salvar e gerar resumo", command=self._save_transcript_and_regenerate,
            height=32, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_regenerate_button.pack(side=tk.RIGHT, padx=(0, 7))

        self._processing_panel = ctk.CTkFrame(
            content, fg_color=_theme_color("#111A2C"), corner_radius=14, border_width=1, border_color=_theme_color("#2A3A58"),
        )
        processing_header = ctk.CTkFrame(self._processing_panel, fg_color="transparent")
        processing_header.pack(fill=tk.X, padx=14, pady=(12, 4))
        ctk.CTkLabel(
            processing_header, text="PROCESSAMENTOS", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            processing_header, text="Atualizar", command=self._refresh_processing_page, width=78, height=28,
            corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT)
        self.processing_overview = tk.StringVar(value="Nenhum processamento na fila")
        ctk.CTkLabel(
            self._processing_panel, textvariable=self.processing_overview, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w", wraplength=500, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=14, pady=(0, 10))
        self.processing_job_list = ctk.CTkFrame(self._processing_panel, fg_color=_theme_color("#0D1525"), corner_radius=10)
        self.processing_job_list.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

        # Barra de progresso do pipeline
        self.progressbar = ctk.CTkProgressBar(
            content, height=4, corner_radius=2, fg_color=_theme_color("#1C2941"),
            progress_color=_COLORS["accent"], mode="indeterminate",
        )
        self.progressbar.set(0)
        self._processing_actions = ctk.CTkFrame(content, fg_color="transparent")
        self.cancel_processing_button = ctk.CTkButton(
            self._processing_actions, text="Cancelar processamento", command=self._request_cancel_processing,
            height=32, corner_radius=8, fg_color=_theme_color("#3A2637"), hover_color=_theme_color("#573248"),
            text_color=_COLORS["danger"], font=("Segoe UI", 10, "bold"), state=tk.DISABLED,
        )
        self.cancel_processing_button.pack(side=tk.RIGHT)
        self.processing_feedback_label = ctk.CTkLabel(
            self._processing_actions, textvariable=self._processing_feedback, font=("Segoe UI", 9),
            text_color=_COLORS["muted"], anchor="w",
        )
        self.processing_feedback_label.pack(side=tk.LEFT)

        def desktop_context(
            title: str, description: str, steps: tuple[tuple[str, str], ...],
            action_text: str, action: Callable[[], None], height: int,
        ) -> ctk.CTkFrame:
            panel = ctk.CTkFrame(
                content, width=410, height=height, fg_color=_theme_color("#141E32"),
                corner_radius=14, border_width=1, border_color=_theme_color("#2A3A58"),
            )
            panel.pack_propagate(False)
            ctk.CTkLabel(
                panel, text=title, font=("Segoe UI", 18, "bold"),
                text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X, padx=20, pady=(22, 4))
            ctk.CTkLabel(
                panel, text=description, font=("Segoe UI", 13),
                text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT, wraplength=365,
            ).pack(fill=tk.X, padx=20, pady=(0, 20))
            for number, (heading, body) in enumerate(steps, 1):
                step = ctk.CTkFrame(panel, fg_color=_theme_color("#0D1525"), corner_radius=9)
                step.pack(fill=tk.X, padx=16, pady=(0, 10))
                ctk.CTkLabel(
                    step, text=f"{number}  {heading}", font=("Segoe UI", 13, "bold"),
                    text_color=_COLORS["text"], anchor="w",
                ).pack(fill=tk.X, padx=14, pady=(12, 2))
                ctk.CTkLabel(
                    step, text=body, font=("Segoe UI", 12),
                    text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT,
                    wraplength=340,
                ).pack(fill=tk.X, padx=14, pady=(0, 12))
            ctk.CTkLabel(
                panel, textvariable=self.queue_hint, font=("Segoe UI", 12),
                text_color=_theme_color("#C9D3FF"), anchor="w", wraplength=365,
            ).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 14))
            ctk.CTkButton(
                panel, text=action_text, command=action, height=40,
                corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
                text_color=_COLORS["text"], font=("Segoe UI", 13, "bold"),
            ).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
            return panel

        self._file_context_panel = desktop_context(
            "Da importação ao resultado",
            "O arquivo original continua no local escolhido.",
            (
                ("Escolha o arquivo", "Aceita áudio ou vídeo já salvo no computador."),
                ("Acompanhe as etapas", "Transcrição e resumo entram na fila de Processos."),
                ("Revise na Biblioteca", "Abra, organize e exporte os resultados quando terminarem."),
            ),
            "Ver Processos", self._show_processing_page, 730,
        )
        self._youtube_context_panel = desktop_context(
            "Como funciona",
            "Use o endereço de um vídeo que você pode processar.",
            (
                ("Informe o link", "Cole a URL do vídeo no campo ao lado."),
                ("Escolha o resultado", "A transcrição pode incluir um resumo."),
                ("Acompanhe a fila", "O áudio e os documentos ficam disponíveis na Biblioteca."),
            ),
            "Ver Processos", self._show_processing_page, 610,
        )
        self._settings_context_panel = desktop_context(
            "Configuração do app",
            "Estas escolhas serão usadas nos próximos processamentos.",
            (
                ("Verifique a instalação", "Confira áudio, modelo local e serviços conectados."),
                ("Ajuste o processamento", "Escolha modelo, idioma, resumos e falantes."),
                ("Teste antes de usar", "Os testes ficam em Verificação e Transcrição."),
            ),
            "Ver Biblioteca", self._toggle_library, 650,
        )

        self._build_focus_record(content)
        self._build_focus_library(content)
        self._build_focus_processes(content)
        self._build_focus_file(content)
        self._build_focus_youtube(content)
        self._focus_settings_heading = ctk.CTkFrame(content, fg_color="transparent")
        self._focus_page_heading(
            self._focus_settings_heading, "CONFIGURAÇÃO", "Ajustes",
            "Verifique a instalação e defina como o app trabalha.",
        )

        # Do not put a widget, icon, or overlay in the lower-right corner.
        # The root detects that small corner area directly, so the rounded
        # capsule remains visually uninterrupted.
        # No manual resizing: the three window modes have predictable layouts.

        # Modo compacto: uma etiqueta sempre visível, sem a barra ou os campos
        # do widget completo. Ação e estado continuam acessíveis sem precisar
        # interromper uma reunião para abrir a janela principal.
        self._compact_surface = ctk.CTkFrame(
            self, fg_color=_theme_color("#101827"), corner_radius=0,
            border_width=1, border_color=_theme_color("#34486C"),
        )
        compact_main = ctk.CTkFrame(self._compact_surface, fg_color="transparent")
        compact_main.pack(fill=tk.BOTH, expand=True, padx=12, pady=9)
        self._compact_main = compact_main
        self._compact_indicator = ctk.CTkLabel(
            compact_main, text="", width=10, height=10, corner_radius=5,
            fg_color=_theme_color("#55D6A0"),
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
            compact_main, width=86, height=28, bg=_theme_color("#101827"), highlightthickness=0, bd=0,
        )
        self._compact_meter.pack(side=tk.LEFT, padx=(10, 12))
        self._compact_meter.bind("<Configure>", lambda _: self._redraw_eq())
        self.compact_start_button = ctk.CTkButton(
            compact_main, text="Iniciar", command=self._start_recording,
            width=66, height=32, corner_radius=9, fg_color=_COLORS["accent"],
            hover_color=_COLORS["accent_hover"], text_color=_COLORS["accent_text"],
            font=("Segoe UI", 9, "bold"),
        )
        self.compact_start_button.pack(side=tk.LEFT, padx=(0, 6))
        self.compact_stop_button = ctk.CTkButton(
            compact_main, text="Parar", command=self._stop_recording,
            width=60, height=32, corner_radius=9, fg_color=_theme_color("#3C2A3B"),
            hover_color=_theme_color("#55384E"), text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.compact_stop_button.pack(side=tk.LEFT, padx=(0, 6))
        self.compact_open_button = ctk.CTkButton(
            compact_main, text="Abrir", command=self._restore_full_widget,
            width=52, height=32, corner_radius=9, fg_color=_theme_color("#263550"),
            hover_color=_theme_color("#34476B"), text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
        )
        self.compact_open_button.pack(side=tk.LEFT, padx=(0, 6))
        self.compact_hide_button = ctk.CTkButton(
            compact_main, text="Ocultar", command=self._hide_to_tray,
            width=58, height=32, corner_radius=9, fg_color="transparent",
            hover_color=_theme_color("#22324F"), border_width=1, border_color=_theme_color("#2A3A58"),
            text_color=_COLORS["brand_muted"], font=("Segoe UI", 9, "bold"),
        )
        self.compact_hide_button.pack(side=tk.LEFT)
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
                (self._inline_buttons, {"fill": tk.X, "padx": 20, "pady": (4, 16)}),
                (self._record_recent_panel, {"fill": tk.X, "padx": 20, "pady": (0, 8)}),
                (self._buttons, {"side": tk.BOTTOM, "fill": tk.X, "padx": 20, "pady": (0, 10)}),
            ],
            "file": [
                (self._file_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
                (self._file_context_panel, {}),
            ],
            "youtube": [
                (self._youtube_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
                (self._youtube_context_panel, {}),
            ],
            "library": [
                (self._library_panel, {"fill": tk.BOTH, "expand": True, "padx": 20, "pady": (12, 10)}),
            ],
            "processing": [
                (self._processing_panel, {"fill": tk.BOTH, "expand": True, "padx": 20, "pady": (12, 10)}),
            ],
            "settings": [
                (self._settings_panel, {"fill": tk.X, "padx": 20, "pady": (12, 10)}),
                (self._settings_context_panel, {}),
            ],
        }
        self._current_page = "record"
        self.device_info_text.trace_add("write", self._on_device_info_changed)
        self._sync_recording_result_fields()
        self._show_page("record")
        self.after_idle(self._refresh_recording_recent)

        self._widget_hidden: tuple[tk.Misc, ...] = ()

    def _focus_page_heading(
        self, parent: tk.Misc, kicker: str, title: str | tk.StringVar, description: str,
    ) -> ctk.CTkFrame:
        heading = ctk.CTkFrame(parent, fg_color="transparent")
        heading.pack(fill=tk.X, pady=(0, 17))
        copy = ctk.CTkFrame(heading, fg_color="transparent")
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(
            copy, text=kicker, font=("Segoe UI", 10, "bold"),
            text_color=_theme_color("#B8ACFF"), anchor="w",
        ).pack(fill=tk.X)
        title_option = {"textvariable": title} if isinstance(title, tk.StringVar) else {"text": title}
        ctk.CTkLabel(
            copy, **title_option, font=("Segoe UI", 22, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))
        ctk.CTkLabel(
            copy, text=description, font=("Segoe UI", 11),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, pady=(1, 0))
        return heading

    def _build_focus_record(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        self._focus_record_panel = panel
        heading = self._focus_page_heading(
            panel, "CAPTURA", "Gravar",
            "Configure a gravação e comece quando estiver pronto.",
        )
        status = ctk.CTkFrame(
            heading, fg_color=_theme_color("#17342F"), corner_radius=8,
            border_width=1, border_color=_theme_color("#356450"),
        )
        status.pack(side=tk.RIGHT, padx=(8, 0), pady=(7, 0))
        self._focus_status_indicator = ctk.CTkLabel(
            status, text="", width=8, height=8, corner_radius=4,
            fg_color=_theme_color("#55D6A0"),
        )
        self._focus_status_indicator.pack(side=tk.LEFT, padx=(11, 7), pady=11)
        self._focus_status = tk.StringVar(value="Pronto")
        ctk.CTkLabel(
            status, textvariable=self._focus_status, font=("Segoe UI", 11, "bold"),
            text_color=_theme_color("#DDF7EB"),
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            status, textvariable=self.elapsed, font=("Cascadia Mono", 11),
            text_color=_COLORS["text"],
        ).pack(side=tk.LEFT, padx=(12, 11))
        self.status.trace_add("write", self._sync_focus_record_status)
        self._sync_focus_record_status()

        def section(number: str, title: str, description: str) -> ctk.CTkFrame:
            block = ctk.CTkFrame(
                panel, fg_color=_theme_color("#17243A"), corner_radius=10,
                border_width=1, border_color=_theme_color("#2D3E5B"),
            )
            block.pack(fill=tk.X, pady=(0, 11))
            title_row = ctk.CTkFrame(block, fg_color="transparent")
            title_row.pack(fill=tk.X, padx=17, pady=(15, 10))
            ctk.CTkLabel(
                title_row, text=number, width=26, height=26,
                fg_color=_theme_color("#342E69"), corner_radius=7,
                font=("Segoe UI", 12, "bold"), text_color=_theme_color("#DDD6FF"),
            ).pack(side=tk.LEFT, padx=(0, 10))
            text = ctk.CTkFrame(title_row, fg_color="transparent")
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(
                text, text=title, font=("Segoe UI", 14, "bold"),
                text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkLabel(
                text, text=description, font=("Segoe UI", 11),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, pady=(2, 0))
            return block

        source = section("1", "O que gravar", "Escolha de onde vem o áudio.")
        choices = ctk.CTkFrame(source, fg_color="transparent")
        choices.pack(fill=tk.X, padx=17, pady=(0, 16))
        self._focus_source_cards: list[tuple[ctk.CTkFrame, str]] = []
        self._focus_source_buttons: list[ctk.CTkRadioButton] = []
        for index, (label, value, detail) in enumerate((
            ("Microfone + sistema", "both", "Sua voz e o computador"),
            ("Microfone", "microphone", "Apenas sua voz"),
            ("Sistema", "system", "Som do computador"),
        )):
            choices.grid_columnconfigure(index, weight=1, uniform="source")
            card = ctk.CTkFrame(
                choices, fg_color=_theme_color("#101B2E"), corner_radius=8,
                border_width=1, border_color=_theme_color("#3B4D69"),
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 4, 0))
            radio = ctk.CTkRadioButton(
                card, text=label, variable=self.mode, value=value,
                font=("Segoe UI", 11, "bold"), text_color=_COLORS["text"],
                radiobutton_width=16, radiobutton_height=16,
                fg_color=_COLORS["accent"], border_color=_theme_color("#687A9A"),
            )
            radio.pack(fill=tk.X, padx=10, pady=(10, 2))
            ctk.CTkLabel(
                card, text=detail, font=("Segoe UI", 10),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, padx=34, pady=(0, 9))
            self._focus_source_cards.append((card, value))
            self._focus_source_buttons.append(radio)
        self.mode.trace_add("write", self._sync_focus_source_cards)
        self._sync_focus_source_cards()

        result = section("2", "Depois de parar", "O áudio sempre é salvo antes do processamento.")
        ctk.CTkLabel(
            result, text="Resultado", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17)
        self._focus_record_result_selector = ctk.CTkComboBox(
            result, variable=self.recording_output_choice,
            values=[label for label, _code in _RECORDING_OUTPUT_OPTIONS],
            command=self._on_recording_output_choice, state="readonly", height=36,
            fg_color=_theme_color("#101B2E"), border_color=_theme_color("#3B4D69"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], dropdown_fg_color=_theme_color("#162136"),
        )
        self._focus_record_result_selector.pack(fill=tk.X, padx=17, pady=(4, 6))
        self._focus_record_hint = tk.StringVar(value="")
        ctk.CTkLabel(
            result, textvariable=self._focus_record_hint, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17, pady=(0, 13))
        self._focus_summary_preferences = ctk.CTkFrame(result, fg_color="transparent")
        ctk.CTkLabel(
            self._focus_summary_preferences, text="Formato do resumo",
            font=("Segoe UI", 10, "bold"), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17)
        self._focus_profile_selector = ctk.CTkComboBox(
            self._focus_summary_preferences, variable=self.processing_profile,
            values=self._summary_profile_options(), state="readonly", height=34,
            fg_color=_theme_color("#101B2E"), border_color=_theme_color("#3B4D69"),
            button_color=_theme_color("#263550"), text_color=_COLORS["text"],
        )
        self._focus_profile_selector.pack(fill=tk.X, padx=17, pady=(4, 8))
        ctk.CTkLabel(
            self._focus_summary_preferences, text="Instruções opcionais",
            font=("Segoe UI", 10, "bold"), text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17)
        self._focus_meeting_editor = ctk.CTkTextbox(
            self._focus_summary_preferences, height=55, fg_color=_theme_color("#101B2E"),
            border_width=1, border_color=_theme_color("#3B4D69"), text_color=_COLORS["text"],
            font=("Segoe UI", 11), wrap="word",
        )
        self._focus_meeting_editor.pack(fill=tk.X, padx=17, pady=(4, 13))
        self.recording_output_mode.trace_add("write", self._sync_focus_record_output)
        self._sync_focus_record_output()

        save = section("3", "Onde salvar", "Cada gravação terá uma pasta própria.")
        ctk.CTkLabel(
            save, text="Pasta", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17)
        folder_row = ctk.CTkFrame(save, fg_color="transparent")
        folder_row.pack(fill=tk.X, padx=17, pady=(4, 9))
        self._focus_output_entry = ctk.CTkEntry(
            folder_row, textvariable=self.output_dir, state="readonly", height=35,
            fg_color=_theme_color("#101B2E"), border_color=_theme_color("#3B4D69"),
            text_color=_COLORS["text"],
        )
        self._focus_output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._focus_output_browse = ctk.CTkButton(
            folder_row, text="Alterar pasta", command=self._choose_output_dir,
            width=110, height=35, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
        )
        self._focus_output_browse.pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkLabel(
            save, text="Parar automaticamente", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=17)
        self._focus_stop_choice = tk.StringVar(value="Sem limite")
        self._focus_stop_selector = ctk.CTkComboBox(
            save, variable=self._focus_stop_choice,
            values=["Sem limite", "Após 30 minutos", "Após 1 hora", "Após 2 horas"],
            command=self._set_focus_stop_choice, state="readonly", width=270, height=35,
            fg_color=_theme_color("#101B2E"), border_color=_theme_color("#3B4D69"),
            button_color=_theme_color("#263550"), text_color=_COLORS["text"],
        )
        self._focus_stop_selector.pack(anchor=tk.W, padx=17, pady=(4, 16))

        action = ctk.CTkFrame(panel, fg_color="transparent")
        action.pack(fill=tk.X, pady=(1, 0))
        self._focus_start_button = ctk.CTkButton(
            action, text="Iniciar gravação", command=self._start_recording,
            width=176, height=39, corner_radius=7,
            text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            font=("Segoe UI", 11, "bold"),
        )
        self._focus_start_button.pack(side=tk.LEFT)
        self._focus_stop_button = ctk.CTkButton(
            action, text="Parar", command=self._stop_recording,
            width=90, height=39, corner_radius=7, state=tk.DISABLED,
            fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
        )
        ctk.CTkLabel(
            action, text="Você pode parar a qualquer momento.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"],
        ).pack(side=tk.LEFT, padx=(12, 0))

    def _sync_focus_record_status(self, *_: object) -> None:
        raw = self.status.get().casefold()
        if "grava" in raw or raw == "recording":
            status = "Gravando" if raw == "recording" else "Pronto"
        elif "erro" in raw or "error" in raw or "falha" in raw:
            status = "Atenção"
        else:
            status = "Pronto"
        self._focus_status.set(status)
        self._focus_status_indicator.configure(
            fg_color=_theme_color("#F4A7A8") if status == "Atenção" else _theme_color("#55D6A0"),
        )

    def _sync_focus_source_cards(self, *_: object) -> None:
        for card, value in self._focus_source_cards:
            selected = self.mode.get() == value
            card.configure(
                fg_color=_theme_color("#262953") if selected else _theme_color("#101B2E"),
                border_color=_theme_color("#8F7DF0") if selected else _theme_color("#3B4D69"),
            )

    def _sync_focus_record_output(self, *_: object) -> None:
        mode = self.recording_output_mode.get()
        self._focus_record_hint.set({
            "audio": "Se salvar só o áudio, você poderá transcrevê-lo depois pela Biblioteca.",
            "transcription": "A transcrição começa automaticamente depois de salvar o áudio.",
            "both": "A transcrição e o resumo começam depois de salvar o áudio.",
        }.get(mode, ""))
        if mode == "both":
            if not self._focus_summary_preferences.winfo_manager():
                self._focus_summary_preferences.pack(fill=tk.X)
        else:
            self._focus_summary_preferences.pack_forget()

    def _set_focus_stop_choice(self, choice: str) -> None:
        value, unit = {
            "Sem limite": ("", "minutos"),
            "Após 30 minutos": ("30", "minutos"),
            "Após 1 hora": ("1", "horas"),
            "Após 2 horas": ("2", "horas"),
        }[choice]
        self.recording_limit_value.set(value)
        self.recording_limit_unit.set(unit)

    def _sync_focus_stop_choice(self) -> None:
        value = self.recording_limit_value.get().strip()
        unit = self.recording_limit_unit.get()
        choice = {
            ("", "minutos"): "Sem limite",
            ("30", "minutos"): "Após 30 minutos",
            ("1", "horas"): "Após 1 hora",
            ("2", "horas"): "Após 2 horas",
        }.get((value, unit), f"Após {value} {unit}" if value else "Sem limite")
        self._focus_stop_choice.set(choice)

    def _build_focus_library(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=_theme_color("#0D1525"), corner_radius=0)
        self._focus_library_panel = panel
        self._browser_heading_text = tk.StringVar(value="Biblioteca")
        heading = self._focus_page_heading(
            panel, "SEUS ARQUIVOS", self._browser_heading_text,
            "Veja e organize o conteúdo das suas pastas no computador.",
        )
        ctk.CTkButton(heading, text="Trocar pasta", command=self._choose_library_dir,
                      width=115, height=35, fg_color=_theme_color("#263550")).pack(side=tk.RIGHT, pady=(17, 0))
        self._focus_library_use_recording_button = ctk.CTkButton(
            heading, text="Pasta de Gravar", command=self._use_recording_library_dir,
            width=130, height=35, fg_color=_theme_color("#263550"),
            state=tk.NORMAL if self._library_directory_manual else tk.DISABLED,
        )
        self._focus_library_use_recording_button.pack(side=tk.RIGHT, padx=(0, 8), pady=(17, 0))

        location = ctk.CTkFrame(panel, fg_color="transparent")
        location.pack(fill=tk.X, padx=16, pady=(6, 8))
        self._browser_back_button = ctk.CTkButton(
            location, text="←", command=self._browser_back, width=38,
            height=38, fg_color=_theme_color("#263550"),
        )
        self._browser_back_button.pack(side=tk.LEFT, padx=(0, 5))
        self._browser_up_button = ctk.CTkButton(
            location, text="↑", command=self._browser_up, width=38,
            height=38, fg_color=_theme_color("#263550"),
        )
        self._browser_up_button.pack(side=tk.LEFT, padx=(0, 7))
        self._browser_breadcrumb = ctk.CTkFrame(location, fg_color=_theme_color("#111C30"), corner_radius=7, height=38)
        self._browser_search = tk.StringVar(value="")
        search_box = ctk.CTkFrame(location, fg_color=_theme_color("#111C30"), corner_radius=7,
                                  border_width=1, border_color=_theme_color("#33445F"))
        search_box.pack(side=tk.RIGHT)
        search_label = ctk.CTkLabel(
            search_box, text="⌕  Buscar nesta pasta", font=("Segoe UI", 11),
            text_color=_theme_color("#9FB0CC"),
        )
        search_label.pack(side=tk.LEFT, padx=(10, 5))
        search_entry = ctk.CTkEntry(search_box, textvariable=self._browser_search,
                     width=105, height=32,
                     fg_color=_theme_color("#0B1528"), border_width=1, border_color=_theme_color("#4B5E7D"),
                     text_color=_COLORS["text"])
        self._browser_search_entry = search_entry
        search_entry.pack(side=tk.LEFT, padx=(0, 3), pady=3)
        search_label.bind("<Button-1>", lambda _event: search_entry.focus_set())
        search_box.bind("<Button-1>", lambda _event: search_entry.focus_set())
        self._browser_breadcrumb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self._browser_search.trace_add("write", lambda *_: self._render_focus_browser())

        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.pack(fill=tk.X, padx=16, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Nova pasta", command=self._browser_new_folder,
                      width=145, height=34, fg_color=_theme_color("#263550")).pack(side=tk.LEFT)
        self._browser_move_button = ctk.CTkButton(
            toolbar, text="Mover pasta", command=self._browser_move_folder,
            width=130, height=34, fg_color=_theme_color("#263550"))
        self._browser_move_button.pack(side=tk.LEFT, padx=(7, 0))
        self._browser_rename_button = ctk.CTkButton(
            toolbar, text="Renomear", command=self._browser_rename_folder,
            width=112, height=34, fg_color=_theme_color("#263550"))
        self._browser_rename_button.pack(side=tk.LEFT, padx=(7, 0))
        self._browser_sort = tk.StringVar(value="Nome A–Z")
        ctk.CTkOptionMenu(toolbar, variable=self._browser_sort,
                          values=["Nome A–Z", "Nome Z–A", "Mais recentes", "Mais antigos"],
                          command=lambda _choice: self._render_focus_browser(), width=150,
                          height=34, fg_color=_theme_color("#263550"), button_color=_theme_color("#33445F")).pack(side=tk.RIGHT)

        browser_area = ctk.CTkFrame(panel, fg_color="transparent")
        browser_area.pack(fill=tk.BOTH, expand=True, padx=16)
        self._browser_area = browser_area
        table_holder = ctk.CTkFrame(browser_area, fg_color=_theme_color("#0D1525"))
        self._browser_table_holder = table_holder
        table_holder.pack(fill=tk.BOTH, expand=True)
        table_heading = ctk.CTkFrame(table_holder, fg_color="transparent", height=34)
        table_heading.pack(fill=tk.X)
        table_heading.pack_propagate(False)
        self._browser_heading_labels = []
        for text in ("Nome", "Tipo", "Conteúdo", "Modificado"):
            label = ctk.CTkLabel(table_heading, text=text, font=("Segoe UI", 10),
                                 text_color=_theme_color("#9FB0CC"), anchor="w")
            self._browser_heading_labels.append(label)
        table_heading.bind("<Configure>", self._layout_browser_heading, add="+")
        canvas_holder = ctk.CTkFrame(table_holder, fg_color=_theme_color("#0D1525"))
        canvas_holder.pack(fill=tk.BOTH, expand=True)
        self._browser_canvas = tk.Canvas(
            canvas_holder, bg=_theme_color("#0D1525"), height=315,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self._browser_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ctk.CTkScrollbar(
            canvas_holder, orientation="vertical", command=self._browser_canvas_scrollbar,
            width=9, fg_color=_theme_color("#0D1525"), button_color=_theme_color("#34445F"),
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._browser_canvas.configure(yscrollcommand=scrollbar.set)
        self._browser_canvas.bind("<Configure>", lambda _event: self._draw_browser_rows(), add="+")
        self._browser_canvas.bind("<Button-1>", self._browser_canvas_select)
        self._browser_canvas.bind("<Double-1>", self._browser_canvas_open)
        self._browser_canvas.bind("<MouseWheel>", self._browser_canvas_scroll)
        self._browser_canvas.bind("<Return>", self._browser_open)
        self._browser_count = tk.StringVar(value="")
        ctk.CTkLabel(table_holder, textvariable=self._browser_count, font=("Segoe UI", 10),
                     text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(7, 3))
        self._browser_full_path = tk.StringVar(value="")
        preview = ctk.CTkFrame(browser_area, fg_color=_theme_color("#17213A"), corner_radius=9, height=108)
        self._browser_preview = preview
        preview.pack(fill=tk.X, pady=(0, 12))
        preview.pack_propagate(False)
        self._browser_preview_title = tk.StringVar(value="Selecione um arquivo ou pasta")
        self._browser_preview_body = tk.StringVar(value="Abra uma pasta com dois cliques para ver seu conteúdo.")
        ctk.CTkLabel(preview, textvariable=self._browser_preview_title, font=("Segoe UI", 13, "bold"),
                     text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=14, pady=(10, 2))
        self._browser_preview_body_label = ctk.CTkLabel(
            preview, textvariable=self._browser_preview_body, font=("Segoe UI", 10),
            text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT,
            wraplength=600,
        )
        self._browser_preview_body_label.pack(fill=tk.X, padx=14)
        self._browser_preview_details = tk.StringVar(value="")
        self._browser_preview_details_label = ctk.CTkLabel(
            preview, textvariable=self._browser_preview_details,
            font=("Segoe UI", 11), text_color=_theme_color("#BFCDE3"),
            anchor="nw", justify=tk.LEFT, wraplength=390,
        )
        self._browser_audio_player = ctk.CTkFrame(preview, fg_color="transparent")
        self._browser_play_button = ctk.CTkButton(
            self._browser_audio_player, text=_PLAYER_PLAY_ICON,
            command=self._browser_toggle_audio, width=36, height=34,
            font=("Segoe UI Symbol", 18), text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"],
        )
        self._browser_play_button.pack(side=tk.LEFT, padx=(14, 8))
        self._browser_audio_time = tk.StringVar(value="00:00 / 00:00")
        ctk.CTkLabel(self._browser_audio_player, textvariable=self._browser_audio_time,
                     width=90, font=("Segoe UI", 10),
                     text_color=_COLORS["muted"]).pack(side=tk.RIGHT, padx=(8, 14))
        self._browser_audio_slider = ctk.CTkSlider(
            self._browser_audio_player, from_=0, to=1,
            command=self._browser_seek_audio, fg_color=_theme_color("#33445F"),
            progress_color=_COLORS["accent"])
        self._browser_slider_updating = True
        self._browser_audio_slider.set(0)
        self._browser_audio_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._browser_audio_path: Path | None = None
        self._browser_audio_duration = 0
        self._browser_audio_playing = False
        self._browser_audio_tick: str | None = None
        self._browser_seek_after: str | None = None
        self._browser_slider_updating = False
        preview_actions = ctk.CTkFrame(preview, fg_color="transparent")
        preview_actions.pack(fill=tk.X, padx=14, pady=(2, 8))
        self._browser_open_button = ctk.CTkButton(
            preview_actions, text="Abrir", command=self._browser_open, width=125, height=30,
            text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"])
        self._browser_open_button.pack(side=tk.RIGHT)
        self._browser_process_button = ctk.CTkButton(
            preview_actions, text="Processar áudio", command=self._browser_process_audio,
            width=140, height=30, fg_color=_theme_color("#263550"))
        self._browser_favorite_button = ctk.CTkButton(
            preview_actions, text="☆ Favoritar", command=self._browser_toggle_favorite,
            width=110, height=30, fg_color=_theme_color("#263550"))
        self._browser_metadata_button = ctk.CTkButton(
            preview_actions, text="Título e etiquetas", command=self._browser_edit_metadata,
            width=145, height=30, fg_color=_theme_color("#263550"))
        self._browser_docx_button = ctk.CTkButton(
            preview_actions, text="DOCX", command=lambda: self._browser_export_document("docx"),
            width=62, height=30, fg_color=_theme_color("#263550"))
        self._browser_pdf_button = ctk.CTkButton(
            preview_actions, text="PDF", command=lambda: self._browser_export_document("pdf"),
            width=55, height=30, fg_color=_theme_color("#263550"))
        ctk.CTkLabel(panel, textvariable=self._browser_full_path, font=("Segoe UI", 9),
                     text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, padx=16, pady=(0, 7))
        self._browser_entries: list[BrowserEntry] = []
        self._browser_history: list[Path] = []
        self._browser_selected: BrowserEntry | None = None

    def _build_focus_processes(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=_theme_color("#0D1525"), corner_radius=0)
        self._focus_process_panel = panel
        heading = self._focus_page_heading(
            panel, "TAREFAS", "Processos",
            "Acompanhe, retome ou remova processos sem afetar os arquivos salvos.",
        )
        ctk.CTkButton(heading, text="Atualizar", command=self._refresh_focus_processes,
                      width=95, height=35, fg_color=_theme_color("#263550")).pack(side=tk.RIGHT, pady=(17, 0))
        filters = ctk.CTkFrame(panel, fg_color="transparent")
        filters.pack(fill=tk.X, padx=16, pady=(0, 9))
        self._focus_process_filter = tk.StringVar(value="Todos")
        self._focus_process_filter_buttons: dict[str, ctk.CTkButton] = {}
        for label in ("Todos", "Em andamento", "Aguardando", "Exigem atenção", "Concluídos"):
            button = ctk.CTkButton(
                filters, text=label,
                command=lambda selected=label: self._set_focus_process_filter(selected),
                width=119, height=32, fg_color=_theme_color("#263550"), corner_radius=7,
                font=("Segoe UI", 10),
            )
            button.pack(side=tk.LEFT, padx=(0, 5))
            self._focus_process_filter_buttons[label] = button
        self._focus_process_list = ctk.CTkScrollableFrame(
            panel, fg_color="transparent", height=225,
            scrollbar_button_color=_theme_color("#34445F"),
        )
        self._focus_process_list.pack(fill=tk.X, padx=16)
        self._focus_selected_job_id: str | None = None
        detail = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        detail.pack(fill=tk.X, padx=16, pady=(12, 5))
        self._focus_process_title = tk.StringVar(value="Selecione um processo")
        self._focus_process_detail = tk.StringVar(value="Os detalhes aparecerão aqui.")
        self._focus_process_state = tk.StringVar(value="")
        self._focus_process_stage = tk.StringVar(value="—")
        self._focus_process_audio = tk.StringVar(value="—")
        self._focus_process_when = tk.StringVar(value="—")
        self._focus_process_error_summary = tk.StringVar(value="")
        ctk.CTkLabel(detail, text="PROCESSO SELECIONADO", font=("Segoe UI", 10, "bold"),
                     text_color=_theme_color("#B8ACFF"), anchor="w").pack(fill=tk.X, padx=14, pady=(12, 0))
        title_line = ctk.CTkFrame(detail, fg_color="transparent")
        title_line.pack(fill=tk.X, padx=14, pady=(3, 3))
        ctk.CTkLabel(title_line, textvariable=self._focus_process_title,
                     font=("Segoe UI", 15, "bold"),
                     text_color=_COLORS["text"], anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(title_line, textvariable=self._focus_process_state,
                     font=("Segoe UI", 10, "bold"),
                     text_color=_theme_color("#B8ACFF")).pack(side=tk.RIGHT)
        ctk.CTkLabel(detail, textvariable=self._focus_process_detail, font=("Segoe UI", 11),
                     text_color=_COLORS["muted"], anchor="w", wraplength=630,
                     justify=tk.LEFT).pack(fill=tk.X, padx=14, pady=(0, 9))
        facts = ctk.CTkFrame(detail, fg_color="transparent")
        facts.pack(fill=tk.X, padx=14, pady=(0, 10))
        for index, (label, variable) in enumerate((
            ("ETAPA", self._focus_process_stage),
            ("ÁUDIO", self._focus_process_audio),
            ("QUANDO", self._focus_process_when),
        )):
            facts.grid_columnconfigure(index, weight=1)
            fact = ctk.CTkFrame(facts, fg_color=_theme_color("#111B2D"), corner_radius=7)
            fact.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0))
            ctk.CTkLabel(fact, text=label, font=("Segoe UI", 9, "bold"),
                         text_color=_theme_color("#9FB0CC"), anchor="w").pack(fill=tk.X, padx=10, pady=(7, 0))
            ctk.CTkLabel(fact, textvariable=variable, font=("Segoe UI", 10, "bold"),
                         text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=10, pady=(1, 7))
        self._focus_process_error_panel = ctk.CTkFrame(
            detail, fg_color=_theme_color("#291F31"), corner_radius=7,
            border_width=1, border_color=_theme_color("#72505A"),
        )
        ctk.CTkLabel(self._focus_process_error_panel, text="O que aconteceu",
                     font=("Segoe UI", 10, "bold"), text_color=_theme_color("#FFB7AD"),
                     anchor="w").pack(fill=tk.X, padx=11, pady=(8, 2))
        ctk.CTkLabel(self._focus_process_error_panel,
                     textvariable=self._focus_process_error_summary,
                     font=("Segoe UI", 10), text_color=_theme_color("#E5CFD2"),
                     anchor="w", justify=tk.LEFT, wraplength=610,
                     ).pack(fill=tk.X, padx=11, pady=(0, 8))
        actions = ctk.CTkFrame(detail, fg_color="transparent")
        actions.pack(fill=tk.X, padx=14, pady=(0, 12))
        self._focus_process_retry = ctk.CTkButton(actions, text="Tentar novamente",
                                                   command=self._focus_retry_job, width=155,
                                                   height=34, text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"])
        self._focus_process_retry.pack(side=tk.LEFT)
        self._focus_process_open = ctk.CTkButton(actions, text="Abrir pasta",
                                                  command=self._focus_open_job_folder, width=125,
                                                  height=34, fg_color=_theme_color("#263550"))
        self._focus_process_open.pack(side=tk.LEFT, padx=(8, 0))
        self._focus_process_error = ctk.CTkButton(actions, text="Ver erro completo",
                                                   command=self._focus_show_job_error, width=145,
                                                   height=34, fg_color=_theme_color("#3A2637"))
        self._focus_process_error.pack(side=tk.LEFT, padx=(8, 0))
        self._focus_process_remove = ctk.CTkButton(actions, text="Remover da lista",
                                                    command=self._focus_remove_job, width=145,
                                                    height=34, fg_color=_theme_color("#3A2637"))
        self._focus_process_remove.pack(side=tk.RIGHT)
        ctk.CTkLabel(panel, text="Remover da lista não apaga o áudio nem os documentos salvos.",
                     font=("Segoe UI", 10), text_color=_COLORS["muted"],
                     anchor="w").pack(fill=tk.X, padx=18, pady=(0, 10))

    def _build_focus_file(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        self._focus_file_panel = panel
        self._focus_page_heading(
            panel, "IMPORTAÇÃO", "Arquivo",
            "Processe um áudio ou vídeo que já está no computador.",
        )
        before = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        before.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(before, text="Antes de começar", font=("Segoe UI", 12, "bold"),
                     text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=16, pady=(10, 1))
        ctk.CTkLabel(before, text="O original é preservado. Acompanhe a tarefa em Processos e encontre o resultado na Biblioteca.",
                     font=("Segoe UI", 11), text_color=_COLORS["muted"],
                     anchor="w", wraplength=800, justify=tk.LEFT).pack(fill=tk.X, padx=16, pady=(0, 10))
        first = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        first.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(first, text="1  Escolher arquivo", font=("Segoe UI", 15, "bold"),
                     text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=16, pady=(14, 3))
        ctk.CTkLabel(first, text="Selecione o áudio ou vídeo que será processado.",
                     font=("Segoe UI", 11), text_color=_COLORS["muted"],
                     anchor="w").pack(fill=tk.X, padx=16, pady=(0, 9))
        target = ctk.CTkFrame(first, fg_color=_theme_color("#101B2E"), corner_radius=8,
                              border_width=1, border_color=_theme_color("#3B4D69"))
        target.pack(fill=tk.X, padx=16, pady=(0, 14))
        self._focus_file_label = tk.StringVar(value="Nenhum arquivo escolhido")
        ctk.CTkLabel(target, textvariable=self._focus_file_label,
                     font=("Segoe UI", 12, "bold"), text_color=_COLORS["text"],
                     anchor="w").pack(fill=tk.X, padx=14, pady=(12, 3))
        ctk.CTkLabel(target, text="MP3, WAV, M4A, MP4 e outros formatos aceitos",
                     font=("Segoe UI", 10), text_color=_COLORS["muted"],
                     anchor="w").pack(fill=tk.X, padx=14)
        ctk.CTkButton(target, text="Escolher arquivo", command=self._focus_choose_file,
                      width=140, height=34, fg_color=_theme_color("#263550")).pack(anchor=tk.W, padx=14, pady=(10, 13))
        second = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        second.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(second, text="2  Configurar processamento", font=("Segoe UI", 15, "bold"),
                     text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=16, pady=(14, 3))
        ctk.CTkLabel(second, text="Estas opções valem somente para este arquivo.",
                     font=("Segoe UI", 11), text_color=_COLORS["muted"],
                     anchor="w").pack(fill=tk.X, padx=16, pady=(0, 9))
        choices = (
            ("Resultado", self.file_output_mode, ["Transcrição e resumo", "Apenas transcrição"]),
            ("Idioma", self.file_pipeline_language, _LANG_LABELS),
            ("Modelo local", self.file_pipeline_model, self._available_models),
            ("Resumo com", self.file_summary_provider, self._summary_provider_options()),
            ("Fonte da transcrição", self.file_transcription_source, self._transcription_source_options()),
            ("Formato do resumo", self.file_processing_profile, self._summary_profile_options()),
        )
        advanced = ctk.CTkFrame(second, fg_color="transparent")
        for index in range(0, len(choices), 2):
            host = second if index < 4 else advanced
            row = ctk.CTkFrame(host, fg_color="transparent")
            row.pack(fill=tk.X, padx=16, pady=(0, 10))
            for label, variable, values in choices[index:index + 2]:
                field = ctk.CTkFrame(row, fg_color="transparent")
                field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
                ctk.CTkLabel(field, text=label, font=("Segoe UI", 10, "bold"),
                             text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
                selector = ctk.CTkComboBox(field, variable=variable, values=values,
                                            state="readonly", height=36, fg_color=_theme_color("#0D1525"),
                                            border_color=_theme_color("#33445F"), button_color=_theme_color("#263550"))
                selector.pack(fill=tk.X)
                if variable is self.file_summary_provider:
                    self._focus_file_provider_selector = selector
                if variable is self.file_transcription_source:
                    self._focus_file_source_selector = selector
        ctk.CTkCheckBox(advanced, text="Separar falantes", variable=self.file_diarize_speakers,
                        fg_color=_COLORS["accent"]).pack(anchor=tk.W, padx=16, pady=(0, 11))
        def toggle_advanced() -> None:
            if advanced.winfo_manager():
                advanced.pack_forget()
            else:
                advanced.pack(fill=tk.X, before=advanced_button)
        advanced_button = ctk.CTkButton(
            second, text="Opções avançadas ▾", command=toggle_advanced,
            width=145, height=29, fg_color="transparent", hover_color=_theme_color("#263550"),
            text_color=_theme_color("#B8ACFF"), anchor="w",
        )
        advanced_button.pack(anchor=tk.W, padx=16, pady=(0, 12))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill=tk.X)
        ctk.CTkButton(actions, text="Processar arquivo", command=self._focus_process_file,
                      width=200, height=40, text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"]).pack(side=tk.LEFT)
        ctk.CTkButton(actions, text="Colar ou abrir transcrição", command=self._focus_show_text_tools,
                      width=210, height=40, fg_color=_theme_color("#263550")).pack(side=tk.LEFT, padx=(9, 0))
        self._focus_file_audio_sections = (first, second, actions)
        self._focus_text_import_panel = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        ctk.CTkLabel(
            self._focus_text_import_panel, text="Transcrição pronta", font=("Segoe UI", 13, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 3))
        ctk.CTkLabel(
            self._focus_text_import_panel,
            text="Cole o texto abaixo ou abra um arquivo .txt/.md para guardar na Biblioteca.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w", wraplength=650,
        ).pack(fill=tk.X, padx=16, pady=(0, 10))
        ctk.CTkLabel(
            self._focus_text_import_panel, text="Título", font=("Segoe UI", 10, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 3))
        ctk.CTkEntry(
            self._focus_text_import_panel, textvariable=self.import_text_title,
            placeholder_text="Título da transcrição", height=35,
            fg_color=_theme_color("#101B2E"), border_color=_theme_color("#3B4D69"),
        ).pack(fill=tk.X, padx=16, pady=(0, 9))
        self._focus_import_text_editor = ctk.CTkTextbox(
            self._focus_text_import_panel, height=135, corner_radius=8,
            fg_color=_theme_color("#101B2E"), border_width=1, border_color=_theme_color("#3B4D69"),
            text_color=_COLORS["text"], font=("Consolas", 10), wrap="word",
        )
        self._focus_import_text_editor.pack(fill=tk.X, padx=16, pady=(0, 10))
        text_actions = ctk.CTkFrame(self._focus_text_import_panel, fg_color="transparent")
        text_actions.pack(fill=tk.X, padx=16, pady=(0, 14))
        ctk.CTkButton(text_actions, text="Abrir .txt/.md", command=self._load_text_import,
                      width=115, height=33, fg_color=_theme_color("#263550")).pack(side=tk.LEFT)
        ctk.CTkButton(text_actions, text="Voltar para arquivo", command=self._focus_show_text_tools,
                      width=135, height=33, fg_color=_theme_color("#263550")).pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkButton(text_actions, text="Salvar e gerar resumo",
                      command=self._save_imported_text_and_regenerate,
                      width=170, height=33, text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"]).pack(side=tk.RIGHT)
        ctk.CTkButton(text_actions, text="Salvar", command=self._save_imported_text,
                      width=75, height=33, fg_color=_theme_color("#244462")).pack(side=tk.RIGHT, padx=(0, 8))
        self._focus_text_tools_visible = False

    def _focus_choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Escolher áudio ou vídeo",
            filetypes=[("Áudio e vídeo", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma *.mp4 *.m4v *.mov *.mkv *.webm *.avi"),
                       ("Todos os arquivos", "*.*")],
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if chosen:
            self._focus_file_path = Path(chosen)
            self._focus_file_label.set(self._focus_file_path.name)

    def _focus_process_file(self) -> None:
        path = self._focus_file_path
        if path is None or not path.is_file():
            messagebox.showinfo("Escolha um arquivo", "Selecione um áudio ou vídeo para processar.", parent=self)
            return
        if self._queue_pipeline(
            path, _LANG_CODES.get(self.file_pipeline_language.get(), "pt"),
            self.file_pipeline_model.get(),
            self._summary_provider_code_for_label(self.file_summary_provider.get()),
            self._summary_template_code_for_choice(self.file_processing_profile.get(), "Reunião"),
            output_mode="transcription" if self.file_output_mode.get() == "Apenas transcrição" else "both",
            output_dir=Path(self.output_dir.get() or default_output_dir()),
            transcription_provider=self._transcription_provider_code_for_label(self.file_transcription_source.get()),
            separate_speakers=self.file_diarize_speakers.get(), preserve_source=True,
        ):
            self._focus_file_path = None
            self._focus_file_label.set("Nenhum arquivo escolhido")
            self._show_page("processing")

    def _focus_show_text_tools(self) -> None:
        self._focus_text_tools_visible = not self._focus_text_tools_visible
        if self._focus_text_tools_visible:
            for section in self._focus_file_audio_sections:
                section.pack_forget()
            self._focus_text_import_panel.pack(fill=tk.X, pady=(12, 0))
        else:
            self._focus_text_import_panel.pack_forget()
            first, second, actions = self._focus_file_audio_sections
            first.pack(fill=tk.X, pady=(0, 12))
            second.pack(fill=tk.X, pady=(0, 12))
            actions.pack(fill=tk.X)

    def _build_focus_youtube(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        self._focus_youtube_panel = panel
        self._focus_page_heading(
            panel, "IMPORTAÇÃO", "YouTube",
            "Cole um link autorizado e escolha o resultado.",
        )
        before = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        before.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(before, text="Antes de começar", font=("Segoe UI", 12, "bold"),
                     anchor="w").pack(fill=tk.X, padx=16, pady=(11, 2))
        ctk.CTkLabel(before, text="Use apenas vídeos próprios ou autorizados. O áudio e os documentos ficarão disponíveis na Biblioteca.",
                     text_color=_COLORS["muted"], font=("Segoe UI", 11), anchor="w",
                     wraplength=800, justify=tk.LEFT).pack(fill=tk.X, padx=16, pady=(0, 10))
        first = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        first.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(first, text="1  Link do vídeo", font=("Segoe UI", 15, "bold"),
                     anchor="w").pack(fill=tk.X, padx=16, pady=(14, 7))
        ctk.CTkEntry(first, textvariable=self.youtube_url,
                     placeholder_text="https://www.youtube.com/watch?v=...", height=40,
                     fg_color=_theme_color("#0D1525"), border_color=_theme_color("#33445F")).pack(fill=tk.X, padx=16, pady=(0, 14))
        second = ctk.CTkFrame(panel, fg_color=_theme_color("#17213A"), corner_radius=9)
        second.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(second, text="2  Configurar resultado", font=("Segoe UI", 15, "bold"),
                     anchor="w").pack(fill=tk.X, padx=16, pady=(14, 8))
        row = ctk.CTkFrame(second, fg_color="transparent")
        row.pack(fill=tk.X, padx=16, pady=(0, 16))
        for label, variable, values in (
            ("Resultado", self.youtube_mode, ["Transcrição e resumo", "Só transcrição", "Só resumo"]),
            ("Formato do resumo", self.processing_profile, self._summary_profile_options()),
        ):
            field = ctk.CTkFrame(row, fg_color="transparent")
            field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            ctk.CTkLabel(field, text=label, font=("Segoe UI", 10, "bold"),
                         text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(0, 3))
            selector = ctk.CTkComboBox(field, variable=variable, values=values,
                                        state="readonly", height=36, fg_color=_theme_color("#0D1525"),
                                        border_color=_theme_color("#33445F"), button_color=_theme_color("#263550"))
            selector.pack(fill=tk.X)
            if variable is self.processing_profile:
                self._focus_youtube_profile_selector = selector
        self._focus_youtube_process_button = ctk.CTkButton(
            panel, text="Baixar áudio e processar", command=self._process_youtube,
            width=220, height=40, text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"])
        self._focus_youtube_process_button.pack(anchor=tk.W)
        ctk.CTkLabel(panel, textvariable=self.youtube_hint, font=("Segoe UI", 10),
                     text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X, pady=(8, 0))

    def _summary_provider_options(self) -> list[str]:
        """Return native providers plus individually named saved API providers."""
        self._api_provider_labels = {}
        used_labels = set(_SUMMARY_PROVIDER_LABELS)
        for config in self._api_provider_configs:
            base = f"API · {config.name.strip() or 'Minha API'}"
            label = base
            suffix = 2
            while label in used_labels:
                label = f"{base} ({suffix})"
                suffix += 1
            used_labels.add(label)
            self._api_provider_labels[label] = f"api:{config.id}"
        return [*_SUMMARY_PROVIDER_LABELS, *self._api_provider_labels]

    def _selected_summary_provider_code(self) -> str:
        return self._api_provider_labels.get(
            self.summary_provider.get(),
            _SUMMARY_PROVIDER_CODES.get(self.summary_provider.get(), "codex"),
        )

    def _summary_provider_code_for_label(self, label: str) -> str:
        return self._api_provider_labels.get(label, _SUMMARY_PROVIDER_CODES.get(label, "codex"))

    def _label_for_summary_provider_code(self, provider_code: str) -> str | None:
        """Resolve a persisted provider code to the current visible label."""
        native_label = next(
            (label for label, code in _SUMMARY_PROVIDER_CODES.items() if code == provider_code),
            None,
        )
        if native_label is not None:
            return native_label
        return next(
            (label for label, code in self._api_provider_labels.items() if code == provider_code),
            None,
        )

    def _restore_summary_provider_choice(self, provider_code: str | None = None) -> bool:
        """Restore a saved choice, falling back only when its provider vanished."""
        self._summary_provider_options()
        desired_code = provider_code if provider_code is not None else self._preferred_summary_provider_code
        label = self._label_for_summary_provider_code(desired_code)
        if label is None:
            self.summary_provider.set("Codex")
            return False
        self.summary_provider.set(label)
        return True

    def _transcription_source_options(self) -> list[str]:
        self._summary_provider_options()
        compatible_ids = {
            config.id for config in self._api_provider_configs
            if config.protocol == "openai_compatible"
        }
        return [
            "Whisper local",
            *[
                label for label, code in self._api_provider_labels.items()
                if code.removeprefix("api:") in compatible_ids
            ],
        ]

    def _selected_transcription_provider_code(self) -> str:
        if self.transcription_source.get() == "Whisper local":
            return "local"
        return self._api_provider_labels.get(self.transcription_source.get(), "local")

    def _transcription_provider_code_for_label(self, label: str) -> str:
        if label == "Whisper local":
            return "local"
        return self._api_provider_labels.get(label, "local")

    def _api_provider_for_id(self, provider_id: str) -> object | None:
        return next((config for config in self._api_provider_configs if config.id == provider_id), None)

    def _refresh_api_provider_choices(self) -> None:
        from record_transcript_resume.api_provider import load_configs

        current_code = self._selected_summary_provider_code()
        self._api_provider_configs = load_configs()
        values = self._summary_provider_options()
        if hasattr(self, "provider_selector"):
            self.provider_selector.configure(values=values)
        if hasattr(self, "file_summary_provider_selector"):
            self.file_summary_provider_selector.configure(values=values)
            if hasattr(self, "_focus_file_provider_selector"):
                self._focus_file_provider_selector.configure(values=values)
            if self.file_summary_provider.get() not in values:
                self.file_summary_provider.set(self.summary_provider.get())
        transcription_values = self._transcription_source_options()
        if hasattr(self, "transcription_source_selector"):
            self.transcription_source_selector.configure(values=transcription_values)
        if hasattr(self, "file_transcription_source_selector"):
            self.file_transcription_source_selector.configure(values=transcription_values)
            if hasattr(self, "_focus_file_source_selector"):
                self._focus_file_source_selector.configure(values=transcription_values)
            if self.file_transcription_source.get() not in transcription_values:
                self.file_transcription_source.set("Whisper local")
        desired_code = self._preferred_summary_provider_code or current_code
        self._restore_summary_provider_choice(desired_code)
        if self.transcription_source.get() not in transcription_values:
            self.transcription_source.set("Whisper local")
        if hasattr(self, "api_provider_list"):
            self._render_api_provider_list()

    def _summary_profile_options(self) -> list[str]:
        return [*list(_PROCESSING_PROFILES), *[f"Perfil salvo · {profile.name}" for profile in self._summary_profiles]]

    def _custom_summary_profile_for_label(self, label: str) -> object | None:
        prefix = "Perfil salvo · "
        if not label.startswith(prefix):
            return None
        name = label.removeprefix(prefix)
        return next((profile for profile in self._summary_profiles if profile.name == name), None)

    def _selected_summary_template_code(self) -> str:
        return self._summary_template_code_for_choice(
            self.processing_profile.get(), self.summary_template.get(),
        )

    def _summary_template_code_for_choice(self, profile_label: str, template_label: str) -> str:
        """Resolve a profile/form choice without mutating the current screen."""
        profile = self._custom_summary_profile_for_label(profile_label)
        if profile is not None:
            return f"custom:{getattr(profile, 'id')}"
        profile_template, _model, _speakers = _PROCESSING_PROFILES.get(profile_label, (None, None, None))
        return _SUMMARY_TEMPLATE_CODES.get(profile_template or template_label, "meeting")

    def _show_selected_profile_prompt(self) -> None:
        """Show the exact summary instruction without making it editable here."""
        self._show_profile_prompt(self._selected_summary_template_code(), self.processing_profile.get())

    def _show_profile_prompt(self, template_code: str, profile_label: str) -> None:
        """Show a selected profile prompt from the normal or retry flow."""
        try:
            preview = prompt_preview(template_code)
        except Exception as exc:
            messagebox.showerror("Prompt indisponível", str(exc))
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Prompt do perfil")
        self._fit_dialog(dialog, 660, 560, 480, 400)
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text=f"PROMPT DO PERFIL · {profile_label}", font=("Segoe UI", 12, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(18, 3))
        ctk.CTkLabel(
            dialog,
            text="Somente leitura. As instruções desta reunião são adicionadas a este prompt quando você iniciar o processamento.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w", wraplength=610,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=18, pady=(0, 10))
        editor = ctk.CTkTextbox(
            dialog, corner_radius=10, fg_color=_theme_color("#0D1525"), border_width=1,
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Cascadia Mono", 10),
            wrap="word",
        )
        editor.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))
        editor.insert("1.0", preview)
        editor.configure(state=tk.DISABLED)
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill=tk.X, padx=18, pady=(0, 16))

        def copy_prompt() -> None:
            self.clipboard_clear()
            self.clipboard_append(preview)
            self.update()
            self.status.set("Prompt copiado")

        ctk.CTkButton(
            actions, text="Fechar", command=dialog.destroy, width=82, height=32,
            corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        ctk.CTkButton(
            actions, text="Copiar prompt", command=copy_prompt, width=110, height=32,
            corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _meeting_instructions(self) -> str:
        if not self._maximized and hasattr(self, "_focus_meeting_editor"):
            return self._focus_meeting_editor.get("1.0", "end-1c").strip()
        editor = getattr(self, "meeting_instructions_editor", None)
        return editor.get("1.0", "end-1c").strip() if editor is not None else ""

    def _clear_meeting_instructions(self) -> None:
        self.meeting_instructions_editor.delete("1.0", tk.END)
        if hasattr(self, "_focus_meeting_editor"):
            self._focus_meeting_editor.delete("1.0", tk.END)

    def _refresh_summary_profile_choices(self) -> None:
        from record_transcript_resume.summary_profiles import load_profiles

        self._summary_profiles = load_profiles()
        values = self._summary_profile_options()
        for selector_name in ("profile_selector", "youtube_profile_selector", "file_profile_selector", "_focus_profile_selector"):
            selector = getattr(self, selector_name, None)
            if selector is not None:
                selector.configure(values=values)
        if self.processing_profile.get() not in values:
            self.processing_profile.set("Resumo padrão")
        if hasattr(self, "file_processing_profile") and self.file_processing_profile.get() not in values:
            self.file_processing_profile.set("Resumo padrão")
        if hasattr(self, "summary_profile_list"):
            self._render_summary_profile_list()

    def _render_summary_profile_list(self) -> None:
        for child in self.summary_profile_list.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.summary_profile_list, text="FORMATOS NATIVOS", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(9, 3))
        for label, (template, _model, _speakers) in _PROCESSING_PROFILES.items():
            row = ctk.CTkFrame(self.summary_profile_list, fg_color="transparent")
            row.pack(fill=tk.X, padx=10, pady=(0, 6))
            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(details, text=label, font=("Segoe UI", 10, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X)
            ctk.CTkLabel(
                details, text=f"{template} · prompt padrão", font=("Segoe UI", 9),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkButton(
                row, text="Ver prompt", command=lambda current_label=label, current_template=template: self._show_profile_prompt(
                    _SUMMARY_TEMPLATE_CODES.get(current_template, "meeting"), current_label,
                ), width=76, height=28, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.RIGHT)

        ctk.CTkLabel(
            self.summary_profile_list, text="PERFIS SALVOS", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(8, 3))
        if not self._summary_profiles:
            ctk.CTkLabel(
                self.summary_profile_list, text="Crie um perfil salvo quando quiser reutilizar instruções próprias sobre um formato nativo.",
                font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT, wraplength=445,
            ).pack(fill=tk.X, padx=10, pady=(0, 9))
            return
        for profile in self._summary_profiles:
            row = ctk.CTkFrame(self.summary_profile_list, fg_color="transparent")
            row.pack(fill=tk.X, padx=10, pady=(0, 7))
            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(details, text=profile.name, font=("Segoe UI", 10, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X)
            template_label = _SUMMARY_TEMPLATE_NAMES_BY_CODE.get(profile.base_template, "Prompt próprio")
            speaker_status = "falantes" if profile.separate_speakers else "sem falantes"
            ctk.CTkLabel(details, text=f"{template_label} · {profile.model_size} · {speaker_status}", font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w").pack(fill=tk.X)
            ctk.CTkButton(
                row, text="Editar", command=lambda profile_id=profile.id: self._edit_summary_profile(profile_id),
                width=64, height=28, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.RIGHT)
            ctk.CTkButton(
                row, text="Ver prompt", command=lambda profile_id=profile.id, profile_name=profile.name: self._show_profile_prompt(
                    f"custom:{profile_id}", f"Perfil salvo · {profile_name}",
                ), width=76, height=28, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.RIGHT, padx=(0, 6))

    def _open_new_summary_profile_dialog(self) -> None:
        from record_transcript_resume.summary_profiles import SummaryProfile

        self._open_summary_profile_dialog(SummaryProfile())

    def _edit_summary_profile(self, profile_id: str) -> None:
        profile = next((item for item in self._summary_profiles if item.id == profile_id), None)
        if profile is None:
            messagebox.showerror("Perfil indisponível", "Esse perfil não foi encontrado. Atualize a lista e tente novamente.")
            return
        self._open_summary_profile_dialog(profile)

    def _open_summary_profile_dialog(self, profile: object) -> None:
        """Create or edit a saved profile without expanding the settings page."""
        profile_id = str(getattr(profile, "id", ""))
        profile_name = str(getattr(profile, "name", "Meu perfil"))
        stored_base_template = str(getattr(profile, "base_template", ""))
        base_template = _SUMMARY_TEMPLATE_NAMES_BY_CODE.get(stored_base_template, "Reunião")
        prompt_mode = str(getattr(profile, "prompt_mode", "append"))
        use_base_initially = bool(stored_base_template)
        start_mode_value = tk.StringVar(value="Usar prompt-base" if use_base_initially else "Começar em branco")
        name_value = tk.StringVar(value=profile_name)
        template_value = tk.StringVar(value=base_template)
        model_value = tk.StringVar(value=str(getattr(profile, "model_size", "small")))
        speakers_value = tk.BooleanVar(value=bool(getattr(profile, "separate_speakers", False)))
        initial_instructions = str(getattr(profile, "instructions", ""))
        if use_base_initially and (not profile_id or prompt_mode != "custom"):
            initial_instructions = profile_prompt_seed(stored_base_template or "meeting", initial_instructions)

        dialog = ctk.CTkToplevel(self)
        dialog.title("Editar perfil de resumo" if profile_id else "Novo perfil de resumo")
        self._fit_dialog(dialog, 680, 760, 500, 520)
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()

        shell = ctk.CTkScrollableFrame(dialog, fg_color=_COLORS["surface"], corner_radius=16)
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            shell, text="Editar perfil de resumo" if profile_id else "Criar perfil de resumo",
            font=("Segoe UI", 15, "bold"), text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(18, 2))
        ctk.CTkLabel(
            shell,
            text=(
                "Escolha começar vazio ou carregar um prompt-base nativo para editar. "
                "O que você salvar aqui será o prompt deste perfil."
            ),
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT,
            wraplength=620,
        ).pack(fill=tk.X, padx=18, pady=(0, 14))

        def field_label(text: str) -> None:
            ctk.CTkLabel(
                shell, text=text, font=("Segoe UI", 9, "bold"),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, padx=18, pady=(0, 3))

        field_label("NOME DO PERFIL")
        name_entry = ctk.CTkEntry(
            shell, textvariable=name_value, height=34, corner_radius=9, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        name_entry.pack(fill=tk.X, padx=18, pady=(0, 12))

        field_label("COMO DESEJA COMEÇAR?")
        start_mode_selector = ctk.CTkSegmentedButton(
            shell, variable=start_mode_value, values=["Usar prompt-base", "Começar em branco"],
            height=34, corner_radius=8, fg_color=_theme_color("#0D1525"), selected_color=_theme_color("#315A80"),
            selected_hover_color=_theme_color("#3A6A94"), unselected_color=_theme_color("#1A2942"), unselected_hover_color=_theme_color("#263A5B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        start_mode_selector.pack(fill=tk.X, padx=18, pady=(0, 12))

        base_header = ctk.CTkFrame(shell, fg_color="transparent")
        base_header.pack(fill=tk.X, padx=18)
        ctk.CTkLabel(
            base_header, text="FORMATO-BASE", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            base_header, text="Ver prompt-base", width=112, height=26, corner_radius=7,
            fg_color=_theme_color("#1A2942"), hover_color=_theme_color("#263A5B"), text_color=_theme_color("#D8E4FF"), font=("Segoe UI", 9, "bold"),
            command=lambda: self._show_profile_prompt(
                _SUMMARY_TEMPLATE_CODES.get(template_value.get(), "meeting"),
                f"Formato-base · {template_value.get()}",
            ),
        ).pack(side=tk.RIGHT)
        template_selector = ctk.CTkComboBox(
            shell, variable=template_value, values=_SUMMARY_TEMPLATE_LABELS, state="readonly",
            height=34, corner_radius=9, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        template_selector.pack(fill=tk.X, padx=18, pady=(3, 6))
        base_note = ctk.CTkFrame(shell, fg_color=_theme_color("#101C30"), corner_radius=8)
        base_note.pack(fill=tk.X, padx=18, pady=(0, 14))
        base_note_label = ctk.CTkLabel(
            base_note,
            text="", font=("Segoe UI", 9), text_color=_theme_color("#C9D3FF"), anchor="w", justify=tk.LEFT, wraplength=600,
        )
        base_note_label.pack(fill=tk.X, padx=10, pady=7)

        field_label("PROMPT DESTE PERFIL")
        instructions_editor = ctk.CTkTextbox(
            shell, height=154, corner_radius=9, fg_color=_theme_color("#0D1525"), border_width=1,
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Segoe UI", 10), wrap="word",
        )
        instructions_editor.pack(fill=tk.X, padx=18)
        instructions_editor.insert("1.0", initial_instructions)
        ctk.CTkLabel(
            shell,
            text="As regras técnicas de idioma e do formato de resposta continuam protegidas pelo aplicativo.",
            font=("Segoe UI", 9), text_color=_theme_color("#C9D3FF"), anchor="w", justify=tk.LEFT, wraplength=600,
        ).pack(fill=tk.X, padx=18, pady=(4, 10))

        seeded_prompt = [initial_instructions if use_base_initially else ""]

        def seed_for_selected_template() -> str:
            return profile_prompt_seed(_SUMMARY_TEMPLATE_CODES.get(template_value.get(), "meeting"))

        def replace_editor(text: str) -> None:
            instructions_editor.delete("1.0", tk.END)
            instructions_editor.insert("1.0", text)

        def confirm_replacement() -> bool:
            current = instructions_editor.get("1.0", "end-1c").strip()
            if not current or current == seeded_prompt[0].strip():
                return True
            return messagebox.askyesno(
                "Substituir prompt?",
                "Essa escolha substituirá o texto que você está editando. Deseja continuar?",
                parent=dialog,
            )

        def refresh_start_mode(*_args: object) -> None:
            use_base = start_mode_value.get() == "Usar prompt-base"
            template_selector.configure(state="readonly" if use_base else tk.DISABLED)
            if use_base:
                base_note_label.configure(text="O prompt-base completo será carregado no editor para você adaptar e salvar como um perfil próprio.")
                if confirm_replacement():
                    seeded_prompt[0] = seed_for_selected_template()
                    replace_editor(seeded_prompt[0])
                else:
                    start_mode_value.set("Começar em branco")
                    refresh_start_mode()
            else:
                base_note_label.configure(
                    text="Comece seu prompt do zero. Você define livremente as orientações e a estrutura do resumo.",
                )
                if confirm_replacement():
                    replace_editor("")
                    seeded_prompt[0] = ""
                else:
                    start_mode_value.set("Usar prompt-base")
                    refresh_start_mode()

        def change_base_template(_value: str) -> None:
            if start_mode_value.get() != "Usar prompt-base":
                return
            if not confirm_replacement():
                return
            seeded_prompt[0] = seed_for_selected_template()
            replace_editor(seeded_prompt[0])

        start_mode_selector.configure(command=refresh_start_mode)
        template_selector.configure(command=change_base_template)
        if use_base_initially:
            template_selector.configure(state="readonly")
            base_note_label.configure(
                text="O prompt-base completo foi carregado no editor, incluindo idioma, formato de resposta e estrutura. Edite-o e salve uma versão própria.",
            )
        else:
            template_selector.configure(state=tk.DISABLED)
            base_note_label.configure(
                text="Comece seu prompt do zero. Você define livremente as orientações e a estrutura do resumo.",
            )

        preferences = ctk.CTkFrame(shell, fg_color="transparent")
        preferences.pack(fill=tk.X, padx=18, pady=(0, 8))
        ctk.CTkLabel(
            preferences, text="Modelo Whisper", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkComboBox(
            preferences, variable=model_value, values=self._available_models, state="readonly",
            width=132, height=32, corner_radius=8, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        ).pack(side=tk.RIGHT)
        ctk.CTkCheckBox(
            shell, text="Separar falantes quando houver token configurado", variable=speakers_value,
            fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["text"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, padx=18, pady=(0, 14))

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill=tk.X, padx=18, pady=(0, 18))
        ctk.CTkButton(
            actions, text="Cancelar", command=dialog.destroy, width=82, height=34, corner_radius=8,
            fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        ctk.CTkButton(
            actions, text="Salvar alterações" if profile_id else "Salvar perfil",
            command=lambda: self._save_summary_profile(
                dialog, profile_id, name_value.get(),
                template_value.get() if start_mode_value.get() == "Usar prompt-base" else "",
                instructions_editor.get("1.0", "end-1c"), model_value.get(), speakers_value.get(),
            ),
            height=34, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.after(100, name_entry.focus_set)

    def _save_summary_profile(
        self,
        dialog: ctk.CTkToplevel,
        profile_id: str,
        name: str,
        base_template: str,
        instructions: str,
        model_size: str,
        separate_speakers: bool,
    ) -> None:
        from record_transcript_resume.summary_profiles import SummaryProfile, save_profile

        try:
            saved = save_profile(SummaryProfile(
                id=profile_id,
                name=name,
                base_template=_SUMMARY_TEMPLATE_CODES.get(base_template, "") if base_template else "",
                instructions=instructions,
                model_size=model_size,
                separate_speakers=separate_speakers,
                prompt_mode="custom",
            ))
        except ValueError as exc:
            messagebox.showerror("Perfil incompleto", str(exc), parent=dialog)
            return
        self._refresh_summary_profile_choices()
        self.processing_profile.set(f"Perfil salvo · {saved.name}")
        dialog.destroy()
        messagebox.showinfo("Perfil salvo", "O perfil está disponível para gravações, importações e vídeos do YouTube.")

    def _render_api_provider_list(self) -> None:
        """Show saved providers separately from the create/edit form."""
        for child in self.api_provider_list.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.api_provider_list, text="PROVIDERS POR API", font=("Segoe UI", 9, "bold"),
            text_color=_COLORS["muted"], anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(9, 3))
        if not self._api_provider_configs:
            ctk.CTkLabel(
                self.api_provider_list, text="Nenhum provider por API cadastrado ainda.",
                font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, padx=10, pady=(0, 9))
            return
        for config in self._api_provider_configs:
            row = ctk.CTkFrame(self.api_provider_list, fg_color="transparent")
            row.pack(fill=tk.X, padx=10, pady=(0, 6))
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(
                text, text=config.name, font=("Segoe UI", 10, "bold"),
                text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkLabel(
                text, text=f"{config.model} · token {'salvo' if self._api_provider_has_token(config.id) else 'pendente'}",
                font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkButton(
                row, text="Editar", command=lambda provider_id=config.id: self._edit_api_provider(provider_id),
                width=64, height=28, corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
                text_color=_COLORS["text"], font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.RIGHT)

    @staticmethod
    def _api_provider_has_token(provider_id: str) -> bool:
        from record_transcript_resume.api_provider import has_token

        return has_token(provider_id)

    def _refresh_provider_hint(self, *_: object) -> None:
        provider = self._selected_summary_provider_code()
        if provider.startswith("api:"):
            config = self._api_provider_for_id(provider.removeprefix("api:"))
            if config is not None:
                token_status = "token salvo" if self._api_provider_has_token(config.id) else "token pendente"
                self.provider_hint.set(f"Resumo por API · {config.name} · {config.model} · {token_status}")
                return
            self.provider_hint.set("O provider de API selecionado não está mais disponível.")
            return
        self.provider_hint.set(f"Resumo por {self.summary_provider.get()}  ·  altere em Ajustes")

    def _on_provider_changed(self, *_: object) -> None:
        provider_code = self._selected_summary_provider_code()
        self._preferred_summary_provider_code = provider_code
        try:
            save_summary_provider(provider_code)
        except OSError:
            # The active UI selection remains valid even if the disk is
            # temporarily unavailable; never make provider selection fail.
            pass
        self._refresh_provider_hint()
        self.after_idle(self._check_provider_login)

    def _on_transcription_source_changed(self, *_: object) -> None:
        provider = self._selected_transcription_provider_code()
        if provider == "local":
            self.transcription_source_hint.set("Processa o áudio neste computador com o modelo Whisper selecionado.")
            return
        config = self._api_provider_for_id(provider.removeprefix("api:"))
        if config is None:
            self.transcription_source_hint.set("O provider selecionado não está mais disponível.")
            return
        self.transcription_source_hint.set(
            f"Envia o áudio para {config.name} usando {config.transcription_model}. Pode gerar custo e requer internet."
        )

    def _on_model_changed(self, *_: object) -> None:
        model = self.pipeline_model.get()
        self.model_description.set(
            _WHISPER_MODEL_DESCRIPTIONS.get(model, "Modelo Whisper selecionado")
        )
        if not self._local_transcription_test_running:
            self.local_transcription_test_status.set(f"Ainda não testado para {model}.")
            if hasattr(self, "local_transcription_test_label"):
                self.local_transcription_test_label.configure(text_color=_COLORS["muted"])

    def _start_installation_check(self) -> None:
        self.installation_check_button.configure(state=tk.DISABLED, text="Verificando…")
        for status in self.installation_check_status.values():
            status.set("Verificando…")
        output_dir = Path(self.output_dir.get() or default_output_dir()).expanduser()
        threading.Thread(target=self._installation_check_worker, args=(output_dir,), daemon=True).start()

    def _installation_check_worker(self, output_dir: Path) -> None:
        import tempfile

        from record_transcript_resume.synthesis import provider_login_status

        results: dict[str, str] = {}
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix="voice-notes-check-", delete=True):
                pass
            free_mb = shutil.disk_usage(output_dir).free // (1024 * 1024)
            results["output"] = f"OK · gravável · {free_mb} MB livres" if free_mb >= 100 else f"Pouco espaço · {free_mb} MB livres"
        except OSError as exc:
            results["output"] = f"Falhou · {exc}"

        for key, microphone, system in (("microphone", True, False), ("system", False, True)):
            try:
                backend = WindowsAudioBackend(WindowsAudioBackendConfig(
                    capture_microphone=microphone, capture_system_audio=system,
                ))
                mic, loopback = backend._resolve_devices()
                device = mic or loopback
                results[key] = f"OK · {device.name}" if device is not None else "Não encontrado"
            except Exception as exc:
                results[key] = f"Não disponível · {str(exc).strip() or type(exc).__name__}"

        for provider in ("codex", "claude"):
            try:
                state = provider_login_status(provider)
                if not state.installed:
                    results[provider] = "CLI não instalada"
                elif state.authenticated is True:
                    results[provider] = "OK · conta conectada"
                else:
                    results[provider] = "Instalada · faça login ou use o teste de resposta"
            except Exception as exc:
                results[provider] = f"Não foi possível verificar · {str(exc).strip() or type(exc).__name__}"
        self._post_to_ui(self._finish_installation_check, results)

    def _finish_installation_check(self, results: dict[str, str]) -> None:
        self.installation_check_button.configure(state=tk.NORMAL, text="Verificar novamente")
        for key, result in results.items():
            self.installation_check_status[key].set(result)

    def _start_provider_health_check(self, provider: str) -> None:
        if provider not in self._provider_test_status or provider in self._provider_test_running:
            return
        self._provider_test_running.add(provider)
        self._provider_test_status[provider].set("Testando conexão e geração…")
        self._provider_test_labels[provider].configure(text_color=_theme_color("#C9D3FF"))
        self._provider_test_buttons[provider].configure(state=tk.DISABLED, text="Testando…")
        self.install_provider_test_buttons[provider].configure(state=tk.DISABLED, text="Testando…")
        threading.Thread(
            target=self._provider_health_check_worker, args=(provider,), daemon=True,
        ).start()

    def _provider_health_check_worker(self, provider: str) -> None:
        try:
            from record_transcript_resume.log import log_exception
            from record_transcript_resume.synthesis import test_summary_provider

            test_summary_provider(provider)
        except Exception as exc:
            try:
                from record_transcript_resume.log import log_exception

                log_exception(f"Provider health check failed | provider={provider}", exc)
            except Exception:
                pass
            self._post_to_ui(self._finish_provider_health_check, provider, False, str(exc))
            return
        self._post_to_ui(self._finish_provider_health_check, provider, True, "")

    def _finish_provider_health_check(self, provider: str, succeeded: bool, detail: str) -> None:
        self._provider_test_running.discard(provider)
        button = self._provider_test_buttons.get(provider)
        label = self._provider_test_labels.get(provider)
        if button is None or label is None:
            return
        button.configure(state=tk.NORMAL, text="Testar")
        self.install_provider_test_buttons[provider].configure(state=tk.NORMAL, text=f"Testar {'Codex' if provider == 'codex' else 'Claude'}")
        if succeeded:
            self._provider_test_status[provider].set("Tudo certo · resposta recebida")
            label.configure(text_color=_theme_color("#55D6A0"))
        else:
            self._provider_test_status[provider].set(f"Falhou · {detail or 'sem detalhes adicionais'}")
            label.configure(text_color=_COLORS["danger"])

    def _start_local_transcription_test(self) -> None:
        if self._local_transcription_test_running:
            return
        model_size = self.pipeline_model.get()
        self._local_transcription_test_running = True
        self.local_transcription_test_status.set(
            f"Carregando {model_size} e testando localmente… pode baixar na primeira vez."
        )
        self.local_transcription_test_label.configure(text_color=_theme_color("#C9D3FF"))
        self.local_transcription_test_button.configure(state=tk.DISABLED, text="Testando…")
        self.install_local_test_button.configure(state=tk.DISABLED, text="Testando…")
        threading.Thread(
            target=self._local_transcription_test_worker, args=(model_size,), daemon=True,
        ).start()

    def _local_transcription_test_worker(self, model_size: str) -> None:
        import json
        import os
        import subprocess

        from record_transcript_resume.log import log

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--diagnostics-worker", "local-transcription", model_size]
        else:
            src_dir = str(Path(__file__).resolve().parent.parent)
            existing_pp = env.get("PYTHONPATH", "")
            if src_dir not in existing_pp.split(os.pathsep):
                env["PYTHONPATH"] = src_dir + (os.pathsep + existing_pp if existing_pp else "")
            command = [
                sys.executable, "-m", "record_transcript_resume._diagnostics_proc",
                "local-transcription", model_size,
            ]

        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", env=env, **hidden_process_kwargs(),
            )
            stdout, stderr = process.communicate()
        except Exception as exc:
            log(f"GUI: could not start local transcription diagnostic: {type(exc).__name__}: {exc}")
            self._post_to_ui(self._finish_local_transcription_test, model_size, False, str(exc))
            return

        event = None
        for line in stdout.splitlines():
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("type") in {"done", "error"}:
                event = candidate
        if process.returncode == 0 and event is not None and event.get("type") == "done":
            self._post_to_ui(self._finish_local_transcription_test, model_size, True, "")
            return

        error_type = str(event.get("error_type", "")) if event else ""
        message = str(event.get("msg", "")) if event else ""
        detail = f"{error_type}: {message}" if error_type and message else message
        if not detail:
            detail = stderr.strip()[-1000:] or f"O processo de diagnóstico encerrou com código {process.returncode}."
        log(f"GUI: local transcription diagnostic failed | {detail[:300]}")
        self._post_to_ui(self._finish_local_transcription_test, model_size, False, detail)

    def _finish_local_transcription_test(self, model_size: str, succeeded: bool, detail: str) -> None:
        self._local_transcription_test_running = False
        self.local_transcription_test_button.configure(state=tk.NORMAL, text="Testar modelo")
        self.install_local_test_button.configure(state=tk.NORMAL, text="Testar modelo selecionado")
        if succeeded:
            self.local_transcription_test_status.set(
                f"OK · modelo {model_size} carregou e processou o teste local."
            )
            self.local_transcription_test_label.configure(text_color=_theme_color("#55D6A0"))
        else:
            self.local_transcription_test_status.set(f"Falhou · {detail or 'sem detalhes adicionais'}")
            self.local_transcription_test_label.configure(text_color=_COLORS["danger"])

    def _on_processing_profile_changed(self, *_: object) -> None:
        custom = self._custom_summary_profile_for_label(self.processing_profile.get())
        if custom is not None:
            self.summary_template.set(_SUMMARY_TEMPLATE_NAMES_BY_CODE.get(getattr(custom, "base_template"), "Reunião"))
            if getattr(custom, "model_size") in self._available_models:
                self.pipeline_model.set(getattr(custom, "model_size"))
            self.diarize_speakers.set(bool(getattr(custom, "separate_speakers") and self.huggingface_token.get().strip()))
            return
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
        self._sync_recording_result_fields()

    def _sync_recording_result_fields(self) -> None:
        """Show summary inputs only when the recording will generate a summary."""
        preferences = getattr(self, "_recording_summary_preferences", None)
        if preferences is None:
            return
        if self.recording_output_mode.get() == "both":
            if not preferences.winfo_manager():
                preferences.pack(fill=tk.X)
        else:
            preferences.pack_forget()
        self._schedule_content_scrollbar()

    def _sync_recording_status_details(self, *_: object) -> None:
        label = getattr(self, "_recording_limit_status", None)
        if label is None:
            return
        if self.recording_limit_hint.get() == "Sem parada automática":
            label.pack_forget()
        elif not label.winfo_manager():
            label.pack(fill=tk.X, padx=32, pady=(0, 6))

    def _sync_recording_meter(self) -> None:
        meter = getattr(self, "_meter_card", None)
        if meter is None:
            return
        recording = self._service is not None and self._service.state == RecordingState.RECORDING
        errored = any(word in self.status.get().casefold() for word in ("error", "erro", "falha"))
        self._status_indicator.configure(
            fg_color=_theme_color("#F4A7A8") if recording or errored else _theme_color("#55D6A0")
        )
        if recording:
            if not meter.winfo_manager():
                meter.pack(fill=tk.X, padx=12, pady=(0, 10))
        else:
            meter.pack_forget()

    def _check_provider_login(self) -> None:
        """Reflect provider readiness without ever opening a command prompt."""
        provider = self._selected_summary_provider_code()
        if provider.startswith("api:"):
            from record_transcript_resume.api_provider import has_token
            self.provider_login_button.pack_forget()
            self.provider_setup_button.pack_forget()
            provider_id = provider.removeprefix("api:")
            config = self._api_provider_for_id(provider_id)
            self.provider_hint.set(
                f"Resumo por API · {config.name} · token configurado" if config is not None and has_token(provider_id)
                else "O provider selecionado precisa de um token. Use Editar em Ajustes para configurá-lo."
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
            self._post_to_ui(self._on_provider_status_checked, provider, None)
            return
        self._post_to_ui(self._on_provider_status_checked, provider, status)

    def _on_provider_status_checked(self, provider: str, status: object | None) -> None:
        self._provider_status_check_running = False
        if provider != self._selected_summary_provider_code() or status is None:
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
        self._post_to_ui(self._on_provider_setup_finished, message)

    def _on_provider_setup_finished(self, message: str) -> None:
        self._provider_setup_running = False
        self.provider_hint.set(message)
        self.after(400, self._check_provider_login)

    def _start_provider_login(self) -> None:
        """Request browser authentication only when the person chooses it."""
        provider = self._selected_summary_provider_code()
        if provider.startswith("api:"):
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
            card, height=34, width=315, corner_radius=8, fg_color=_theme_color("#0D1525"),
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Consolas", 9),
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
        self.diarize_speakers.set(False)
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
        self._post_to_ui(self._on_update_checked, result)

    def _on_update_checked(self, result: object) -> None:
        self._update_check_running = False
        self._available_update = result
        self.update_hint.set(str(getattr(result, "message", "Não foi possível verificar atualizações.")))
        available = bool(getattr(result, "available", False))
        self.update_check_button.configure(
            state=tk.NORMAL, text="Verificar agora",
            fg_color=_theme_color("#263550") if available else _COLORS["accent"],
            hover_color=_theme_color("#34476B") if available else _COLORS["accent_hover"],
            text_color=_COLORS["text"] if available else _COLORS["accent_text"],
        )
        self.update_apply_button.configure(
            state=tk.NORMAL if available else tk.DISABLED,
            fg_color=_COLORS["accent"] if available else _theme_color("#263550"),
            hover_color=_COLORS["accent_hover"] if available else _theme_color("#34476B"),
            text_color=_COLORS["accent_text"] if available else _COLORS["text"],
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
        self._post_to_ui(self._on_update_applied, result)

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
        self._window_surface.configure(corner_radius=0)
        for widget in self._widget_hidden:
            widget.pack_forget()
        self.title("Voice Notes (Beta)")
        self.attributes("-topmost", True)
        focus_width, focus_height = self._focus_dimensions()
        self.minsize(min(self._min_widget_width, focus_width), min(self._min_widget_height, focus_height))
        self.maxsize(focus_width, focus_height)
        self.overrideredirect(True)
        left, top, monitor_width, monitor_height = self._current_monitor_bounds()
        self._set_widget_geometry(
            focus_width, focus_height,
            left + (monitor_width - focus_width) // 2,
            top + (monitor_height - focus_height) // 2,
        )
        # Releasing anywhere in the widget reliably ends a header drag.  This
        # binding only clears state; it never starts a drag from page controls.
        self.bind("<ButtonRelease-1>", self._stop_window_drag, add="+")
        self.after_idle(self._schedule_widget_rounding)
        self._refresh_provider_hint()

    def _schedule_widget_rounding(self, event: tk.Event[tk.Misc] | None = None) -> None:
        """The focus shell is rectangular, so no native clipping is needed."""
        return

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

            if self._resize_active or (self._maximized and not self._compact_mode):
                user32.SetWindowRgn(hwnd, None, True)
                return

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

    def _geometry_string(self, width: int, height: int, x: int, y: int) -> str:
        """Convert desktop coordinates to Tk offsets, including left/top monitors."""
        virtual_right = self.winfo_vrootx() + self.winfo_vrootwidth()
        virtual_bottom = self.winfo_vrooty() + self.winfo_vrootheight()
        x_position = f"+{x}" if x >= 0 else f"-{max(0, virtual_right - x - width)}"
        y_position = f"+{y}" if y >= 0 else f"-{max(0, virtual_bottom - y - height)}"
        return f"{width}x{height}{x_position}{y_position}"

    def _current_monitor_bounds(self, *, work_area: bool = True) -> tuple[int, int, int, int]:
        """Return the work area or full bounds of the monitor containing the app."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.GetParent.argtypes = (ctypes.c_void_p,)
                user32.GetParent.restype = ctypes.c_void_p
                user32.MonitorFromWindow.argtypes = (ctypes.c_void_p, wintypes.DWORD)
                user32.MonitorFromWindow.restype = ctypes.c_void_p
                user32.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.POINTER(MonitorInfo))
                user32.GetMonitorInfoW.restype = wintypes.BOOL
                child = self.winfo_id()
                monitor = user32.MonitorFromWindow(user32.GetParent(child) or child, 2)
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    rect = info.rcWork if work_area else info.rcMonitor
                    return (
                        rect.left, rect.top,
                        rect.right - rect.left, rect.bottom - rect.top,
                    )
            except (AttributeError, OSError, TypeError):
                pass

        left, top = self.winfo_vrootx(), self.winfo_vrooty()
        width, height = self.winfo_vrootwidth(), self.winfo_vrootheight()
        if width <= 0 or height <= 0:
            return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        return left, top, width, height

    def _monitor_bounds_at(self, x: int, y: int, *, work_area: bool = True) -> tuple[int, int, int, int]:
        """Find the nearest monitor for a proposed window position or pointer."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
                user32.MonitorFromPoint.restype = ctypes.c_void_p
                user32.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.POINTER(MonitorInfo))
                user32.GetMonitorInfoW.restype = wintypes.BOOL
                monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    rect = info.rcWork if work_area else info.rcMonitor
                    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
            except (AttributeError, OSError, TypeError):
                pass
        return self._current_monitor_bounds(work_area=work_area)

    def _clamp_window_position(
        self, width: int, height: int, x: int, y: int,
        *, anchor: tuple[int, int] | None = None,
    ) -> tuple[int, int]:
        """Keep the whole focus window on one monitor whenever it fits."""
        point_x, point_y = anchor or (x + width // 2, y + 24)
        left, top, monitor_width, monitor_height = self._monitor_bounds_at(point_x, point_y)
        margin = 12
        rightmost = max(left + margin, left + monitor_width - width - margin)
        bottommost = max(top + margin, top + monitor_height - height - margin)
        return (
            min(max(x, left + margin), rightmost),
            min(max(y, top + margin), bottommost),
        )

    def _apply_absolute_geometry(self, width: int, height: int, x: int, y: int) -> None:
        """Position the window in desktop coordinates, including negative monitor axes."""
        if sys.platform == "win32":
            try:
                import ctypes

                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.GetParent.argtypes = (ctypes.c_void_p,)
                user32.GetParent.restype = ctypes.c_void_p
                user32.SetWindowPos.argtypes = (
                    ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                )
                user32.SetWindowPos.restype = ctypes.c_int
                child = self.winfo_id()
                wrapper = user32.GetParent(child) or child
                if user32.SetWindowPos(wrapper, None, x, y, width, height, 0x0014):
                    return
            except (AttributeError, OSError, tk.TclError):
                pass
        tk.Tk.geometry(self, self._geometry_string(width, height, x, y))

    def _schedule_window_reachability(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is self and self._reachability_after is None:
            self._reachability_after = self.after(80, self._ensure_window_reachable)

    def _ensure_window_reachable(self) -> None:
        self._reachability_after = None
        if not self.winfo_exists() or self.state() == "iconic" or self._drag_active:
            return
        width, height = self.winfo_width(), self.winfo_height()
        x, y = self.winfo_x(), self.winfo_y()
        if self._maximized and not self._compact_mode:
            safe_x, safe_y, safe_width, safe_height = self._monitor_bounds_at(
                x + width // 2, y + 24, work_area=False,
            )
            if (x, y, width, height) != (safe_x, safe_y, safe_width, safe_height):
                self._apply_absolute_geometry(safe_width, safe_height, safe_x, safe_y)
            return
        safe_x, safe_y = self._clamp_window_position(width, height, x, y)
        if (x, y) != (safe_x, safe_y):
            self._apply_absolute_geometry(width, height, safe_x, safe_y)

    def _focus_dimensions(self) -> tuple[int, int]:
        """Use the approved focus size, clipped to the current monitor."""
        _, _, monitor_width, monitor_height = self._current_monitor_bounds(work_area=True)
        return (
            min(self._preferred_widget_width, max(380, monitor_width - 24)),
            min(self._main_widget_height, max(420, monitor_height - 24)),
        )

    def _fit_dialog(
        self, dialog: tk.Toplevel, width: int, height: int,
        min_width: int = 360, min_height: int = 260,
    ) -> None:
        left, top, available_width, available_height = self._current_monitor_bounds()
        fitted_width = min(width, max(320, available_width - 32))
        fitted_height = min(height, max(240, available_height - 48))
        x = left + max(0, (available_width - fitted_width) // 2)
        y = top + max(0, (available_height - fitted_height) // 2)
        dialog.minsize(min(min_width, fitted_width), min(min_height, fitted_height))
        dialog.geometry(self._geometry_string(fitted_width, fitted_height, x, y))
        # Focus mode is always on top. Its document/settings windows must join
        # the same layer, including after CTk remaps their native title bars.
        dialog.transient(self)
        dialog.attributes("-topmost", bool(self.attributes("-topmost")))
        dialog.bind("<Map>", lambda event: dialog.lift() if event.widget is dialog else None, add="+")

    def _toggle_maximized(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        """Switch between the fixed focus window and the full monitor."""
        if self._compact_mode:
            return "break"
        if hasattr(self, "_focus_meeting_editor"):
            source = self.meeting_instructions_editor if self._maximized else self._focus_meeting_editor
            destination = self._focus_meeting_editor if self._maximized else self.meeting_instructions_editor
            if destination.cget("state") == tk.NORMAL:
                instructions = source.get("1.0", "end-1c")
                destination.delete("1.0", tk.END)
                destination.insert("1.0", instructions)
        self._resize_active = False
        self._pending_resize_geometry = None
        # Windows can maximize this borderless window independently. In the
        # native "zoomed" state, geometry changes do not restore its size.
        if self.state() == "zoomed":
            self.state("normal")
            self.update_idletasks()
            if not self._maximized:
                self._restore_geometry = self.geometry()
                self._restore_bounds = (
                    self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y(),
                )
            self._maximized = True
            self._window_surface.configure(corner_radius=22)
        if not self._maximized:
            self.update_idletasks()
            self._restore_geometry = self.geometry()
            self._restore_bounds = (
                self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y(),
            )
            self._maximized = True
            self.maximize_button.configure(text="Modo foco")
            self.minsize(1, 1)
            self.maxsize(10_000, 10_000)
            self.attributes("-topmost", False)
            left, top, width, height = self._current_monitor_bounds(work_area=False)
            self._apply_absolute_geometry(width, height, left, top)
        else:
            self._maximized = False
            self._window_surface.configure(corner_radius=0)
            self.maximize_button.configure(text="Tela cheia")
            focus_width, focus_height = self._focus_dimensions()
            self.minsize(min(self._min_widget_width, focus_width), min(self._min_widget_height, focus_height))
            self.maxsize(focus_width, focus_height)
            restore_x, restore_y = (
                self._restore_bounds[2], self._restore_bounds[3]
            ) if self._restore_bounds is not None else (self.winfo_x(), self.winfo_y())
            self._set_widget_geometry(
                focus_width, focus_height,
                restore_x, restore_y,
            )
            self.update_idletasks()
            self.attributes("-topmost", True)
            self.after_idle(self._adapt_fullscreen_content)
            self.after_idle(self._apply_page_minimum)
        if self._maximized:
            self.after_idle(self._adapt_fullscreen_content)
        self.after_idle(lambda: self._show_page(self._current_page, refresh_data=False))
        if self._current_page == "processing":
            self.after(120, self._refresh_processing_page)
        self._schedule_widget_rounding()
        self._schedule_content_scrollbar()
        self._schedule_window_repaint()
        return "break"

    def _schedule_window_repaint(self) -> None:
        """Paint the settled native window once after a mode/size transition."""
        if self._window_repaint_after is not None:
            self.after_cancel(self._window_repaint_after)
        self._window_repaint_after = self.after(100, self._repaint_window)

    def _repaint_window(self) -> None:
        self._window_repaint_after = None
        if sys.platform != "win32" or not self.winfo_exists():
            return
        self.update_idletasks()
        self._retheme_widget_tree(self, visible_only=True, force=True)
        self.update_idletasks()
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetParent.argtypes = (ctypes.c_void_p,)
            user32.GetParent.restype = ctypes.c_void_p
            user32.RedrawWindow.argtypes = (
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
            )
            user32.RedrawWindow.restype = ctypes.c_int
            child = self.winfo_id()
            wrapper = user32.GetParent(child) or child
            # Invalidate and erase all native children, then paint immediately.
            # SetWindowPos can otherwise leave copied focus-mode pixels until
            # Windows delivers its next deferred WM_PAINT messages.
            user32.RedrawWindow(wrapper, None, None, 0x0185)
        except (AttributeError, OSError, tk.TclError):
            pass

    def _sync_window_controls(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self or self._compact_mode:
            return
        label = "Modo foco" if self._maximized or self.state() == "zoomed" else "Tela cheia"
        if self.maximize_button.cget("text") != label:
            self.maximize_button.configure(text=label)

    def _adapt_fullscreen_content(self) -> None:
        """Keep the readable application shell centered on wide displays."""
        if not self.winfo_exists():
            return
        self._update_shell_layout()
        self._schedule_content_scrollbar()

    def _apply_focus_chrome(self) -> None:
        """Give the fixed focus window the approved titlebar and navigation."""
        if self._maximized:
            if not self._header_title.winfo_manager():
                self._header_title.pack(anchor=tk.W, pady=(8, 6))
            if not self._header_drag_hint.winfo_manager():
                self._header_drag_hint.pack(anchor=tk.W)
            self._header.configure(fg_color="transparent")
            self._header.pack_propagate(True)
            inset = max(20, (self.winfo_width() - self._maximized_content_width) // 2)
            self._header.pack_configure(
                padx=inset if self._wide_shell else 20, pady=(16, 8),
            )
            self._title_block.pack_configure(padx=0, pady=0)
            self._window_controls.pack_configure(padx=0, pady=0)
            self.close_button.configure(
                text="Encerrar", width=64, font=("Segoe UI", 10, "bold"),
            )
            self._navigation.configure(
                fg_color=_theme_color("#0D1525"), corner_radius=10, border_width=0,
            )
        else:
            self._header_title.pack_forget()
            self._header_drag_hint.pack_forget()
            self._header.configure(fg_color=_theme_color("#101929"), height=60)
            self._header.pack_propagate(False)
            self._header.pack_configure(padx=0, pady=0)
            self._title_block.pack_configure(padx=(19, 0), pady=(16, 0))
            self._window_controls.pack_configure(padx=(0, 18), pady=(14, 0))
            self.close_button.configure(
                text="Encerrar", width=64, font=("Segoe UI", 10, "bold"),
            )
            self._navigation.configure(
                fg_color=_theme_color("#101929"), corner_radius=0,
                border_width=1, border_color=_theme_color("#30405D"),
            )
        columns = (
            1 if self._wide_shell else (3 if self._navigation.winfo_width() < 550 else 6)
        ) if self._maximized else 6
        for index, button in enumerate(self._page_buttons.values()):
            self._navigation.grid_columnconfigure(
                index, weight=1 if self._maximized and index < columns else 0,
            )
            button.configure(
                width=78 if self._maximized else 92,
                height=42 if self._maximized and columns == 1 else 34 if self._maximized else 35,
                font=("Segoe UI", 12 if self._maximized and columns == 1 else 11,
                      "bold" if self._maximized else "normal"),
            )
        # Layout changes above also propagate backgrounds to child controls.
        # Synchronize after that propagation, before these controls are mapped.
        self._retheme_widget_tree(self._header)
        self._retheme_widget_tree(self._navigation)

    def _update_shell_layout(self) -> None:
        """Use a side navigation on wide windows and a top navigation otherwise."""
        if not hasattr(self, "_workspace") or self._compact_mode:
            return
        width = self.winfo_width()
        wide = self._maximized and width >= 920
        inset = max(20, (width - self._maximized_content_width) // 2) if wide else 0
        self._header.pack_configure(padx=(inset or 20) if self._maximized else 0)
        self._workspace.pack_configure(padx=inset)
        if wide != self._wide_shell:
            self._navigation.pack_forget()
            self._main_shell.pack_forget()
            self._wide_shell = wide
            if wide:
                self._navigation.configure(width=184)
                self._navigation.grid_propagate(False)
                self._navigation.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12), pady=(4, 6))
                self._main_shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            else:
                self._navigation.grid_propagate(True)
                self._navigation.pack(
                    side=tk.TOP, fill=tk.X,
                    padx=20 if self._maximized else 0,
                    pady=(4, 8) if self._maximized else (0, 0),
                )
                self._main_shell.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self._layout_navigation(self._navigation.winfo_width())
        if not wide:
            self._navigation.pack_configure(
                padx=20 if self._maximized else 0,
                pady=(4, 8) if self._maximized else (0, 0),
            )
        self._apply_focus_chrome()
        self._container._parent_frame.pack_configure(padx=2, pady=(0, 4))
        desktop = self._maximized and wide and width >= 1280 and self.winfo_height() >= 700
        if desktop != self._desktop_layout:
            self._desktop_layout = desktop
            if hasattr(self, "_page_layouts"):
                self._show_page(self._current_page, refresh_data=False)
        elif self._desktop_layout:
            self._processing_panel.configure(height=max(650, self.winfo_height() - 170))
        if hasattr(self, "_focus_library_panel") and self._maximized:
            self._focus_library_panel.configure(height=max(650, self.winfo_height() - 140))
        if hasattr(self, "_inline_buttons") and getattr(self, "_current_page", None) == "record":
            self._sync_recording_action_location()

    def _ensure_page_layout(self, page: str) -> None:
        """Reflow the visible destination when the desktop breakpoint changes."""
        if self._page_layout_desktop.get(page) == self._desktop_layout:
            return
        if page == "record":
            self._layout_record_sections()
            self._layout_source_choices()
        elif page in {"file", "youtube"}:
            self._layout_import_actions()
            self._page_layout_desktop["file"] = self._desktop_layout
            self._page_layout_desktop["youtube"] = self._desktop_layout
        elif page == "library":
            self._layout_browser()
        elif page == "processing":
            self._layout_processing_panel()
        self._page_layout_desktop[page] = self._desktop_layout

    def _layout_record_sections(self) -> None:
        if not hasattr(self, "_record_source_section"):
            return
        sections = (
            self._record_source_section, self._record_result_section,
            self._record_save_section,
        )
        for section in sections:
            section.pack_forget()
            section.grid_forget()
        if self._desktop_layout:
            self._record_capture_card.grid_columnconfigure(0, weight=1, uniform="record")
            self._record_capture_card.grid_columnconfigure(1, weight=1, uniform="record")
            self._record_source_section.grid(
                row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12),
            )
            self._record_result_section.grid(
                row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 10),
            )
            self._record_save_section.grid(
                row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10),
            )
        else:
            self._record_source_section.pack(fill=tk.X, pady=(0, 10))
            self._record_result_section.pack(fill=tk.X, pady=(0, 10))
            self._record_save_section.pack(fill=tk.X)

    def _layout_source_choices(self) -> None:
        if not hasattr(self, "_source_choice_cards"):
            return
        for choice, detail in zip(self._source_choice_cards, self._source_choice_descriptions):
            choice.pack_forget()
            if self._desktop_layout:
                choice.configure(fg_color=_theme_color("#0D1525"))
                detail.pack(fill=tk.X, padx=14, pady=(0, 10))
                choice.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            else:
                choice.configure(fg_color="transparent")
                detail.pack_forget()
                choice.pack(side=tk.LEFT, padx=(0, 4))

    def _layout_import_actions(self) -> None:
        if not hasattr(self, "youtube_process_button"):
            return
        for button, width in (
            (self.process_button, 290),
            (self.text_import_button, 290),
            (self.retry_summary_button, 350),
        ):
            button.configure(width=width if self._desktop_layout else 140)
            button.pack_configure(
                fill=tk.NONE if self._desktop_layout else tk.X,
                anchor=tk.W if self._desktop_layout else tk.CENTER,
            )
        self.youtube_process_button.pack_forget()
        self._youtube_hint_label.pack_forget()
        if self._desktop_layout:
            self._youtube_hint_label.pack(
                side=tk.BOTTOM, fill=tk.X, padx=17, pady=(0, 16),
            )
            self.youtube_process_button.configure(width=300)
            self.youtube_process_button.pack(
                side=tk.BOTTOM, anchor=tk.W, padx=16, pady=(12, 6),
            )
        else:
            self.youtube_process_button.configure(width=140)
            self.youtube_process_button.pack(fill=tk.X, padx=16, pady=(12, 4))
            self._youtube_hint_label.pack(fill=tk.X, padx=17, pady=(0, 12))

    def _layout_browser(self) -> None:
        """Use the same folder browser in focus and full-screen layouts."""
        if not hasattr(self, "_browser_area"):
            return
        self._browser_heading_text.set("Explorar arquivos" if self._maximized else "Biblioteca")
        table = self._browser_table_holder
        preview = self._browser_preview
        table.pack_forget()
        preview.pack_forget()
        self._focus_library_panel.pack_propagate(not self._maximized)
        if self._desktop_layout:
            preview.configure(width=430, height=150)
            preview.pack(side=tk.RIGHT, fill=tk.Y, padx=(14, 0), pady=(0, 12))
            preview.pack_propagate(False)
            table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self._browser_preview_body_label.configure(wraplength=390)
            self._browser_preview_details_label.pack(
                fill=tk.X, padx=14, pady=(16, 0),
                before=self._browser_open_button.master,
            )
        else:
            preview.configure(height=150 if self._browser_selected and self._browser_selected.kind == "audio" else 108)
            preview.pack_propagate(False)
            preview.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 12))
            table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self._browser_preview_body_label.configure(wraplength=600)
            self._browser_preview_details_label.pack_forget()

    def _layout_processing_panel(self) -> None:
        if not hasattr(self, "_processing_panel"):
            return
        if self._desktop_layout:
            self._processing_panel.configure(height=max(650, self.winfo_height() - 170))
            self._processing_panel.pack_propagate(False)
        else:
            self._processing_panel.pack_propagate(True)

    def _apply_desktop_typography(self) -> None:
        """Make content readable on large screens without enlarging the widget mode."""
        if not hasattr(self, "_container"):
            return
        styled = (
            ctk.CTkLabel, ctk.CTkButton, ctk.CTkEntry, ctk.CTkComboBox,
            ctk.CTkOptionMenu, ctk.CTkCheckBox, ctk.CTkRadioButton,
            ctk.CTkTextbox, tk.Listbox,
        )
        for old in tuple(self._desktop_style_original):
            if not old.winfo_exists():
                del self._desktop_style_original[old]
                self._desktop_style_applied.pop(old, None)

        def visit(parent: tk.Misc) -> None:
            for widget in parent.winfo_children():
                if isinstance(widget, styled):
                    if widget not in self._desktop_style_original:
                        try:
                            original_font = widget.cget("font")
                        except (tk.TclError, ValueError):
                            original_font = None
                        original_height = None
                        if isinstance(widget, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkOptionMenu)):
                            try:
                                original_height = int(widget.cget("height"))
                            except (tk.TclError, TypeError, ValueError):
                                pass
                        self._desktop_style_original[widget] = (original_font, original_height)
                    original_font, original_height = self._desktop_style_original[widget]
                    target_font = original_font
                    target_height = original_height
                    if isinstance(original_font, tuple) and len(original_font) >= 2:
                        try:
                            base_size = int(original_font[1])
                        except (TypeError, ValueError):
                            base_size = 0
                        if base_size:
                            minimum = (13 if self._desktop_layout else 11) if isinstance(widget, (
                                ctk.CTkButton, ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkOptionMenu,
                                ctk.CTkCheckBox, ctk.CTkRadioButton, ctk.CTkTextbox,
                                tk.Listbox,
                            )) else (12 if self._desktop_layout else 11)
                            if isinstance(widget, ctk.CTkLabel) and len(original_font) > 2 and "bold" in str(original_font[2]):
                                minimum = 13 if self._desktop_layout else 11
                            target_size = max(base_size, minimum)
                            target_font = (original_font[0], target_size, *original_font[2:])
                    if original_height is not None:
                        if self._desktop_layout:
                            min_height = 38 if isinstance(widget, (ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkOptionMenu)) else 34
                        else:
                            min_height = 32
                        target_height = max(original_height, min_height)
                    applied = self._desktop_style_applied.get(widget)
                    if applied != (target_font, target_height):
                        if target_font is not None and (applied is None or applied[0] != target_font):
                            widget.configure(font=target_font)
                        if target_height is not None and (applied is None or applied[1] != target_height):
                            widget.configure(height=target_height)
                        self._desktop_style_applied[widget] = (target_font, target_height)
                visit(widget)

        visit(self._container)

    def _sync_recording_action_location(self) -> None:
        """Keep the action near the form on wide windows and fixed on narrow ones."""
        if self._compact_mode or self._current_page != "record":
            return
        if not self._maximized:
            self._buttons.pack_forget()
            self._inline_buttons.pack_forget()
            self._record_recent_panel.pack_forget()
            return
        if self._use_inline_recording_actions():
            self._buttons.pack_forget()
            if not self._inline_buttons.winfo_manager():
                self._inline_buttons.pack(
                    after=self._record_capture_card, fill=tk.X, padx=20, pady=(4, 16),
                )
            if not self._record_recent_panel.winfo_manager():
                self._record_recent_panel.pack(
                    after=self._inline_buttons, fill=tk.X, padx=20, pady=(0, 8),
                )
            self._container._parent_frame.pack_configure(pady=(0, 20))
        else:
            self._inline_buttons.pack_forget()
            self._record_recent_panel.pack_forget()
            if not self._buttons.winfo_manager():
                self._buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
            self._container._parent_frame.pack_configure(pady=(0, 4))

    def _use_inline_recording_actions(self) -> bool:
        return self._maximized and self._wide_shell and self.winfo_height() >= 760

    def _set_recording_action_state(
        self, *, start: str | None = None, stop: str | None = None,
        show_stop: bool | None = None,
    ) -> None:
        """Mirror recording controls in the fixed and inline action bars."""
        if start is not None:
            self.start_button.configure(state=start)
            self.inline_start_button.configure(state=start)
            self._focus_start_button.configure(state=start)
        if stop is not None:
            self.stop_button.configure(state=stop)
            self.inline_stop_button.configure(state=stop)
            self._focus_stop_button.configure(state=stop)
        if show_stop is not None:
            for button in (self.stop_button, self.inline_stop_button):
                if show_stop and not button.winfo_manager():
                    button.pack(side=tk.LEFT, padx=(8, 0))
                elif not show_stop:
                    button.pack_forget()
            if show_stop and not self._focus_stop_button.winfo_manager():
                self._focus_stop_button.pack(side=tk.LEFT, padx=(8, 0))
            elif not show_stop:
                self._focus_stop_button.pack_forget()

    def _make_draggable(self, *widgets: tk.Misc) -> None:
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
            widget.bind("<B1-Motion>", self._drag_window, add="+")

    def _install_button_tooltips(self) -> None:
        """Use one tooltip for every button, including buttons created later."""
        self.bind_all("<Enter>", self._button_tooltip_enter, add="+")
        self.bind_all("<Leave>", self._button_tooltip_leave, add="+")
        self.bind_all("<ButtonPress>", lambda _event: self._hide_button_tooltip(), add="+")
        self.bind_all("<KeyPress>", lambda _event: self._hide_button_tooltip(), add="+")
        self.bind_all("<MouseWheel>", lambda _event: self._hide_button_tooltip(), add="+")

    @staticmethod
    def _button_at_widget(widget: tk.Misc) -> tk.Misc | None:
        while widget is not None:
            if isinstance(widget, (ctk.CTkButton, tk.Button, ttk.Button)):
                return widget
            widget = widget.master
        return None

    def _button_tooltip_enter(self, event: tk.Event[tk.Misc]) -> None:
        button = self._button_at_widget(event.widget)
        if button is None:
            return
        if button is self._button_tooltip_target:
            return
        self._hide_button_tooltip()
        self._button_tooltip_target = button
        self._button_tooltip_after = self.after(600, self._show_button_tooltip)

    def _button_tooltip_leave(self, event: tk.Event[tk.Misc]) -> None:
        button = self._button_at_widget(event.widget)
        if button is None or button is not self._button_tooltip_target:
            return
        try:
            x, y = self.winfo_pointerxy()
            inside = (
                button.winfo_rootx() <= x < button.winfo_rootx() + button.winfo_width()
                and button.winfo_rooty() <= y < button.winfo_rooty() + button.winfo_height()
            )
        except tk.TclError:
            inside = False
        if not inside:
            self._hide_button_tooltip()

    def _button_help_text(self, button: tk.Misc) -> str:
        label = str(button.cget("text") or "").strip()
        command = button.cget("command")
        name = getattr(command, "__name__", "")

        if button is getattr(self, "_browser_play_button", None):
            return ("Pausa a reprodução do áudio selecionado."
                    if self._browser_audio_playing else "Reproduz o áudio selecionado nesta janela.")
        if button is getattr(self, "_browser_back_button", None):
            return (_BUTTON_HELP["←"] if self._browser_history
                    else "Não há outra pasta anterior nesta navegação.")
        if button is getattr(self, "_browser_up_button", None):
            directory = self._browser_directory
            return (_BUTTON_HELP["↑"] if directory is not None and directory.parent != directory
                    else "Esta pasta não tem outra pasta acima dela.")
        if name == "_toggle_maximized":
            return (_BUTTON_HELP["Modo foco"] if self._maximized else _BUTTON_HELP["Tela cheia"])
        if name == "_start_installation_check":
            return "Verifica se o modelo local e os provedores de IA estão prontos para uso."
        if name == "_check_for_updates":
            return "Procura uma versão mais recente do Voice Notes."
        if name == "_save_imported_text":
            return "Salva o texto importado como transcrição."
        if name == "_save_open_document":
            return "Salva as alterações no documento aberto."
        if name == "_save_transcript_and_regenerate":
            return "Salva a transcrição editada e gera um novo resumo."
        if name == "_edit_selected_transcript":
            return "Abre a transcrição selecionada para leitura e edição."
        if name == "_open_selected_summary":
            return "Abre o resumo selecionado para leitura e edição."
        if name == "_restore_full_widget":
            return "Expande o controle compacto para a janela do app."
        if name == "_browser_open":
            entry = self._browser_selected
            if entry is not None and entry.kind in {"folder", "recording", "text_record"}:
                return "Entra na pasta selecionada e mostra seu conteúdo."
            return _BUTTON_HELP.get(label, _BUTTON_HELP["Abrir"])
        if name == "save_metadata":
            return "Salva o título e as etiquetas deste item."

        breadcrumb = getattr(self, "_browser_breadcrumb", None)
        parent = button.master
        while parent is not None:
            if parent is breadcrumb:
                return f"Abre a pasta {label} na Biblioteca."
            parent = parent.master

        if button is getattr(self, "library_tag_selector", None):
            return "Escolhe a etiqueta usada para filtrar a Biblioteca."
        if button is getattr(self, "library_filter_selector", None):
            return "Filtra as gravações pelo estado do áudio e dos resultados."
        if button is getattr(self, "library_sort_selector", None):
            return "Escolhe a ordem de exibição das gravações."
        if label in _BUTTON_HELP:
            return _BUTTON_HELP[label]
        if label.endswith("▾") or label.endswith("▴"):
            return f"Mostra ou oculta as opções de {label[:-1].strip().lower()}."
        if label.startswith("Abrir "):
            return f"Abre {label[6:].lower()} para o item selecionado."
        if label.startswith("Testar "):
            return f"Verifica o funcionamento de {label[7:]}."
        if label.startswith("Salvar "):
            return f"Salva {label[7:].lower()}."
        return f"Executa a ação “{label or 'selecionada'}” nesta tela."

    def _show_button_tooltip(self) -> None:
        self._button_tooltip_after = None
        button = self._button_tooltip_target
        if button is None:
            return
        try:
            if not button.winfo_exists() or not button.winfo_ismapped():
                return
            x, y = self.winfo_pointerxy()
            if not (
                button.winfo_rootx() <= x < button.winfo_rootx() + button.winfo_width()
                and button.winfo_rooty() <= y < button.winfo_rooty() + button.winfo_height()
            ):
                return
            description = self._button_help_text(button)
        except tk.TclError:
            return

        if self._button_tooltip_popup is None:
            popup = tk.Toplevel(self)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.attributes("-topmost", True)
            popup.configure(bg=_theme_color("#53647F"))
            body = tk.Frame(popup, bg=_theme_color("#263550"))
            body.pack(padx=1, pady=1)
            self._button_tooltip_label = tk.Label(
                body, bg=_theme_color("#263550"), fg=_theme_color("#F1F5FB"), font=("Segoe UI", 10),
                justify=tk.LEFT, wraplength=300, padx=10, pady=7,
            )
            self._button_tooltip_label.pack()
            self._button_tooltip_popup = popup
        popup = self._button_tooltip_popup
        assert self._button_tooltip_label is not None
        # Native Tk tooltips are cached between hovers. Resolve their colors
        # again after a palette change, just as freshly created controls do.
        popup.configure(bg=_theme_color("#53647F"))
        self._button_tooltip_label.master.configure(bg=_theme_color("#263550"))
        self._button_tooltip_label.configure(
            text=description, bg=_theme_color("#263550"), fg=_theme_color("#F1F5FB"),
        )
        popup.update_idletasks()
        width, height = popup.winfo_reqwidth(), popup.winfo_reqheight()
        left, top, monitor_width, monitor_height = self._monitor_bounds_at(x, y)
        popup_x = min(max(x + 14, left + 8), max(left + 8, left + monitor_width - width - 8))
        popup_y = y + 20
        if popup_y + height > top + monitor_height - 8:
            popup_y = y - height - 12
        popup_y = max(top + 8, popup_y)
        popup.geometry(self._geometry_string(width, height, popup_x, popup_y))
        popup.deiconify()
        popup.lift()

    def _hide_button_tooltip(self) -> None:
        if self._button_tooltip_after is not None:
            self.after_cancel(self._button_tooltip_after)
            self._button_tooltip_after = None
        self._button_tooltip_target = None
        if self._button_tooltip_popup is not None:
            self._button_tooltip_popup.withdraw()

    def _start_window_drag(self, event: tk.Event[tk.Misc]) -> None:
        if self._maximized:
            return
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()
        self._drag_active = True

    def _drag_window(self, event: tk.Event[tk.Misc]) -> None:
        if not self._drag_active or self._maximized:
            return

        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        self._set_widget_geometry(
            self.winfo_width(), self.winfo_height(), x, y,
            anchor=(event.x_root, event.y_root),
        )

    def _stop_window_drag(self, _event: tk.Event[tk.Misc]) -> None:
        self._drag_active = False
        self._ensure_window_reachable()

    def _is_resize_corner(self, event: tk.Event[tk.Misc]) -> bool:
        """Return whether a pointer event is in the invisible resize corner."""
        if self._compact_mode or self._maximized:
            return False
        try:
            if event.widget.winfo_toplevel() is not self:
                return False
        except tk.TclError:
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
        self._resize_active = True
        self._user_resized_window = True
        if self._round_region_after is not None:
            self.after_cancel(self._round_region_after)
            self._round_region_after = None
        if self._responsive_wrap_after is not None:
            self.after_cancel(self._responsive_wrap_after)
            self._responsive_wrap_after = None
        # The old native clipping region would cut off newly exposed content.
        self._apply_widget_rounding()

    def _resize_window(self, event: tk.Event[tk.Misc]) -> None:
        if not self._resize_active or self._compact_mode or self._maximized:
            return
        delta_x = event.x_root - self._resize_origin_x
        delta_y = event.y_root - self._resize_origin_y
        left, top, monitor_width, monitor_height = self._current_monitor_bounds(work_area=True)
        maximum_width = max(1, left + monitor_width - self.winfo_x() - 12)
        maximum_height = max(1, top + monitor_height - self.winfo_y() - 12)
        width = min(maximum_width, max(self._active_min_width, self._resize_origin_width + delta_x))
        height = min(maximum_height, max(self._active_min_height, self._resize_origin_height + delta_y))
        self._pending_resize_geometry = (width, height)
        if self._resize_apply_after is None:
            # Apply geometry at a modest rate while allowing normal responsive
            # layout; scaling every CTk widget during pointer motion caused
            # clipping and unstable measurements on high-DPI displays.
            self._resize_apply_after = self.after(70, self._apply_pending_resize)

    def _apply_pending_resize(self) -> None:
        self._resize_apply_after = None
        target_geometry = self._pending_resize_geometry
        self._pending_resize_geometry = None
        if target_geometry is None or not self._resize_active:
            return
        width, height = target_geometry
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
        self.after_idle(self._update_responsive_wraps)
        self._schedule_widget_rounding()
        self.after_idle(self._apply_page_minimum)

    def _minimize_widget(self) -> None:
        """Collapse into the fixed, always-on-top recording label."""
        if self._compact_mode:
            return
        if self.state() == "zoomed":
            # A native maximized window ignores the compact label's geometry.
            self.state("normal")
            self.update_idletasks()
            if self._maximized and self._restore_geometry:
                tk.Tk.geometry(self, self._restore_geometry)
            self._maximized = False
            self.maximize_button.configure(text="Tela cheia")
            self.minsize(self._active_min_width, self._active_min_height)
        self._full_widget_geometry = self.geometry()
        self._full_widget_bounds = (
            self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y(),
        )
        full_x, full_y = self.winfo_x(), self.winfo_y()
        full_width = self.winfo_width()
        self._compact_mode = True
        self._drag_active = False
        self._resize_active = False
        self._buttons.pack_forget()
        self._window_surface.pack_forget()
        self.maxsize(10_000, 10_000)
        self.minsize(self._compact_width, self._compact_height)
        self._retheme_widget_tree(self._compact_surface)
        self._compact_surface.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._place_compact_widget(
            *(self._compact_position or (full_x + max(0, (full_width - self._compact_width) // 2), full_y + 12))
        )
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self._refresh_compact_controls()
        self._schedule_window_repaint()

    def _place_compact_widget(self, x: int, y: int) -> None:
        """Place the movable compact label while keeping it reachable on screen."""
        width, height = self._compact_width, self._compact_height
        safe_x, safe_y = self._clamp_window_position(width, height, x, y)
        self._compact_position = (safe_x, safe_y)
        self._apply_absolute_geometry(width, height, safe_x, safe_y)
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
        bounds = self._full_widget_bounds
        self._compact_surface.pack_forget()
        # Keep the full widget's silhouette identical to its initial state.
        self._window_surface.pack(fill=tk.BOTH, expand=True)
        self._window_surface.configure(corner_radius=22 if self._maximized else 0)
        if self._current_page == "record" and self._maximized and not self._use_inline_recording_actions():
            self._buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
        if not self._maximized:
            focus_width, focus_height = self._focus_dimensions()
            self.maxsize(focus_width, focus_height)
            self.minsize(min(self._active_min_width, focus_width),
                         min(self._active_min_height, focus_height))
        else:
            self.minsize(1, 1)
        if self._maximized:
            original_x, original_y = (bounds[2], bounds[3]) if bounds else (self.winfo_x(), self.winfo_y())
            left, top, width, height = self._monitor_bounds_at(
                original_x + self._preferred_widget_width // 2,
                original_y + 24, work_area=False,
            )
            self._apply_absolute_geometry(width, height, left, top)
        else:
            width, height = self._focus_dimensions()
            original_x, original_y = (bounds[2], bounds[3]) if bounds else (self.winfo_x(), self.winfo_y())
            self._set_widget_geometry(width, height, original_x, original_y)
        self._compact_mode = False
        self._schedule_widget_rounding()
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self.deiconify()
        self.lift()
        self.attributes("-topmost", not self._maximized)
        self._schedule_window_repaint()
        self.after_idle(self._apply_page_minimum)

    def _refresh_compact_controls(self) -> None:
        """Keep compact status and actions truthful without opening the widget."""
        self._tray.refresh()
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
            activity = self._processing_activity or "Processando"
            label, color = f"{activity.upper()}  {self.elapsed.get()}", _COLORS["accent"]
        elif any(token in self.status.get().casefold() for token in ("error", "falhou", "falha")):
            label, color = "ATENÇÃO NECESSÁRIA", _COLORS["danger"]
        else:
            label, color = "PRONTO PARA GRAVAR", _COLORS["success"]
        self._compact_status.set(label)
        self._compact_indicator.configure(fg_color=color)
        self.compact_start_button.configure(state=tk.DISABLED if recording or finalizing else tk.NORMAL)
        self.compact_stop_button.configure(state=tk.NORMAL if recording else tk.DISABLED)

    def _hide_to_tray(self) -> None:
        """Remove the widget from the desktop while keeping its tray controls."""
        self._close_browser_audio()
        if not self._tray_available:
            # Keep a reachable window if Windows could not expose the tray icon.
            # Tk cannot iconify an override-redirect window. Temporarily let
            # the window manager own it and restore the borderless surface on
            # the next Map event.
            if self.overrideredirect():
                self.overrideredirect(False)
                self._restore_borderless_on_map = True
            try:
                self.iconify()
            except tk.TclError:
                self._restore_borderless()
                self.lift()
            return
        self.withdraw()

    def _show_widget(self) -> None:
        """Restore and focus the widget after a notification-area action."""
        self.deiconify()
        self._restore_full_widget()
        self._ensure_window_reachable()
        self.lift()
        self.attributes("-topmost", not self._maximized)
        self.focus_force()

    def _restore_borderless_after_minimize(self, _event: tk.Event[tk.Misc]) -> None:
        if not self._restore_borderless_on_map:
            return

        self.after_idle(self._restore_borderless)

    def _restore_borderless(self) -> None:
        if self._restore_borderless_on_map and self.state() != "iconic":
            self.overrideredirect(True)
            self._restore_borderless_on_map = False
            self._ensure_window_reachable()
            self._schedule_widget_rounding()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or ".")
        if selected:
            self.output_dir.set(selected)
            self._refresh_recording_recent()

    def _on_output_directory_changed(self, *_: object) -> None:
        if not self._library_directory_manual:
            self.library_dir.set(self.output_dir.get())
            self._browser_directory = None

    def _choose_library_dir(self) -> None:
        current = Path(self.library_dir.get()).expanduser()
        initial = current if current.is_dir() else Path(self.output_dir.get() or default_output_dir())
        selected = filedialog.askdirectory(
            parent=self, title="Escolher pasta da Biblioteca", initialdir=str(initial),
        )
        if not selected:
            return
        self._library_directory_manual = True
        self.library_dir.set(str(Path(selected).resolve()))
        self._browser_directory = None
        self.library_use_recording_button.configure(state=tk.NORMAL)
        self._focus_library_use_recording_button.configure(state=tk.NORMAL)
        try:
            save_library_directory(self.library_dir.get())
        except OSError as exc:
            self.status.set(f"Pasta alterada, mas não foi possível lembrá-la ao reiniciar: {exc}")
        self._reset_library_filters()
        self._refresh_library()

    def _use_recording_library_dir(self) -> None:
        self._library_directory_manual = False
        self.library_dir.set(self.output_dir.get())
        self._browser_directory = None
        self.library_use_recording_button.configure(state=tk.DISABLED)
        self._focus_library_use_recording_button.configure(state=tk.DISABLED)
        try:
            save_library_directory("")
        except OSError as exc:
            self.status.set(f"Pasta alterada, mas não foi possível lembrar a escolha: {exc}")
        self._reset_library_filters()
        self._refresh_library()

    def _set_capture_preferences_state(self, state: str) -> None:
        for button in self._source_buttons:
            button.configure(state=state)
        for button in getattr(self, "_focus_source_buttons", ()):
            button.configure(state=state)
        selector = getattr(self, "recording_output_selector", None)
        if selector is not None:
            selector.configure(state="readonly" if state == tk.NORMAL else state)
        self.output_entry.configure(state=state)
        self.output_browse_button.configure(state=state)
        self.recording_limit_entry.configure(state=state)
        self.recording_limit_selector.configure(state="readonly" if state == tk.NORMAL else state)
        self.profile_selector.configure(state="readonly" if state == tk.NORMAL else state)
        self.meeting_instructions_editor.configure(state=state)
        if hasattr(self, "_focus_record_result_selector"):
            for widget in (
                self._focus_record_result_selector, self._focus_profile_selector,
                self._focus_stop_selector,
            ):
                widget.configure(state="readonly" if state == tk.NORMAL else state)
            self._focus_output_browse.configure(state=state)
            self._focus_meeting_editor.configure(state=state)
        if hasattr(self, "transcription_source_selector"):
            self.transcription_source_selector.configure(state="readonly" if state == tk.NORMAL else state)

    def _set_summary_template_state(self, state: str) -> None:
        combobox_state = "readonly" if state == tk.NORMAL else state
        self.profile_selector.configure(state=combobox_state)
        self.youtube_profile_selector.configure(state=combobox_state)

    def _set_navigation_state(self, state: str) -> None:
        for button in self._page_buttons.values():
            button.configure(state=state)

    def _apply_page_minimum(self) -> None:
        """Keep focus dimensions fixed while pages scroll within the shell."""
        if self._compact_mode or self._resize_active:
            return
        self.update_idletasks()
        if self._maximized:
            self._schedule_content_scrollbar()
            return
        focus_width, focus_height = self._focus_dimensions()
        if (self.winfo_width(), self.winfo_height()) != (focus_width, focus_height):
            self._set_widget_geometry(
                focus_width, focus_height,
                self.winfo_x(), self.winfo_y(),
            )
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
                # This control may have stayed hidden throughout a theme
                # change. Prepare it before its first native paint as well.
                self._retheme_widget_tree(self._container._scrollbar)
                self._container._scrollbar.grid()
        except tk.TclError:
            # The widget may be closing while a deferred layout pass runs.
            pass

    def _set_widget_geometry(
        self, width: int, height: int, x: int, y: int,
        *, anchor: tuple[int, int] | None = None,
    ) -> None:
        """Apply geometry while keeping an expanded borderless widget reachable."""
        safe_x, safe_y = self._clamp_window_position(width, height, x, y, anchor=anchor)
        self._apply_absolute_geometry(width, height, safe_x, safe_y)
        self._schedule_widget_rounding()

    def _set_resized_widget_geometry(self, width: int, height: int, x: int, y: int) -> None:
        """Set physical geometry without CTk's transient scale-time size lock."""
        safe_x, safe_y = self._clamp_window_position(width, height, x, y)
        # CTk.geometry() converts through its window-scaling state. During a
        # live scale that conversion can pin the shell to its previous size.
        # Tk.geometry() works with the actual pixels already measured above.
        self._apply_absolute_geometry(width, height, safe_x, safe_y)
        self._schedule_widget_rounding()

    def _layout_navigation(self, width: int) -> None:
        columns = 1 if self._wide_shell else (3 if width < 550 else 6)
        if columns == self._navigation_columns:
            return
        self._navigation_columns = columns
        if columns == 1:
            self._nav_heading.grid(row=0, column=0, sticky="ew", padx=12, pady=(16, 10))
        else:
            self._nav_heading.grid_forget()
        for index in range(6):
            self._navigation.grid_columnconfigure(index, weight=1 if index < columns else 0)
        for index, button in enumerate(self._page_buttons.values()):
            button.grid_forget()
            button.configure(
                height=42 if columns == 1 else 34,
                font=("Segoe UI", 12 if columns == 1 else 11, "bold"),
            )
            button.grid(row=index // columns + (1 if columns == 1 else 0),
                        column=index % columns, sticky="ew",
                        padx=8 if columns == 1 else 2, pady=3 if columns == 1 else 2)

    def _bind_responsive_wraps(self, parent: tk.Misc) -> None:
        """Track explanatory labels whose wrapping follows the content column."""
        for widget in parent.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                try:
                    wrapped = int(widget.cget("wraplength")) > 0
                except (tk.TclError, TypeError, ValueError):
                    wrapped = False
                if wrapped:
                    self._responsive_labels.append(widget)
            self._bind_responsive_wraps(widget)

    def _schedule_responsive_wraps(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self or (
            event.width == self._last_responsive_width
            and event.height == self._last_responsive_height
        ):
            return
        self._last_responsive_width = event.width
        self._last_responsive_height = event.height
        if self._resize_active:
            return
        if self._responsive_wrap_after is not None:
            self.after_cancel(self._responsive_wrap_after)
        self._responsive_wrap_after = self.after(80, self._update_responsive_wraps)

    def _update_responsive_wraps(self) -> None:
        self._responsive_wrap_after = None
        if self._resize_active:
            return
        self._update_shell_layout()
        for label in self._responsive_labels:
            if not label.winfo_exists():
                continue
            available = label.master.winfo_width() - 28
            if available >= 160 and abs(int(label.cget("wraplength")) - available) >= 24:
                label.configure(wraplength=available)

    def _layout_settings_navigation(self, width: int) -> None:
        columns = 3 if width < 600 else min(len(self._settings_section_buttons), 6)
        if columns == self._settings_navigation_columns:
            return
        self._settings_navigation_columns = columns
        for index in range(len(self._settings_section_buttons)):
            self._settings_navigation.grid_columnconfigure(index, weight=1 if index < columns else 0)
        for index, button in enumerate(self._settings_section_buttons.values()):
            button.grid_forget()
            button.grid(row=index // columns, column=index % columns, sticky="ew", padx=2, pady=2)

    def _layout_theme_choices(self, width: int) -> None:
        if not hasattr(self, "_theme_choice_buttons"):
            return
        columns = max(1, min(3, int(max(1, width) // 180)))
        if columns == getattr(self, "_theme_choice_columns", None):
            return
        self._theme_choice_columns = columns
        for index, button in enumerate(self._theme_choice_buttons.values()):
            button.grid_forget()
            button.grid(row=index // columns, column=index % columns, sticky="ew", padx=3, pady=3)
        for column in range(4):
            self._theme_choice_grid.grid_columnconfigure(column, weight=1 if column < columns else 0)

    @staticmethod
    def _theme_detail_text(theme_name: str) -> str:
        if theme_name == "machine_red":
            return "Machine Red usa #FF2E3A nos destaques e Glacier Blue #DBF6FF nos textos azulados."
        return f"Tema selecionado: {THEME_LABELS.get(theme_name, THEME_LABELS[DEFAULT_THEME])}."

    def _refresh_theme_choices(self) -> None:
        if hasattr(self, "_theme_choice_detail"):
            self._theme_choice_detail.configure(text=self._theme_detail_text(self._theme_name))
        for theme_name, button in getattr(self, "_theme_choice_buttons", {}).items():
            palette = THEMES[theme_name]
            selected = theme_name == self._theme_name
            button.configure(
                fg_color=palette["surface_button"],
                hover_color=palette["surface_button_hover"],
                border_color=palette["accent"] if selected else palette["border"],
                border_width=2 if selected else 1,
                text_color=palette["text"],
            )

    def _retheme_widget_tree(self, widget: tk.Misc, *, visible_only: bool = False, force: bool = False) -> None:
        """Apply stable bindings through the public composite-widget API.

        CTk owns its internal Canvas, Label, Entry and Text. Recoloring those
        directly corrupts anti-aliased shapes and transparent backgrounds.
        Batch each public control's options so it only redraws once here.
        """
        if visible_only and widget is not self and not widget.winfo_ismapped():
            return
        custom_options = (
            "bg_color", "fg_color", "text_color", "hover_color", "border_color", "button_color",
            "button_hover_color", "dropdown_fg_color", "dropdown_text_color", "dropdown_hover_color",
            "placeholder_text_color", "progress_color", "scrollbar_fg_color",
            "scrollbar_button_color", "scrollbar_button_hover_color", "checkmark_color",
            "text_color_disabled", "selected_color", "selected_hover_color",
            "unselected_color", "unselected_hover_color",
        )
        if hasattr(widget, "_apply_appearance_mode") and (force or getattr(widget, "_voice_notes_theme", None) != self._theme_name):
            changes = {}
            for option in custom_options:
                try:
                    value = widget.cget(option)
                except (tk.TclError, ValueError, AttributeError):
                    continue
                if isinstance(value, ThemeColor):
                    target = value.for_theme(self._theme_name)
                    if force or target != value:
                        changes[option] = target
            if isinstance(widget, ctk.CTkScrollableFrame):
                # Its native scrolling canvas is not a CTk child and does not
                # receive inherited bg_color changes from the wrapper frame.
                changes.setdefault("fg_color", widget.cget("fg_color"))
            if changes:
                widget.configure(**changes)
            widget._voice_notes_theme = self._theme_name
        if isinstance(widget, ctk.CTkBaseClass):
            self._sync_native_theme_background(widget)
        if hasattr(widget, "_apply_appearance_mode"):
            if not isinstance(widget, (ctk.CTk, ctk.CTkToplevel, ctk.CTkFrame, ctk.CTkScrollableFrame)):
                return
        # A scrollable frame has a native Canvas between its wrapper and its
        # public content frame; traverse that bridge without painting it.
        for child in widget.winfo_children():
            self._retheme_widget_tree(child, visible_only=visible_only, force=force)

    @staticmethod
    def _sync_native_theme_background(widget: ctk.CTkBaseClass) -> None:
        """Keep the native backing frame ready for its first paint on Map.

        CTk updates its canvas and labels for bg_color but deliberately leaves
        the native Frame background at its construction color. During mapping
        or font/layout changes that old frame is exposed before the canvas.
        Only synchronize the composite's backing frame; its internal drawing
        children remain entirely owned by CTk.
        """
        color = widget._apply_appearance_mode(widget.cget("bg_color"))
        if tk.Frame.cget(widget, "background").lower() != color.lower():
            tk.Frame.configure(widget, background=color)

    def _apply_page_theme(self, page: str) -> None:
        """Update a destination before showing it; hidden pages never block a switch."""
        if page == "settings":
            self._retheme_widget_tree(self._focus_settings_heading)
            self._retheme_widget_tree(self._settings_navigation)
            section = getattr(self, "_active_settings_section", "verification")
            self._retheme_widget_tree(self._settings_sections[section])
            if self._maximized:
                self._retheme_widget_tree(self._settings_context_panel)
            for child in self._settings_panel.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    self._retheme_widget_tree(child)
            # Update the card itself without visiting its hidden sections.
            self._settings_panel.configure(fg_color=_theme_color("#0C1423"))
            return
        focus_panels = {
            "record": self._focus_record_panel, "file": self._focus_file_panel,
            "library": self._focus_library_panel, "processing": self._focus_process_panel,
            "youtube": self._focus_youtube_panel,
        }
        if not self._maximized or page == "library":
            self._retheme_widget_tree(focus_panels[page])
        else:
            for widget, _options in self._page_layouts[page]:
                self._retheme_widget_tree(widget)

    def _refresh_theme_drawings(self) -> None:
        """Redraw app-owned canvases and editor tags from their original roles."""
        for canvas, original in (
            (self._eq_canvas, "#0C1423"),
            (self._compact_meter, "#101827"),
            (self._browser_canvas, "#0D1525"),
        ):
            canvas.configure(bg=_theme_color(original))
        self._redraw_eq()
        self._draw_browser_rows()
        if self.transcript_editor.winfo_exists():
            self._configure_markdown_tags()

    def _select_color_theme(self, theme_name: str) -> None:
        global _ACTIVE_THEME_NAME
        if theme_name not in THEMES or theme_name == self._theme_name:
            return
        try:
            save_color_theme(theme_name)
        except OSError as exc:
            messagebox.showerror("Não foi possível salvar", f"O tema não foi salvo nas preferências.\n\n{exc}")
            return
        self._hide_button_tooltip()
        self._theme_name = theme_name
        _ACTIVE_THEME_NAME = theme_name
        _COLORS.update(theme_colors(theme_name))
        configure_widget_defaults(ctk.ThemeManager.theme, theme_name)
        self._retheme_widget_tree(self, visible_only=True)
        self._refresh_theme_drawings()
        self._refresh_theme_choices()
        style = ttk.Style(self)
        style.configure("App.TFrame", background=_COLORS["bg"])
        style.configure("Panel.TLabelframe", background=_COLORS["surface"], foreground=_COLORS["text"], bordercolor=_COLORS["border"], relief="flat")
        style.configure("Panel.TLabelframe.Label", background=_COLORS["surface"], foreground=_COLORS["text"])
        style.configure("App.TRadiobutton", background=_COLORS["surface"], foreground=_COLORS["text"])
        style.map("App.TRadiobutton", background=[("active", _COLORS["surface"])], foreground=[("active", _COLORS["text"])])
        style.configure("Status.TLabel", background=_COLORS["bg"], foreground=_COLORS["text"])
        style.configure("Timer.TLabel", background=_COLORS["bg"], foreground=_COLORS["text"])
        style.configure("DiskWarn.TLabel", background=_COLORS["bg"], foreground=_COLORS["warning"])
        style.configure("PipelineInfo.TLabel", background=_COLORS["bg"], foreground=_COLORS["brand_muted"])
        style.configure("TEntry", fieldbackground=_COLORS["surface_alt"], foreground=_COLORS["text"], bordercolor=_COLORS["border"], insertcolor=_COLORS["text"])
        style.configure("TCombobox", fieldbackground=_COLORS["surface_alt"], background=_COLORS["surface_alt"], foreground=_COLORS["text"], arrowcolor=_COLORS["muted"], bordercolor=_COLORS["border"])
        style.map("TCombobox", fieldbackground=[("readonly", _COLORS["surface_alt"])], foreground=[("readonly", _COLORS["text"])])
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=_COLORS["surface_alt"], background=_COLORS["accent"], bordercolor=_COLORS["surface_alt"])

    def _show_page(self, page: str, *, refresh_data: bool = True) -> None:
        """Show one direct destination in the widget; pages never nest."""
        if page not in self._page_layouts:
            raise ValueError(f"Página desconhecida: {page}")
        if self._library_open and page != "library" and not self._close_transcript_editor():
            return
        self._ensure_page_layout(page)
        self._apply_page_theme(page)
        # The narrow recording layout has a fixed action bar. Other layouts
        # reserve room below the scroll canvas for the rounded window corners.
        bottom_inset = 4 if page == "record" and not self._use_inline_recording_actions() else 20
        self._container._parent_frame.pack_configure(pady=(0, bottom_inset))
        for layouts in self._page_layouts.values():
            for widget, _options in layouts:
                widget.pack_forget()
        self._focus_record_panel.pack_forget()
        self._focus_library_panel.pack_forget()
        self._focus_process_panel.pack_forget()
        if self._focus_text_tools_visible:
            self._focus_show_text_tools()
        self._focus_file_panel.pack_forget()
        self._focus_text_import_panel.pack_forget()
        self._focus_youtube_panel.pack_forget()
        self._focus_settings_heading.pack_forget()
        if page != "library":
            self._close_browser_audio()
        self._focus_text_tools_visible = False
        context_panels = (
            self._file_context_panel, self._youtube_context_panel,
            self._settings_context_panel,
        )
        desktop_context = {
            "file": self._file_context_panel,
            "youtube": self._youtube_context_panel,
            "settings": self._settings_context_panel,
        }.get(page) if self._desktop_layout else None

        if not self._maximized and page == "settings":
            self._focus_settings_heading.pack(fill=tk.X, padx=27, pady=(23, 0))
            self._settings_kicker.pack_forget()
            self._settings_description.pack_forget()
        elif self._maximized:
            if not self._settings_kicker.winfo_manager():
                self._settings_kicker.pack(fill=tk.X, padx=18, pady=(18, 2), before=self._settings_navigation)
            if not self._settings_description.winfo_manager():
                self._settings_description.pack(fill=tk.X, padx=18, pady=(0, 8), after=self._settings_kicker)
        if desktop_context is not None:
            desktop_context.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 20), pady=(12, 10))
        for widget, options in self._page_layouts[page]:
            if page == "library":
                continue
            if not self._maximized and page == "record":
                continue
            if not self._maximized and page in {"file", "library", "processing", "youtube"}:
                continue
            # Reserve a row between the two recording cards only when there is
            # actual device information to show.  An empty label previously
            # created an unexplained visual gap in the primary workflow.
            if widget is self.device_info_label and not self.device_info_text.get().strip():
                continue
            if widget in (self._inline_buttons, self._record_recent_panel) and not self._use_inline_recording_actions():
                continue
            if widget is self._buttons and self._use_inline_recording_actions():
                continue
            if widget in context_panels:
                continue
            if desktop_context is not None:
                widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 8), pady=(12, 10))
                continue
            widget.pack(**options)
        if not self._maximized and page == "record":
            self._sync_focus_stop_choice()
            self._focus_record_panel.pack(fill=tk.X, padx=27, pady=(23, 18))
        elif page == "library":
            if self._maximized:
                self._focus_library_panel.configure(height=max(650, self.winfo_height() - 140))
            self._focus_library_panel.pack(
                fill=tk.BOTH, expand=True,
                padx=20 if self._maximized else 11,
                pady=(12, 10) if self._maximized else (23, 10),
            )
            self._layout_browser()
            if not refresh_data:
                self._refresh_focus_library()
        elif not self._maximized and page == "processing":
            self._focus_process_panel.pack(fill=tk.BOTH, expand=True, padx=11, pady=(23, 10))
            if not refresh_data:
                self._refresh_focus_processes()
        elif not self._maximized and page == "file":
            self._focus_file_panel.pack(fill=tk.X, padx=27, pady=(23, 8))
        elif not self._maximized and page == "youtube":
            self._focus_youtube_panel.pack(fill=tk.X, padx=27, pady=(23, 8))
        # Destinations always open at their first field.  Without this reset a
        # tall previous page could leave a newly selected page scrolled to an
        # apparently empty lower section.
        self._container._parent_canvas.yview_moveto(0)
        self.after_idle(lambda: self._container._parent_canvas.yview_moveto(0))
        self.after(80, lambda: self._container._parent_canvas.yview_moveto(0))

        page_titles = {
            "record": ("Gravar", "Configure a captura e inicie quando estiver pronto."),
            "file": ("Arquivo", "Importe uma gravação já existente"),
            "youtube": ("YouTube", "Importe um vídeo autorizado para transcrever"),
            "library": ("Biblioteca", "Encontre, revise e retome seus resultados"),
            "processing": ("Processamentos", "Acompanhe a fila e continue usando o aplicativo"),
            "settings": ("Ajustes", "Defina como o Voice Notes deve processar"),
        }
        title, hint = page_titles[page]
        self._header_title.configure(text=title)
        self._header_drag_hint.configure(text=hint)
        self._apply_focus_chrome()
        for key, button in self._page_buttons.items():
            active = key == page
            button.configure(
                fg_color=(_theme_color("#354A6E") if not self._maximized else _theme_color("#314B70")) if active else "transparent",
                text_color=_COLORS["text"] if active else _COLORS["muted"],
            )
        self._current_page = page
        self._settings_open = page == "settings"
        self._youtube_open = page == "youtube"
        self._library_open = page == "library"
        if page == "library" and refresh_data:
            self._refresh_library()
        if page == "processing" and refresh_data:
            self._refresh_processing_page()
        if page == "settings" and refresh_data:
            self._show_settings_section(getattr(self, "_active_settings_section", "verification"))
        self._apply_desktop_typography()
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
        self._retheme_widget_tree(self._settings_sections[section])
        for panel in self._settings_sections.values():
            panel.pack_forget()
        self._settings_sections[section].pack(fill=tk.X, padx=0, pady=(0, 4))
        for key, button in self._settings_section_buttons.items():
            active = key == section
            button.configure(
                fg_color=_theme_color("#314B70") if active else "transparent",
                text_color=_COLORS["text"] if active else _COLORS["muted"],
            )
        self._active_settings_section = section
        if getattr(self, "_current_page", None) == "settings":
            self._apply_desktop_typography()
            self.after_idle(self._apply_page_minimum)

    def _toggle_api_provider_form(self) -> None:
        """Open a blank create form without mixing it with saved providers."""
        if self._api_provider_open:
            self._hide_api_provider_form()
            return
        from record_transcript_resume.api_provider import ApiProviderConfig

        self._editing_api_provider_id = None
        self._fill_api_provider_form(ApiProviderConfig())
        self.api_form_title.configure(text="NOVO PROVIDER POR TOKEN")
        self.api_save_button.configure(text="Salvar provider")
        self.api_token_hint.set("O token será guardado no Cofre de Credenciais do Windows.")
        self._show_api_provider_form()

    def _show_api_provider_form(self) -> None:
        if not self._api_provider_open:
            self.api_card.pack(fill=tk.X, padx=14, pady=(0, 10), before=self._api_form_anchor)
            self._api_provider_open = True
        self.new_provider_button.configure(text="− Ocultar novo provider")
        self.after_idle(self._apply_page_minimum)

    def _hide_api_provider_form(self) -> None:
        self.api_card.pack_forget()
        self._api_provider_open = False
        self.new_provider_button.configure(text="+ Novo Provider")
        self.after_idle(self._apply_page_minimum)

    def _fill_api_provider_form(self, config: object) -> None:
        self.api_provider_name.set(str(getattr(config, "name", "Minha API")))
        self.api_protocol.set(str(getattr(config, "protocol", "openai_compatible")))
        self.api_base_url.set(str(getattr(config, "base_url", "https://api.openai.com/v1")))
        self.api_model.set(str(getattr(config, "model", "gpt-4.1-mini")))
        self.api_transcription_model.set(str(getattr(config, "transcription_model", "whisper-1")))
        self.api_auth_header.set(str(getattr(config, "auth_header", "Authorization")))
        self.api_auth_prefix.set(str(getattr(config, "auth_prefix", "Bearer ")))
        self.api_response_path.set(str(getattr(config, "response_path", "choices.0.message.content")))
        self.api_request_template.delete("1.0", tk.END)
        self.api_request_template.insert("1.0", str(getattr(config, "request_template", self.api_request_template_default)))
        self.api_token.set("")

    def _edit_api_provider(self, provider_id: str) -> None:
        config = self._api_provider_for_id(provider_id)
        if config is None:
            messagebox.showerror("Provider indisponível", "Esse provider não foi encontrado. Atualize a lista e tente novamente.")
            return
        self._editing_api_provider_id = provider_id
        self._fill_api_provider_form(config)
        self.api_form_title.configure(text=f"EDITAR PROVIDER · {config.name}")
        self.api_save_button.configure(text="Salvar alterações")
        self.api_token_hint.set(
            "Token salvo no Cofre de Credenciais. Deixe o campo vazio para mantê-lo ou informe outro para substituir."
            if self._api_provider_has_token(provider_id)
            else "Este provider ainda não possui token. Informe um token para poder utilizá-lo."
        )
        self._show_api_provider_form()

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
        is_new = self._editing_api_provider_id is None
        token_changed = bool(self.api_token.get().strip())
        if is_new and not token_changed:
            messagebox.showerror("Token ausente", "Cole o token da API antes de salvar o provider.")
            return
        try:
            saved = save_config(
                ApiProviderConfig(
                    id=self._editing_api_provider_id or "",
                    name=self.api_provider_name.get().strip() or "Minha API",
                    protocol=self.api_protocol.get(),
                    base_url=self.api_base_url.get().strip(),
                    model=self.api_model.get().strip(),
                    transcription_model=self.api_transcription_model.get().strip() or "whisper-1",
                    auth_header=self.api_auth_header.get().strip(),
                    auth_prefix=self.api_auth_prefix.get(),
                    request_template=self.api_request_template.get("1.0", "end").strip(),
                    response_path=self.api_response_path.get().strip(),
                ),
                self.api_token.get() or None,
            )
        except Exception as exc:
            messagebox.showerror("Não foi possível salvar", str(exc))
            return
        self._refresh_api_provider_choices()
        selected_label = next(
            (label for label, code in self._api_provider_labels.items() if code == f"api:{saved.id}"),
            "Codex",
        )
        self.summary_provider.set(selected_label)
        self.api_token.set("")
        self._hide_api_provider_form()
        messagebox.showinfo(
            "Provider salvo",
            "Provider salvo. O token foi guardado no Cofre de Credenciais do Windows." if token_changed
            else "Provider atualizado. O token salvo foi mantido no Cofre de Credenciais do Windows.",
        )

    def _toggle_library(self) -> None:
        self._show_page("library")

    def _show_processing_page(self) -> None:
        self._show_page("processing")

    def _refresh_recording_recent(self, items: list[LibraryItem] | None = None) -> None:
        """Show useful library shortcuts in the room available on large screens."""
        if not hasattr(self, "_record_recent_list"):
            return
        if items is None:
            items = discover_recordings(
                Path(self.output_dir.get() or default_output_dir()), self._library_metadata,
            )
        signature = tuple(items[:3])
        if signature == self._recent_render_signature:
            return
        self._recent_render_signature = signature
        for child in self._record_recent_list.winfo_children():
            child.destroy()
        if not items:
            empty = ctk.CTkFrame(
                self._record_recent_list, fg_color=_theme_color("#162239"), corner_radius=10, height=176,
            )
            empty.pack(fill=tk.X)
            empty.pack_propagate(False)
            empty_content = ctk.CTkFrame(empty, fg_color="transparent")
            empty_content.pack(fill=tk.X, expand=True, padx=18)
            ctk.CTkLabel(
                empty_content, text="Ainda não há gravações nesta pasta.",
                font=("Segoe UI", 14, "bold"), text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkLabel(
                empty_content, text="Inicie uma gravação acima ou importe um áudio existente.",
                font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, pady=(2, 10))
            ctk.CTkButton(
                empty_content, text="Importar áudio", command=self._show_file_import,
                width=114, height=34, corner_radius=8, fg_color=_theme_color("#263550"),
                hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                font=("Segoe UI", 12, "bold"),
            ).pack(anchor="w")
            return
        for index, item in enumerate(items[:3]):
            row = ctk.CTkFrame(self._record_recent_list, fg_color=_theme_color("#162239"), corner_radius=9)
            row.pack(fill=tk.X, pady=(0, 6) if index < min(len(items), 3) - 1 else 0)
            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=14, pady=5)
            title = item.title.strip() or item.folder.name
            if len(title) > 68:
                title = f"{title[:67].rstrip()}…"
            ctk.CTkLabel(
                details, text=title, font=("Segoe UI", 13, "bold"),
                text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X)
            state = (
                "Resumo pronto" if item.summary_available
                else "Transcrição pronta" if item.transcript_path is not None
                else "Áudio salvo"
            )
            ctk.CTkLabel(
                details, text=f"{item.sort_at:%d/%m às %H:%M}  ·  {state}",
                font=("Segoe UI", 11), text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X)
            ctk.CTkButton(
                row, text="Abrir", command=lambda selected=item: self._open_recent_recording(selected),
                width=72, height=32, corner_radius=8, fg_color=_theme_color("#263550"),
                hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                font=("Segoe UI", 11, "bold"),
            ).pack(side=tk.RIGHT, padx=14)

    def _open_recent_recording(self, item: LibraryItem) -> None:
        root = Path(self.library_dir.get() or default_output_dir()).expanduser()
        target = item.folder if item.folder != root else (
            item.mp3_path or item.transcript_path or item.summary_path or item.folder
        )
        self._browser_directory = target.parent if target.parent.is_dir() else root
        self._browser_selected = None
        self._browser_search.set("")
        self._show_page("library")
        for index, entry in enumerate(self._browser_visible_entries):
            if entry.path == target:
                self._browser_selected = entry
                self._browser_select()
                self._browser_canvas.yview_moveto(index / max(1, len(self._browser_visible_entries)))
                self._draw_browser_rows()
                break

    def _refresh_library(self) -> None:
        if hasattr(self, "_browser_canvas") and self._current_page == "library":
            self._refresh_focus_library()
        library_root = Path(self.library_dir.get() or default_output_dir()).expanduser()
        self._library_folder_available = library_root.is_dir()
        self._library_items = discover_recordings(library_root, self._library_metadata)
        self._library_tag_values = [
            "Todas as etiquetas",
            *sorted({tag for item in self._library_items for tag in item.tags}, key=str.casefold),
        ]
        if self.library_tag_filter.get() not in self._library_tag_values:
            self.library_tag_filter.set("Todas as etiquetas")
        self.library_tag_selector.configure(state=tk.NORMAL if len(self._library_tag_values) > 1 else tk.DISABLED)
        self._refresh_recording_recent(self._library_items)
        pending = [job for job in self._job_store.list() if job.status in {"queued", "running", "failed", "needs_attention", "warning"}]
        resumable = [job for job in pending if job.status in {"queued", "failed", "needs_attention"}]
        if not pending:
            self.queue_hint.set("Fila vazia")
            self.retry_queue_button.configure(state=tk.DISABLED)
        else:
            failed = sum(job.status in {"failed", "needs_attention"} for job in pending)
            warnings = sum(job.status == "warning" for job in pending)
            running = sum(job.status == "running" for job in pending)
            queued = sum(job.status == "queued" for job in pending)
            parts = []
            if running:
                parts.append(f"{running} processando")
            if queued:
                parts.append(f"{queued} na fila")
            if failed:
                parts.append(f"{failed} exigem atenção")
            if warnings:
                parts.append(f"{warnings} com aviso")
            self.queue_hint.set(" · ".join(parts))
            self.retry_queue_button.configure(state=tk.NORMAL if resumable else tk.DISABLED)

    def _refresh_focus_library(self) -> None:
        root = Path(self.library_dir.get() or default_output_dir()).expanduser()
        if self._browser_directory is None or not self._browser_directory.is_dir():
            self._browser_directory = root
            self._browser_history.clear()
        directory = self._browser_directory
        self._browser_entries = browse_directory(directory, self._library_metadata)
        self._browser_full_path.set(str(directory))
        self._browser_back_button.configure(state=tk.NORMAL if self._browser_history else tk.DISABLED)
        self._browser_up_button.configure(state=tk.NORMAL if directory.parent != directory else tk.DISABLED)
        self._render_browser_breadcrumb(directory)
        self._render_focus_browser()
        if not directory.is_dir():
            self._browser_preview_title.set("Pasta indisponível")
            self._browser_preview_body.set("Escolha outra pasta para continuar.")

    def _render_browser_breadcrumb(self, directory: Path) -> None:
        frame = self._browser_breadcrumb
        for child in frame.winfo_children():
            child.destroy()
        root = Path(self.library_dir.get() or default_output_dir()).expanduser()
        base = root.parent
        try:
            parts = directory.relative_to(base).parts
        except ValueError:
            base = directory.parent
            parts = (directory.name,)
        path = base
        ctk.CTkButton(frame, text=base.name or str(base), command=lambda folder=base: self._browser_navigate(folder),
                      width=72, height=28, fg_color="transparent", hover_color=_theme_color("#263550"),
                      anchor="w").pack(side=tk.LEFT, padx=(8, 0), pady=5)
        for part in parts:
            path = path / part
            ctk.CTkLabel(frame, text="›", width=18, text_color=_COLORS["muted"]).pack(side=tk.LEFT)
            ctk.CTkButton(frame, text=part[:24] + ("…" if len(part) > 24 else ""),
                          command=lambda folder=path: self._browser_navigate(folder),
                          width=max(70, min(200, len(part) * 8 + 14)), height=28,
                          fg_color="transparent", hover_color=_theme_color("#263550"),
                          anchor="w").pack(side=tk.LEFT, pady=5)

    def _render_focus_browser(self) -> None:
        if not hasattr(self, "_browser_canvas"):
            return
        selected_path = self._browser_selected.path if self._browser_selected else None
        query = self._browser_search.get().strip().casefold()
        entries = [entry for entry in self._browser_entries
                   if not query or query in entry.title.casefold() or query in entry.path.name.casefold()]
        order = self._browser_sort.get()
        if order == "Nome Z–A":
            entries.sort(key=lambda entry: entry.title.casefold(), reverse=True)
        elif order == "Mais recentes":
            entries.sort(key=lambda entry: entry.modified_at, reverse=True)
        elif order == "Mais antigos":
            entries.sort(key=lambda entry: entry.modified_at)
        else:
            entries.sort(key=lambda entry: entry.title.casefold())
        self._browser_visible_entries = entries
        if selected_path is None or all(entry.path != selected_path for entry in entries):
            self._browser_selected = None
            self._browser_preview_title.set("Selecione um arquivo ou pasta")
            self._browser_preview_body.set("Abra uma pasta com dois cliques para ver seu conteúdo.")
            self._browser_preview_details.set(
                "Navegue pelas pastas e gravações desta pasta. Selecione um item para ver seus arquivos e as ações disponíveis."
            )
            self._browser_open_button.configure(text="Abrir", state=tk.DISABLED)
            self._browser_process_button.pack_forget()
            self._browser_audio_player.pack_forget()
            self._close_browser_audio()
            self._browser_audio_player.master.configure(height=108)
            for button in (self._browser_favorite_button, self._browser_metadata_button,
                           self._browser_docx_button, self._browser_pdf_button):
                button.pack_forget()
        self._draw_browser_rows()
        if query:
            self._browser_count.set(
                f"{len(entries)} de {len(self._browser_entries)} itens encontrados nesta pasta"
            )
        else:
            folders = sum(entry.kind in {"folder", "recording", "text_record"} for entry in entries)
            recordings = sum(entry.kind == "recording" for entry in entries)
            audio_files = sum(entry.kind == "audio" for entry in entries)
            documents = sum(entry.kind == "document" for entry in entries)
            parts = [f"{len(entries)} itens nesta pasta"]
            if folders:
                folder_label = f"{folders} {'pasta' if folders == 1 else 'pastas'}"
                if recordings:
                    folder_label += f" ({recordings} {'gravação' if recordings == 1 else 'gravações'})"
                parts.append(folder_label)
            if audio_files:
                parts.append(f"{audio_files} {'áudio' if audio_files == 1 else 'áudios'}")
            if documents:
                parts.append(f"{documents} {'documento' if documents == 1 else 'documentos'}")
            self._browser_count.set("  ·  ".join(parts))
        self._browser_update_folder_actions()

    def _layout_browser_heading(self, event: tk.Event[tk.Misc]) -> None:
        width = event.width
        for label, x in zip(self._browser_heading_labels, (
            10, int(width * .46), int(width * .65), int(width * .84),
        )):
            label.place(x=x, y=4)

    def _browser_canvas_scrollbar(self, *args: object) -> None:
        self._browser_canvas.yview(*args)
        self._draw_browser_rows()

    def _browser_canvas_scroll(self, event: tk.Event[tk.Misc]) -> None:
        self._browser_canvas.yview_scroll(-int(event.delta / 120), "units")
        self._draw_browser_rows()

    def _browser_canvas_select(self, event: tk.Event[tk.Misc]) -> None:
        index = int(self._browser_canvas.canvasy(event.y) // 70)
        if 0 <= index < len(self._browser_visible_entries):
            self._browser_selected = self._browser_visible_entries[index]
            self._browser_canvas.focus_set()
            self._draw_browser_rows()
            self._browser_select()

    def _browser_canvas_open(self, event: tk.Event[tk.Misc]) -> None:
        self._browser_canvas_select(event)
        self._browser_open()

    def _draw_browser_rows(self) -> None:
        canvas = self._browser_canvas
        entries = getattr(self, "_browser_visible_entries", ())
        width = max(1, canvas.winfo_width())
        row_height = 70
        canvas.configure(scrollregion=(0, 0, width, max(len(entries) * row_height, canvas.winfo_height())))
        top = canvas.canvasy(0)
        bottom = top + canvas.winfo_height()
        canvas.delete("all")
        if not entries:
            message = ("Nenhum item encontrado nesta pasta."
                       if self._browser_search.get().strip() else "Esta pasta está vazia.")
            canvas.create_text(14, 25, anchor="nw", text=message,
                               fill=_theme_color("#A9B9D1"), font=("Segoe UI", 11))
            return
        icons = {"folder": "📁", "recording": "🎙", "text_record": "▤",
                 "audio": "♫", "document": "▤", "file": "▣"}
        types = {"folder": "Pasta", "recording": "Gravação", "text_record": "Texto",
                 "audio": "Áudio", "document": "Documento", "file": "Arquivo"}
        subtitles = {
            "folder": "Pasta neste diretório", "recording": "Áudio e documentos",
            "text_record": "Transcrição importada", "audio": "Arquivo de áudio",
            "document": "Documento desta gravação", "file": "Arquivo neste diretório",
        }
        first = max(0, int(top // row_height) - 1)
        last = min(len(entries), int(bottom // row_height) + 2)
        for index in range(first, last):
            entry = entries[index]
            y = index * row_height
            selected = self._browser_selected is not None and entry.path == self._browser_selected.path
            canvas.create_rectangle(
                2, y + 3, width - 3, y + row_height - 3,
                fill=_theme_color("#213251") if selected else _theme_color("#0D1525"),
                outline=_theme_color("#8170E6") if selected else _theme_color("#293951"),
                width=1,
            )
            icon_color = _theme_color("#363768") if entry.kind in {"folder", "recording"} else _theme_color("#294660")
            canvas.create_rectangle(12, y + 17, 47, y + 52, fill=icon_color, outline="")
            canvas.create_text(29, y + 34, text=icons.get(entry.kind, "▣"),
                               fill=_theme_color("#DAD3FF"), font=("Segoe UI Emoji", 15))
            title = entry.title.strip() or entry.path.name
            title_limit = max(26, min(74, int((width * .46 - 75) / 7)))
            if len(title) > title_limit:
                title = title[:title_limit - 1].rstrip() + "…"
            canvas.create_text(59, y + 24, text=title, anchor="w",
                               fill=_theme_color("#F1F5FB"), font=("Segoe UI", 11, "bold"))
            canvas.create_text(59, y + 46, text=subtitles.get(entry.kind, "Arquivo"), anchor="w",
                               fill=_theme_color("#A9B9D1"), font=("Segoe UI", 9))
            type_label = types.get(entry.kind, "Arquivo")
            if entry.kind == "audio":
                type_label = f"Áudio {entry.path.suffix.lstrip('.').upper()}"
            canvas.create_text(int(width * .46), y + 35, text=type_label, anchor="w",
                               fill=_theme_color("#CAD6E9"), font=("Segoe UI", 10))
            detail = entry.detail or "—"
            detail_limit = max(16, min(38, int((width * .19 - 10) / 7)))
            if len(detail) > detail_limit:
                detail = detail[:detail_limit - 1].rstrip() + "…"
            canvas.create_text(int(width * .65), y + 35, text=detail, anchor="w",
                               fill=_theme_color("#CAD6E9"), font=("Segoe UI", 10))
            canvas.create_text(int(width * .84), y + 35,
                               text=entry.modified_at.strftime("%d/%m/%Y"), anchor="w",
                               fill=_theme_color("#A9B9D1"), font=("Segoe UI", 10))

    def _browser_select(self, _event: object = None) -> None:
        entry = self._browser_selected
        if entry is None:
            return
        self._browser_open_button.configure(state=tk.NORMAL)
        self._browser_preview_title.set(entry.title)
        self._browser_preview_body.set(
            f"{entry.detail or entry.kind.title()}  ·  {entry.path.name}"
        )
        self._browser_preview_details.set(self._browser_entry_details(entry))
        self._browser_open_button.configure(
            text="Abrir pasta" if entry.kind in {"folder", "recording", "text_record"} else
                 "Abrir no player" if entry.kind == "audio" else "Abrir documento" if entry.kind == "document" else "Abrir arquivo"
        )
        self._browser_process_button.pack_forget()
        self._browser_audio_player.pack_forget()
        if entry.kind == "audio":
            if self._browser_audio_path != entry.path:
                self._close_browser_audio()
            self._browser_audio_player.pack(fill=tk.X, pady=(7, 0), before=self._browser_open_button.master)
            self._browser_audio_player.master.configure(height=150)
        else:
            self._close_browser_audio()
            self._browser_audio_player.master.configure(height=108)
        for button in (self._browser_favorite_button, self._browser_metadata_button,
                       self._browser_docx_button, self._browser_pdf_button):
            button.pack_forget()
        if entry.kind in {"recording", "text_record"}:
            key = self._browser_metadata_key(entry)
            data = self._library_metadata.load().get(str(key.resolve()).casefold(), {})
            favorite = bool(data.get("favorite", False)) if isinstance(data, dict) else False
            self._browser_favorite_button.configure(text="★ Favorito" if favorite else "☆ Favoritar")
            self._browser_favorite_button.pack(side=tk.LEFT, padx=(0, 7))
            self._browser_metadata_button.pack(side=tk.LEFT)
        if entry.kind == "document" and entry.path.suffix.casefold() == ".md":
            self._browser_docx_button.pack(side=tk.LEFT, padx=(0, 7))
            self._browser_pdf_button.pack(side=tk.LEFT)
        if entry.kind == "audio" and not (entry.path.parent / "transcription.md").is_file():
            self._browser_process_button.configure(text="Processar áudio")
            self._browser_process_button.pack(side=tk.RIGHT, padx=(0, 7))
        elif entry.kind == "document" and entry.path.name.casefold() == "transcription.md":
            self._browser_process_button.configure(text="Gerar resumo")
            self._browser_process_button.pack(side=tk.RIGHT, padx=(0, 7))
        self._browser_update_folder_actions()

    @staticmethod
    def _browser_entry_details(entry: BrowserEntry) -> str:
        details = [f"Modificado em {entry.modified_at:%d/%m/%Y às %H:%M}"]
        if entry.kind in {"folder", "recording", "text_record"}:
            try:
                children = sorted(entry.path.iterdir(), key=lambda path: path.name.casefold())
            except OSError:
                children = []
            if children:
                details.append("\nConteúdo desta pasta")
                details.extend(f"• {path.name}" for path in children[:8])
                if len(children) > 8:
                    details.append(f"• e mais {len(children) - 8} itens")
            else:
                details.append("\nEsta pasta está vazia.")
        elif entry.kind == "audio":
            details.append("\nSelecione o controle de reprodução para ouvir este áudio.")
        elif entry.kind == "document":
            details.append("\nAbra este documento para ler ou editar seu conteúdo.")
        return "\n".join(details)

    def _browser_update_folder_actions(self) -> None:
        can_manage = self._browser_manage_target() is not None
        for button in (self._browser_move_button, self._browser_rename_button):
            button.configure(state=tk.NORMAL if can_manage else tk.DISABLED)

    def _browser_navigate(self, directory: Path, *, remember: bool = True) -> None:
        if not directory.is_dir():
            messagebox.showerror("Pasta indisponível", f"Não foi possível abrir:\n{directory}", parent=self)
            return
        if remember and self._browser_directory is not None:
            self._browser_history.append(self._browser_directory)
        self._close_browser_audio()
        self._browser_directory = directory
        self._browser_selected = None
        self._browser_search.set("")
        self._refresh_focus_library()

    def _browser_back(self) -> None:
        if self._browser_history:
            self._browser_navigate(self._browser_history.pop(), remember=False)

    def _browser_up(self) -> None:
        directory = self._browser_directory
        if directory is not None and directory.parent != directory:
            self._browser_navigate(directory.parent)

    def _browser_open(self, _event: object = None) -> None:
        entry = self._browser_selected
        if entry is None:
            return
        if entry.kind in {"folder", "recording", "text_record"}:
            self._browser_navigate(entry.path)
        elif entry.kind == "document" and entry.path.suffix.casefold() in {".md", ".txt"}:
            self._open_library_document(
                entry.path, f"DOCUMENTO · {entry.path.name}",
                is_transcript=entry.path.name.casefold() == "transcription.md",
            )
        else:
            try:
                os.startfile(str(entry.path))
            except (AttributeError, OSError) as exc:
                messagebox.showerror("Não foi possível abrir", str(exc), parent=self)

    @staticmethod
    def _browser_mci(command: str) -> str:
        import ctypes

        winmm = ctypes.WinDLL("winmm", use_last_error=True)
        call = winmm.mciSendStringW
        call.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p)
        call.restype = ctypes.c_uint
        answer = ctypes.create_unicode_buffer(256)
        code = call(command, answer, len(answer), None)
        if code:
            error = ctypes.create_unicode_buffer(256)
            winmm.mciGetErrorStringW(code, error, len(error))
            raise OSError(error.value or f"Erro de reprodução {code}")
        return answer.value

    @staticmethod
    def _browser_time_label(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _close_browser_audio(self) -> None:
        if getattr(self, "_browser_audio_tick", None) is not None:
            self.after_cancel(self._browser_audio_tick)
            self._browser_audio_tick = None
        if getattr(self, "_browser_seek_after", None) is not None:
            self.after_cancel(self._browser_seek_after)
            self._browser_seek_after = None
        if getattr(self, "_browser_audio_path", None) is not None and sys.platform == "win32":
            try:
                self._browser_mci("close vn_browser_preview")
            except OSError:
                pass
        self._browser_audio_path = None
        self._browser_audio_duration = 0
        self._browser_audio_playing = False
        if hasattr(self, "_browser_audio_slider"):
            self._browser_slider_updating = True
            self._browser_audio_slider.set(0)
            self._browser_slider_updating = False
            self._browser_audio_time.set("00:00 / 00:00")
            self._browser_play_button.configure(text=_PLAYER_PLAY_ICON)

    def _browser_toggle_audio(self) -> None:
        entry = self._browser_selected
        if entry is None or entry.kind != "audio":
            return
        if sys.platform != "win32":
            self._browser_open()
            return
        try:
            if self._browser_audio_path != entry.path:
                self._close_browser_audio()
                media_type = "waveaudio" if entry.path.suffix.casefold() == ".wav" else "mpegvideo"
                try:
                    self._browser_mci(f'open "{entry.path}" type {media_type} alias vn_browser_preview')
                except OSError:
                    if media_type != "waveaudio":
                        raise
                    # The legacy WAV driver rejects some long paths.
                    # The multimedia driver accepts the same WAV
                    # without moving or renaming the user's audio file.
                    self._browser_mci(f'open "{entry.path}" type mpegvideo alias vn_browser_preview')
                self._browser_audio_path = entry.path
                self._browser_mci("set vn_browser_preview time format milliseconds")
                self._browser_audio_duration = int(self._browser_mci("status vn_browser_preview length"))
            if self._browser_audio_playing:
                self._browser_mci("pause vn_browser_preview")
                self._browser_audio_playing = False
                self._browser_play_button.configure(text=_PLAYER_PLAY_ICON)
            else:
                position = int(self._browser_mci("status vn_browser_preview position"))
                if self._browser_audio_duration and position >= self._browser_audio_duration - 100:
                    position = 0
                self._browser_mci(f"play vn_browser_preview from {position}")
                self._browser_audio_playing = True
                self._browser_play_button.configure(text=_PLAYER_PAUSE_ICON)
                self._tick_browser_audio()
        except (OSError, ValueError) as exc:
            self._close_browser_audio()
            messagebox.showerror("Prévia de áudio indisponível",
                                 f"Não foi possível reproduzir este formato no app.\n\n{exc}", parent=self)

    def _browser_seek_audio(self, fraction: float) -> None:
        if self._browser_slider_updating or self._browser_audio_path is None or self._browser_audio_duration <= 0:
            return
        if getattr(self, "_browser_seek_after", None) is not None:
            self.after_cancel(self._browser_seek_after)
        target = int(max(0.0, min(1.0, fraction)) * self._browser_audio_duration)
        self._browser_seek_after = self.after(130, lambda: self._apply_browser_audio_seek(target))

    def _apply_browser_audio_seek(self, milliseconds: int) -> None:
        self._browser_seek_after = None
        if self._browser_audio_path is None:
            return
        try:
            self._browser_mci(f"seek vn_browser_preview to {milliseconds}")
            if self._browser_audio_playing:
                self._browser_mci(f"play vn_browser_preview from {milliseconds}")
        except OSError:
            self._close_browser_audio()

    def _tick_browser_audio(self) -> None:
        self._browser_audio_tick = None
        if not self._browser_audio_playing or self._browser_audio_path is None:
            return
        try:
            position = int(self._browser_mci("status vn_browser_preview position"))
        except (OSError, ValueError):
            self._close_browser_audio()
            return
        duration = self._browser_audio_duration
        self._browser_slider_updating = True
        self._browser_audio_slider.set(min(1.0, position / duration) if duration else 0)
        self._browser_slider_updating = False
        self._browser_audio_time.set(
            f"{self._browser_time_label(position)} / {self._browser_time_label(duration)}"
        )
        if duration and position >= duration - 100:
            self._browser_audio_playing = False
            self._browser_play_button.configure(text=_PLAYER_PLAY_ICON)
            return
        self._browser_audio_tick = self.after(400, self._tick_browser_audio)

    def _browser_new_folder(self) -> None:
        directory = self._browser_directory
        if directory is None:
            return
        name = simpledialog.askstring("Nova pasta", "Nome da pasta:", parent=self)
        if name is None:
            return
        name = name.strip()
        if not name or name in {".", ".."} or any(char in name for char in '<>:"/\\|?*'):
            messagebox.showerror("Nome inválido", "Escolha um nome de pasta válido.", parent=self)
            return
        try:
            (directory / name).mkdir()
        except OSError as exc:
            messagebox.showerror("Não foi possível criar a pasta", str(exc), parent=self)
            return
        self._refresh_focus_library()

    def _browser_manage_target(self) -> Path | None:
        entry = self._browser_selected
        if entry and entry.kind in {"folder", "recording", "text_record"}:
            return entry.path
        directory = self._browser_directory
        root = Path(self.library_dir.get() or default_output_dir()).expanduser()
        return directory if directory is not None and directory != root else None

    def _browser_relocate(self, source: Path, destination: Path) -> None:
        if destination.exists():
            messagebox.showerror("Pasta existente", "Já existe uma pasta com esse nome no destino.", parent=self)
            return
        for job in self._job_store.list():
            if job.status not in {"queued", "running"}:
                continue
            if any(path == source or source in path.parents for path in (Path(job.mp3_path), Path(job.output_dir))):
                messagebox.showinfo("Processamento em andamento",
                                    "Espere o processamento desta pasta terminar antes de movê-la.", parent=self)
                return
        try:
            shutil.move(str(source), str(destination))
        except OSError as exc:
            messagebox.showerror("Não foi possível mover", str(exc), parent=self)
            return
        try:
            self._library_metadata.relocate_tree(source, destination)
            self._job_store.relocate_tree(source, destination)
        except OSError as exc:
            messagebox.showwarning(
                "Pasta movida", f"A pasta foi movida, mas alguns dados de organização não foram atualizados:\n{exc}",
                parent=self,
            )
        self._browser_selected = None
        self._refresh_focus_library()

    def _browser_move_folder(self) -> None:
        source = self._browser_manage_target()
        if source is None:
            return
        chosen = filedialog.askdirectory(parent=self, title="Mover pasta para", initialdir=str(source.parent))
        if not chosen:
            return
        parent = Path(chosen).resolve()
        if parent == source or source in parent.parents:
            messagebox.showerror("Destino inválido", "Escolha uma pasta fora da pasta que será movida.", parent=self)
            return
        self._browser_relocate(source, parent / source.name)

    def _browser_rename_folder(self) -> None:
        source = self._browser_manage_target()
        if source is None:
            return
        name = simpledialog.askstring("Renomear pasta", "Novo nome:", initialvalue=source.name, parent=self)
        if name is None or name.strip() == source.name:
            return
        name = name.strip()
        if not name or name in {".", ".."} or any(char in name for char in '<>:"/\\|?*'):
            messagebox.showerror("Nome inválido", "Escolha um nome de pasta válido.", parent=self)
            return
        self._browser_relocate(source, source.with_name(name))

    def _browser_process_audio(self) -> None:
        entry = self._browser_selected
        if entry is None:
            return
        if entry.kind == "document" and entry.path.name.casefold() == "transcription.md":
            self._open_summary_regeneration_dialog(entry.path)
            return
        if entry.kind != "audio":
            return
        if self._queue_pipeline(
            entry.path, _LANG_CODES.get(self.pipeline_language.get(), "pt"),
            self.pipeline_model.get(), self._selected_summary_provider_code(),
            self._selected_summary_template_code(), output_mode="both",
            output_dir=entry.path.parent,
            reuse_source_folder=entry.path.parent != Path(self.library_dir.get()).expanduser(),
            additional_instructions=RecorderApp._meeting_instructions(self),
        ):
            self._show_page("processing")

    @staticmethod
    def _browser_metadata_key(entry: BrowserEntry) -> Path:
        if entry.kind not in {"recording", "text_record"}:
            return entry.path
        try:
            return next(
                child for child in entry.path.iterdir()
                if child.is_file() and child.suffix.casefold() in {
                    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
                    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
                }
            )
        except (OSError, StopIteration):
            return entry.path

    def _browser_toggle_favorite(self) -> None:
        entry = self._browser_selected
        if entry is None or entry.kind not in {"recording", "text_record"}:
            return
        key = self._browser_metadata_key(entry)
        data = self._library_metadata.load().get(str(key.resolve()).casefold(), {})
        favorite = bool(data.get("favorite", False)) if isinstance(data, dict) else False
        try:
            self._library_metadata.save(key, favorite=not favorite)
        except OSError as exc:
            messagebox.showerror("Não foi possível salvar", str(exc), parent=self)
            return
        self._refresh_focus_library()

    def _browser_edit_metadata(self) -> None:
        entry = self._browser_selected
        if entry is None or entry.kind not in {"recording", "text_record"}:
            return
        key = self._browser_metadata_key(entry)
        data = self._library_metadata.load().get(str(key.resolve()).casefold(), {})
        tags = data.get("tags", []) if isinstance(data, dict) else []
        title = simpledialog.askstring("Título da gravação", "Título:",
                                       initialvalue=entry.title, parent=self)
        if title is None:
            return
        title = title.strip()
        if not title:
            messagebox.showerror("Título vazio", "Informe um título para a gravação.", parent=self)
            return
        tag_text = simpledialog.askstring("Etiquetas", "Etiquetas separadas por vírgula:",
                                          initialvalue=", ".join(tags) if isinstance(tags, list) else "",
                                          parent=self)
        if tag_text is None:
            return
        try:
            self._library_metadata.save(
                key, title=title,
                tags=tuple(tag.strip() for tag in tag_text.split(",") if tag.strip()),
            )
        except OSError as exc:
            messagebox.showerror("Não foi possível salvar", str(exc), parent=self)
            return
        self._refresh_focus_library()

    def _browser_export_document(self, document_format: str) -> None:
        entry = self._browser_selected
        if entry is None or entry.kind != "document" or entry.path.suffix.casefold() != ".md":
            return
        extension = ".docx" if document_format == "docx" else ".pdf"
        chosen = filedialog.asksaveasfilename(
            parent=self, title=f"Exportar {entry.path.name}",
            initialfile=f"{entry.path.stem}{extension}", defaultextension=extension,
            filetypes=[("Documento Word", "*.docx")] if document_format == "docx" else [("Documento PDF", "*.pdf")],
        )
        if not chosen:
            return
        try:
            if document_format == "docx":
                from record_transcript_resume.exports import export_docx
                export_docx(entry.path, Path(chosen))
            else:
                from record_transcript_resume.exports import export_pdf
                export_pdf(entry.path, Path(chosen))
        except Exception as exc:
            messagebox.showerror("Não foi possível exportar", str(exc), parent=self)
            return
        self.status.set(f"Documento exportado: {Path(chosen).name}")

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
        self._run_next_pending_job()
        self._refresh_library()
        self._refresh_processing_page()

    def _render_library_list(self) -> None:
        self._library_render_after = None
        if not hasattr(self, "library_items_frame"):
            return
        selected_item = self._selected_library_item() if hasattr(self, "_library_visible_items") else None
        selected_key = (
            str(selected_item.mp3_path or selected_item.folder) if selected_item is not None else ""
        )
        query = self.library_search.get().strip().casefold()
        filter_choice = self.library_filter.get()
        items = [
            item for item in self._library_items
            if not query or query in item.searchable_text
        ]
        selected_tag = self.library_tag_filter.get().casefold()
        if selected_tag != "todas as etiquetas":
            items = [item for item in items if selected_tag in (tag.casefold() for tag in item.tags)]
        if filter_choice == "Resumo pronto":
            items = [item for item in items if item.summary_available]
        elif filter_choice == "Favoritos":
            items = [item for item in items if item.favorite]
        elif filter_choice == "Resumo pendente":
            items = [
                item for item in items
                if not item.summary_available and (item.transcript_path is not None or item.summary_path is not None)
            ]
        elif filter_choice == "Só áudio":
            items = [
                item for item in items
                if item.mp3_path is not None and item.transcript_path is None and item.summary_path is None
            ]
        sort_choice = self.library_sort.get()
        if sort_choice == "Mais antigos":
            items.sort(key=lambda item: item.sort_at)
        elif sort_choice == "Título A–Z":
            items.sort(key=lambda item: (item.title.casefold(), -item.sort_at.timestamp()))
        elif sort_choice == "Favoritos primeiro":
            items.sort(key=lambda item: (not item.favorite, -item.sort_at.timestamp()))
        else:
            items.sort(key=lambda item: item.sort_at, reverse=True)
        signature = (
            tuple(items), len(self._library_items), self._library_directory_manual,
            getattr(self, "_library_folder_available", True),
        )
        if signature == self._library_render_signature:
            self._library_visible_items = items
            return
        self._library_render_signature = signature
        self._library_visible_items = items
        for row in self._library_rows:
            row.destroy()
        self._library_rows.clear()
        self._library_row_selectors.clear()
        if self._library_empty_panel is not None:
            self._library_empty_panel.destroy()
            self._library_empty_panel = None
        for index, item in enumerate(items):
            row = ctk.CTkFrame(
                self.library_items_frame, fg_color=_theme_color("#111C30"), corner_radius=10,
                border_width=1, border_color=_theme_color("#263550"), height=116,
            )
            row.pack(fill=tk.X, padx=(2, 4), pady=(0, 8))
            row.pack_propagate(False)
            heading = ctk.CTkFrame(row, fg_color="transparent")
            heading.pack(fill=tk.X, padx=16, pady=(9, 0))
            kind = ctk.CTkLabel(
                heading, text=item.contents_label.upper(),
                font=("Segoe UI", 9, "bold"),
                text_color=_theme_color("#AFC2EA"), anchor="w",
            )
            kind.pack(side=tk.LEFT)
            selector = ctk.CTkLabel(
                heading, text="Selecionar", font=("Segoe UI", 9, "bold"),
                text_color=_COLORS["muted"], anchor="e",
            )
            selector.pack(side=tk.RIGHT)
            title = ctk.CTkLabel(
                row, text=f"{'★  ' if item.favorite else ''}{item.title}",
                font=("Segoe UI", 13, "bold"), text_color=_COLORS["text"], anchor="w",
            )
            title.pack(fill=tk.X, padx=16)
            files = ctk.CTkLabel(
                row, text=item.next_step_label,
                font=("Segoe UI", 10), text_color=_theme_color("#C9D3FF"), anchor="w",
            )
            files.pack(fill=tk.X, padx=16)
            tags = f"  ·  {', '.join(item.tags[:2])}" if item.tags else ""
            date_label = "Gravado" if item.recorded_at else "Atualizado"
            metadata = ctk.CTkLabel(
                row, text=f"{date_label} {item.sort_at:%d/%m/%Y às %H:%M}{tags}",
                font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
            )
            metadata.pack(fill=tk.X, padx=16, pady=(0, 7))
            for target in (row, heading, kind, selector, title, files, metadata):
                target.bind("<Button-1>", lambda _event, selected=index: self._select_library_index(selected))
            self._library_rows.append(row)
            self._library_row_selectors.append(selector)
        total = len(self._library_items)
        self.library_count.set(f"{len(items)} de {total} {'item' if total == 1 else 'itens'}")
        selected_index = next(
            (
                index for index, item in enumerate(items)
                if str(item.mp3_path or item.folder) == selected_key
            ),
            0 if items else None,
        )
        if selected_index is not None:
            self._select_library_index(selected_index)
        else:
            self._library_selected_key = ""
            has_recordings = bool(self._library_items)
            unavailable = self._library_directory_manual and not getattr(self, "_library_folder_available", True)
            self._library_empty_panel = ctk.CTkFrame(
                self.library_items_frame, fg_color=_theme_color("#111C30"), corner_radius=10,
            )
            self._library_empty_panel.pack(fill=tk.X, padx=(2, 4), pady=(2, 8))
            ctk.CTkLabel(
                self._library_empty_panel,
                text=(
                    "Pasta indisponível" if unavailable else
                    "Nenhum resultado" if has_recordings else "Sua biblioteca está vazia"
                ),
                font=("Segoe UI", 16, "bold"), text_color=_COLORS["text"], anchor="w",
            ).pack(fill=tk.X, padx=18, pady=(18, 4))
            ctk.CTkLabel(
                self._library_empty_panel,
                text=(
                    "Esta pasta não está acessível. Escolha outra pasta para continuar."
                    if unavailable else
                    "Tente outra busca ou limpe os filtros para ver todas as gravações."
                    if has_recordings else "Grave um áudio ou importe um arquivo para começar."
                ),
                font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
                wraplength=500, justify=tk.LEFT,
            ).pack(fill=tk.X, padx=18, pady=(0, 14))
            ctk.CTkButton(
                self._library_empty_panel,
                text=(
                    "Escolher outra pasta" if unavailable else
                    "Limpar busca e filtros" if has_recordings else "Ir para Gravar"
                ),
                command=(
                    self._choose_library_dir if unavailable else
                    self._reset_library_filters if has_recordings else lambda: self._show_page("record")
                ),
                width=230, height=36, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            ).pack(anchor=tk.W, padx=18, pady=(0, 18))
            self._on_library_select()
        if getattr(self, "_current_page", None) == "library":
            self._apply_desktop_typography()

    def _schedule_library_render(self) -> None:
        if self._library_render_after is not None:
            self.after_cancel(self._library_render_after)
        self._library_render_after = self.after(120, self._render_library_list)

    def _show_library_choice_menu(
        self, anchor: ctk.CTkButton, variable: tk.StringVar, choices: list[str],
    ) -> None:
        current = getattr(self, "_library_choice_popup", None)
        if current is not None and current.winfo_exists():
            current.destroy()
        popup = ctk.CTkToplevel(self)
        self._library_choice_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=_theme_color("#314667"))
        options = ctk.CTkFrame(popup, fg_color=_theme_color("#14213A"), corner_radius=8)
        options.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        def choose(value: str) -> None:
            variable.set(value)
            if popup.winfo_exists():
                popup.destroy()

        for value in choices:
            ctk.CTkButton(
                options, text=value, command=lambda selection=value: choose(selection),
                height=32, corner_radius=6, anchor="w",
                fg_color=_theme_color("#304769") if variable.get() == value else "transparent",
                hover_color=_theme_color("#263B5A"), text_color=_COLORS["text"],
                font=("Segoe UI", 12),
            ).pack(fill=tk.X, padx=4, pady=2)
        width = max(anchor.winfo_width(), 190)
        height = len(choices) * 36 + 10
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 3
        left, top, screen_width, screen_height = self._current_monitor_bounds(work_area=True)
        x = min(x, left + screen_width - width - 4)
        if y + height > top + screen_height:
            y = anchor.winfo_rooty() - height - 3
        popup.geometry(self._geometry_string(width, height, x, y))
        popup.deiconify()
        popup.lift()
        popup.bind("<Escape>", lambda _event: popup.destroy())

        def close_when_pointer_leaves() -> None:
            if not popup.winfo_exists():
                return
            pointer_x = popup.winfo_pointerx()
            pointer_y = popup.winfo_pointery()
            if not (
                popup.winfo_rootx() <= pointer_x < popup.winfo_rootx() + popup.winfo_width()
                and popup.winfo_rooty() <= pointer_y < popup.winfo_rooty() + popup.winfo_height()
            ):
                popup.destroy()

        popup.bind("<Leave>", lambda _event: self.after(120, close_when_pointer_leaves), add="+")

    def _reset_library_filters(self) -> None:
        self.library_search.set("")
        self.library_filter.set("Todas")
        self.library_tag_filter.set("Todas as etiquetas")
        self.library_sort.set("Mais recentes")
        self._render_library_list()

    def _selected_library_item(self) -> LibraryItem | None:
        return next(
            (
                item for item in self._library_visible_items
                if str(item.mp3_path or item.folder) == self._library_selected_key
            ),
            None,
        )

    def _select_library_index(self, index: int) -> None:
        if index >= len(self._library_visible_items):
            return
        item = self._library_visible_items[index]
        self._library_selected_key = str(item.mp3_path or item.folder)
        for row_index, row in enumerate(self._library_rows):
            selected = row_index == index
            row.configure(
                fg_color=_theme_color("#1C2E4B") if selected else _theme_color("#111C30"),
                border_color=_COLORS["accent"] if selected else _theme_color("#263550"),
            )
            self._library_row_selectors[row_index].configure(
                text="✓ SELECIONADA" if selected else "Selecionar",
                text_color=_theme_color("#BBAEFF") if selected else _COLORS["muted"],
            )
        self._on_library_select()

    def _on_library_select(self, _event: object = None) -> None:
        item = self._selected_library_item()
        if item is None:
            self.library_detail_title.set("Nenhuma gravação selecionada")
            self.library_detail.set("Ajuste a busca ou os filtros para encontrar uma gravação.")
            self._library_selection_content.pack_forget()
            return
        if not self._library_selection_content.winfo_manager():
            self._library_selection_content.pack(fill=tk.X)
        summary_state = (
            "Gravação completa" if item.summary_available else
            "Transcrição pronta · resumo pendente" if item.transcript_path else
            "Áudio salvo · transcrição pendente" if item.mp3_path else
            "Documento salvo"
        )
        self.library_detail_title.set(item.title)
        date_label = "Gravado" if item.recorded_at else "Atualizado"
        self.library_detail.set(f"{date_label} {item.sort_at:%d/%m/%Y às %H:%M} · {summary_state}")
        self._library_file_names["ÁUDIO"].set(
            f"{item.mp3_path.suffix.lstrip('.').upper()} salvo" if item.mp3_path else "Não disponível"
        )
        self._library_file_names["TRANSCRIÇÃO"].set(
            "Pronta para ler e editar" if item.transcript_path else "Ainda não criada"
        )
        self._library_file_names["RESUMO"].set(
            "Pronto para ler e exportar" if item.summary_available else
            "Falhou; tente novamente" if item.summary_path else
            "Aguardando transcrição" if not item.transcript_path else "Ainda não criado"
        )
        self.library_favorite_button.configure(text="★ Remover favorito" if item.favorite else "☆ Favoritar")
        self.library_tags_text.set(
            f"Etiquetas: {', '.join(item.tags)}" if item.tags else "Sem etiquetas · use Editar para organizar"
        )
        location = f"{item.nested_in} › {item.folder.name}" if item.nested_in else item.folder.name
        self.library_location_text.set(f"Pasta: {location}")
        for button in (
            self.library_process_button, self.library_summary_button,
            self.library_audio_button, self.library_edit_button, self.library_open_summary_button,
        ):
            button.pack_forget()
        for button, available in (
            (self.library_audio_button, item.mp3_path is not None),
            (self.library_edit_button, item.transcript_path is not None),
            (self.library_open_summary_button, item.summary_available),
            (self.library_process_button, item.mp3_path is not None and item.transcript_path is None),
            (self.library_summary_button, item.transcript_path is not None and not item.summary_available),
        ):
            if available:
                button.pack(side=tk.RIGHT)
        for actions in self._library_asset_actions.values():
            if any(child.winfo_manager() for child in actions.winfo_children()):
                if not actions.winfo_manager():
                    actions.pack(side=tk.RIGHT, padx=(2, 10), pady=9)
            else:
                actions.pack_forget()
        if item.summary_path or item.transcript_path:
            self._library_exports.pack(fill=tk.X, padx=14, pady=(0, 8))
            self.library_preview_text.set(self._library_preview_for(item))
            self._library_preview.pack(fill=tk.X, padx=14, pady=(0, 12))
        else:
            self._library_exports.pack_forget()
            self._library_preview.pack_forget()
        self.last_file.set(str(item.mp3_path or item.folder))

    @staticmethod
    def _library_preview_for(item: LibraryItem) -> str:
        source = item.summary_path if item.summary_available else item.transcript_path
        if source is None:
            return "O áudio está salvo. Use Processar áudio para criar a transcrição e o resumo."
        try:
            with source.open("r", encoding="utf-8") as document:
                excerpt = document.read(900)
        except (OSError, UnicodeError):
            return "Não foi possível ler a prévia. Abra a pasta para verificar o arquivo."
        lines = [line.strip().lstrip("# ") for line in excerpt.splitlines() if line.strip()]
        preview = " ".join(lines)
        return f"{preview[:420].rstrip()}{'…' if len(preview) > 420 else ''}" or "O documento está vazio."

    def _toggle_selected_library_favorite(self) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        try:
            self._library_metadata.save(item.mp3_path or item.folder, favorite=not item.favorite)
        except OSError as exc:
            messagebox.showerror("Não foi possível salvar", str(exc))
            return
        self._refresh_library()

    def _edit_selected_library_metadata(self) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Organizar gravação")
        self._fit_dialog(dialog, 460, 275, 360, 240)
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()
        title_value = tk.StringVar(value=item.title)
        tags_value = tk.StringVar(value=", ".join(item.tags))
        shell = ctk.CTkFrame(dialog, fg_color=_COLORS["surface"], corner_radius=12)
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ctk.CTkLabel(shell, text="Título", anchor="w", font=("Segoe UI", 10, "bold")).pack(fill=tk.X, padx=14, pady=(14, 3))
        title_entry = ctk.CTkEntry(shell, textvariable=title_value, height=34)
        title_entry.pack(fill=tk.X, padx=14)
        ctk.CTkLabel(shell, text="Etiquetas (separadas por vírgula)", anchor="w", font=("Segoe UI", 10, "bold")).pack(fill=tk.X, padx=14, pady=(12, 3))
        ctk.CTkEntry(shell, textvariable=tags_value, height=34).pack(fill=tk.X, padx=14)
        ctk.CTkLabel(shell, text="O áudio e os documentos permanecem na pasta original.", anchor="w", text_color=_COLORS["muted"], font=("Segoe UI", 9)).pack(fill=tk.X, padx=14, pady=(10, 4))
        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill=tk.X, padx=14, pady=(4, 14))

        def save_metadata() -> None:
            title = title_value.get().strip()
            if not title:
                messagebox.showerror("Título vazio", "Informe um título para esta gravação.", parent=dialog)
                return
            tags = tuple(part.strip() for part in tags_value.get().split(",") if part.strip())
            try:
                self._library_metadata.save(item.mp3_path or item.folder, title=title, tags=tags)
            except OSError as exc:
                messagebox.showerror("Não foi possível salvar", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._refresh_library()

        ctk.CTkButton(actions, text="Cancelar", command=dialog.destroy, width=90, height=32, fg_color=_theme_color("#263550")).pack(side=tk.RIGHT)
        ctk.CTkButton(actions, text="Salvar", command=save_metadata, width=90, height=32, text_color=_COLORS['accent_text'], fg_color=_COLORS["accent"]).pack(side=tk.RIGHT, padx=(0, 8))
        title_entry.focus_set()

    def _process_selected_library_audio(self) -> None:
        """Snapshot current processing choices and add the selected audio to the serial queue."""
        item = self._selected_library_item()
        if item is None or item.mp3_path is None:
            messagebox.showinfo("Áudio indisponível", "Selecione um áudio salvo na Biblioteca para processar.")
            return
        if self._queue_pipeline(
            item.mp3_path,
            _LANG_CODES.get(self.pipeline_language.get(), "pt"),
            self.pipeline_model.get(),
            self._selected_summary_provider_code(),
            self._selected_summary_template_code(),
            output_mode="both",
            output_dir=item.folder,
            reuse_source_folder=item.has_own_folder,
            additional_instructions=RecorderApp._meeting_instructions(self),
        ):
            self._show_page("processing")

    def _refresh_processing_page(self) -> None:
        """Render persisted serial-queue state without relying on the active page."""
        if not hasattr(self, "processing_job_list"):
            return
        if not self._maximized:
            self._refresh_focus_processes()
            return
        content_width = max(
            340,
            (self.processing_job_list.winfo_width() - 70) // 2
            if self._desktop_layout else self.processing_job_list.winfo_width() - 44,
        )
        for child in self.processing_job_list.winfo_children():
            child.destroy()
        all_jobs = self._job_store.list()
        active_jobs = [
            job for job in all_jobs
            if job.status in {"queued", "running", "failed", "needs_attention", "cancelled", "warning"}
        ]
        completed_jobs = sorted(
            (job for job in all_jobs if job.status == "completed"),
            key=lambda job: job.updated_at, reverse=True,
        )[:5]
        jobs = [*active_jobs, *completed_jobs]
        active = next((job for job in jobs if job.status == "running"), None)
        queued_count = sum(job.status == "queued" for job in jobs)
        if active is not None:
            self.processing_overview.set(
                f"Processando 1 áudio por vez · agora: {active.audio_path.name} · {queued_count} aguardando",
            )
        elif queued_count:
            self.processing_overview.set(f"{queued_count} áudio(s) aguardando processamento serial")
        elif active_jobs:
            self.processing_overview.set("Veja avisos e tarefas que exigem atenção abaixo.")
        elif completed_jobs:
            self.processing_overview.set("Últimos resultados concluídos · abra a pasta ou encontre tudo na Biblioteca")
        else:
            self.processing_overview.set("Nenhum processamento na fila")
            ctk.CTkLabel(
                self.processing_job_list,
                text="Quando você clicar em Processar áudio na Biblioteca, o acompanhamento aparecerá aqui.",
                font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT, wraplength=content_width,
            ).pack(fill=tk.X, padx=12, pady=12)
            return

        status_labels = {
            "queued": "NA FILA", "running": "PROCESSANDO", "failed": "FALHOU",
            "needs_attention": "ATENÇÃO", "cancelled": "CANCELADO", "warning": "COM AVISO",
            "completed": "PRONTO",
        }
        status_colors = {
            "queued": _theme_color("#C9D3FF"), "running": _theme_color("#B7AAFF"), "failed": _COLORS["danger"],
            "needs_attention": _COLORS["warning"], "cancelled": _COLORS["muted"],
            "warning": _COLORS["warning"],
            "completed": _COLORS["success"],
        }
        destinations: dict[str, ctk.CTkFrame] = {}
        if self._desktop_layout:
            for key, title, group in (
                ("active", "EM ANDAMENTO E ATENÇÃO", active_jobs),
                ("completed", "CONCLUÍDOS RECENTEMENTE", completed_jobs),
            ):
                column = ctk.CTkFrame(self.processing_job_list, fg_color="transparent")
                column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 4))
                ctk.CTkLabel(
                    column, text=title, font=("Segoe UI", 12, "bold"),
                    text_color=_COLORS["muted"], anchor="w",
                ).pack(fill=tk.X, padx=10, pady=(10, 5))
                if not group:
                    ctk.CTkLabel(
                        column,
                        text="Nenhum processamento nesta seção.",
                        font=("Segoe UI", 12), text_color=_COLORS["muted"], anchor="w",
                    ).pack(fill=tk.X, padx=10, pady=12)
                destinations[key] = column
        for job in jobs:
            destination = destinations.get(
                "completed" if job.status == "completed" else "active",
                self.processing_job_list,
            )
            row = ctk.CTkFrame(destination, fg_color=_theme_color("#0D1525"), corner_radius=9)
            row.pack(fill=tk.X, padx=10, pady=(8, 0))
            heading = ctk.CTkFrame(row, fg_color="transparent")
            heading.pack(fill=tk.X, padx=10, pady=(8, 1))
            name = job.audio_path.name
            max_name_chars = max(32, (content_width - 100) // 7)
            if len(name) > max_name_chars:
                name = f"{name[:max_name_chars - 1]}…"
            ctk.CTkLabel(
                heading, text=name, font=("Segoe UI", 10, "bold"),
                text_color=_COLORS["text"], anchor="w", justify=tk.LEFT,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            action_text = status_labels.get(job.status, job.status.upper())
            ctk.CTkLabel(
                heading, text=action_text, font=("Segoe UI", 8, "bold"),
                text_color=status_colors.get(job.status, _COLORS["muted"]),
                width=92, anchor="e",
            ).pack(side=tk.RIGHT, padx=(8, 0))
            detail = job.stage or "Aguardando"
            if job.error:
                preview = " ".join(job.error.split())
                limit = 45 if self._desktop_layout else 75
                if len(preview) > limit:
                    preview = f"{preview[:limit].rstrip()}…"
                detail = f"{detail} · {preview}"
            ctk.CTkLabel(
                row, text=detail, font=("Segoe UI", 9), text_color=_COLORS["muted"],
                anchor="w", justify=tk.LEFT, wraplength=content_width,
            ).pack(fill=tk.X, padx=10, pady=(0, 2))
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(fill=tk.X, padx=10, pady=(4, 8))
            if job.status == "running":
                ctk.CTkButton(
                    actions, text="Cancelar", command=self._request_cancel_processing, width=76, height=28,
                    corner_radius=7, fg_color=_theme_color("#3A2637"), hover_color=_theme_color("#573248"), text_color=_COLORS["danger"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT)
            elif job.status == "queued":
                ctk.CTkButton(
                    actions, text="Remover", command=lambda job_id=job.id: self._remove_processing_job(job_id), width=76, height=28,
                    corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT)
            elif job.status == "completed":
                ctk.CTkButton(
                    actions, text="Abrir pasta", command=lambda folder=job.output_dir: self._open_folder_path(Path(folder)), width=82, height=28,
                    corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT)
            elif job.status == "warning":
                ctk.CTkButton(
                    actions, text="Remover", command=lambda job_id=job.id: self._remove_processing_job(job_id), width=68, height=28,
                    corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT, padx=(5, 0))
                ctk.CTkButton(
                    actions, text="Ver aviso", command=lambda job_id=job.id: self._show_processing_error(job_id), width=76, height=28,
                    corner_radius=7, fg_color=_theme_color("#3A2637"), hover_color=_theme_color("#573248"), text_color=_COLORS["warning"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT, padx=(5, 0))
                if job.summary_failed and (Path(job.output_dir) / "transcription.md").is_file():
                    ctk.CTkButton(
                        actions, text="Refazer resumo", command=lambda job_id=job.id: self._retry_warning_summary(job_id), width=108, height=28,
                        corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"), text_color=_COLORS["text"],
                        font=("Segoe UI", 9, "bold"),
                    ).pack(side=tk.RIGHT, padx=(5, 0))
                ctk.CTkButton(
                    actions, text="Abrir pasta", command=lambda folder=job.output_dir: self._open_folder_path(Path(folder)), width=82, height=28,
                    corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT, padx=(5, 0))
            elif job.status in {"failed", "needs_attention", "cancelled"}:
                ctk.CTkButton(
                    actions, text="Remover", command=lambda job_id=job.id: self._remove_processing_job(job_id), width=68, height=28,
                    corner_radius=7, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT, padx=(5, 0))
                ctk.CTkButton(
                    actions, text="Tentar de novo", command=lambda job_id=job.id: self._retry_job(job_id), width=92, height=28,
                    corner_radius=7, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"), text_color=_COLORS["text"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side=tk.RIGHT, padx=(5, 0))
                if job.error:
                    ctk.CTkButton(
                        actions, text="Ver erro", command=lambda job_id=job.id: self._show_processing_error(job_id), width=70, height=28,
                        corner_radius=7, fg_color=_theme_color("#3A2637"), hover_color=_theme_color("#573248"), text_color=_COLORS["danger"],
                        font=("Segoe UI", 9, "bold"),
                    ).pack(side=tk.RIGHT, padx=(5, 0))
        if not self._desktop_layout:
            ctk.CTkFrame(self.processing_job_list, height=8, fg_color="transparent").pack(fill=tk.X)
        if getattr(self, "_current_page", None) == "processing":
            self._apply_desktop_typography()

    def _set_focus_process_filter(self, selected: str) -> None:
        self._focus_process_filter.set(selected)
        self._refresh_focus_processes()

    def _refresh_focus_processes(self) -> None:
        if not hasattr(self, "_focus_process_list"):
            return
        all_jobs = self._job_store.list()
        counts = {
            "Todos": len(all_jobs),
            "Em andamento": sum(job.status == "running" for job in all_jobs),
            "Aguardando": sum(job.status == "queued" for job in all_jobs),
            "Exigem atenção": sum(job.status in {"failed", "needs_attention", "warning", "cancelled"} for job in all_jobs),
            "Concluídos": sum(job.status == "completed" for job in all_jobs),
        }
        choice = self._focus_process_filter.get()
        for label, button in self._focus_process_filter_buttons.items():
            button.configure(
                text=f"{label}  {counts[label]}",
                fg_color=_theme_color("#3A3379") if label == choice else _theme_color("#263550"),
            )
        jobs = all_jobs
        if choice == "Em andamento":
            jobs = [job for job in jobs if job.status == "running"]
        elif choice == "Aguardando":
            jobs = [job for job in jobs if job.status == "queued"]
        elif choice == "Exigem atenção":
            jobs = [job for job in jobs if job.status in {"failed", "needs_attention", "warning", "cancelled"}]
        elif choice == "Concluídos":
            jobs = [job for job in jobs if job.status == "completed"]
        jobs.sort(key=lambda job: job.updated_at or job.created_at, reverse=True)
        if self._focus_selected_job_id not in {job.id for job in jobs}:
            self._focus_selected_job_id = jobs[0].id if jobs else None
        for widget in self._focus_process_list.winfo_children():
            widget.destroy()
        self._focus_process_rows: dict[str, ctk.CTkFrame] = {}
        labels = {"running": "Em andamento", "queued": "Aguardando",
                  "failed": "Falhou", "needs_attention": "Exige atenção",
                  "warning": "Aviso", "cancelled": "Cancelado", "completed": "Concluído"}
        for job in jobs:
            selected = job.id == self._focus_selected_job_id
            row = ctk.CTkFrame(
                self._focus_process_list,
                fg_color=_theme_color("#213251") if selected else _theme_color("#17243A"),
                corner_radius=8, border_width=1,
                border_color=_theme_color("#8170E6") if selected else _theme_color("#344867"),
            )
            row.pack(fill=tk.X, pady=(0, 7))
            self._focus_process_rows[job.id] = row
            marker = ctk.CTkLabel(
                row, text="", width=9, height=9, corner_radius=5,
                fg_color={"running": _theme_color("#7665E8"), "queued": _theme_color("#8FA1BC"),
                          "completed": _theme_color("#55D6A0")}.get(job.status, _theme_color("#F4A7A8")),
            )
            marker.pack(side=tk.LEFT, padx=(13, 11), pady=18)
            body = ctk.CTkFrame(row, fg_color="transparent")
            body.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=9)
            title = ctk.CTkLabel(
                body, text=job.audio_path.stem, font=("Segoe UI", 11, "bold"),
                text_color=_COLORS["text"], anchor="w",
            )
            title.pack(fill=tk.X)
            stage = ctk.CTkLabel(
                body, text=job.stage or labels.get(job.status, job.status),
                font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w",
            )
            stage.pack(fill=tk.X)
            state = ctk.CTkLabel(
                row, text=labels.get(job.status, job.status),
                font=("Segoe UI", 10, "bold"),
                text_color=_theme_color("#FFB7AD") if job.status in {"failed", "needs_attention", "cancelled"}
                else _theme_color("#A4EDCE") if job.status == "completed" else _theme_color("#C5BDFF"),
            )
            state.pack(side=tk.RIGHT, padx=13)
            for widget in (row, marker, body, title, stage, state):
                widget.bind(
                    "<Button-1>",
                    lambda _event, job_id=job.id: self._select_focus_process_job(job_id),
                    add="+",
                )
        if not jobs:
            ctk.CTkLabel(
                self._focus_process_list,
                text="Nenhum processo nesta visão. Escolha outro filtro ou inicie um processamento.",
                font=("Segoe UI", 11), text_color=_COLORS["muted"],
            ).pack(anchor=tk.W, pady=18)
        self._focus_process_selected()

    def _focus_selected_job(self) -> ProcessingJob | None:
        if not self._focus_selected_job_id:
            return None
        return next((job for job in self._job_store.list() if job.id == self._focus_selected_job_id), None)

    def _select_focus_process_job(self, job_id: str) -> None:
        self._focus_selected_job_id = job_id
        for current_id, row in self._focus_process_rows.items():
            selected = current_id == job_id
            row.configure(
                fg_color=_theme_color("#213251") if selected else _theme_color("#17243A"),
                border_color=_theme_color("#8170E6") if selected else _theme_color("#344867"),
            )
        self._focus_process_selected()

    def _focus_process_selected(self, _event: object = None) -> None:
        job = self._focus_selected_job()
        if job is None:
            self._focus_process_title.set("Nenhum processo nesta visão")
            self._focus_process_detail.set("Escolha outro filtro ou inicie um processamento.")
            self._focus_process_state.set("")
            self._focus_process_stage.set("—")
            self._focus_process_audio.set("—")
            self._focus_process_when.set("—")
            self._focus_process_error_panel.pack_forget()
            for button in (self._focus_process_retry, self._focus_process_open,
                           self._focus_process_error, self._focus_process_remove):
                button.configure(state=tk.DISABLED)
                button.pack_forget()
            return
        self._focus_process_title.set(job.audio_path.stem)
        state = {
            "running": "Em andamento", "queued": "Aguardando",
            "failed": "Falhou", "needs_attention": "Exige atenção",
            "warning": "Concluído com aviso", "cancelled": "Cancelado", "completed": "Concluído",
        }.get(job.status, job.status)
        short_error = " ".join(job.error.split())
        if len(short_error) > 190:
            short_error = short_error[:187].rstrip() + "…"
        self._focus_process_state.set(state)
        self._focus_process_detail.set(f"Resultado em {Path(job.output_dir).name}")
        self._focus_process_stage.set(job.stage or "Aguardando")
        self._focus_process_audio.set("Preservado" if job.audio_path.is_file() else "Indisponível")
        self._focus_process_when.set(
            job.updated_at[:16].replace("T", " ") if job.updated_at else "—"
        )
        self._focus_process_error_summary.set(short_error)
        if short_error:
            if not self._focus_process_error_panel.winfo_manager():
                self._focus_process_error_panel.pack(
                    fill=tk.X, padx=14, pady=(0, 10), before=self._focus_process_retry.master,
                )
        else:
            self._focus_process_error_panel.pack_forget()
        can_retry = (
            job.status in {"failed", "needs_attention", "cancelled"} and job.audio_path.is_file()
            or job.summary_failed and (Path(job.output_dir) / "transcription.md").is_file()
        )
        for button in (self._focus_process_retry, self._focus_process_open,
                       self._focus_process_error, self._focus_process_remove):
            button.pack_forget()
        if can_retry:
            self._focus_process_retry.configure(
                state=tk.NORMAL,
                text="Refazer resumo" if job.summary_failed else "Tentar novamente",
            )
            self._focus_process_retry.pack(side=tk.LEFT)
        if Path(job.output_dir).is_dir():
            self._focus_process_open.configure(state=tk.NORMAL)
            self._focus_process_open.pack(side=tk.LEFT, padx=(8 if can_retry else 0, 0))
        if job.error:
            self._focus_process_error.configure(state=tk.NORMAL)
            self._focus_process_error.pack(side=tk.LEFT, padx=(8, 0))
        if job.status != "running":
            self._focus_process_remove.configure(state=tk.NORMAL)
            self._focus_process_remove.pack(side=tk.RIGHT)

    def _focus_retry_job(self) -> None:
        job = self._focus_selected_job()
        if job is None:
            return
        if job.summary_failed and (Path(job.output_dir) / "transcription.md").is_file():
            self._retry_warning_summary(job.id)
        else:
            self._retry_job(job.id)

    def _focus_open_job_folder(self) -> None:
        job = self._focus_selected_job()
        if job is not None:
            self._open_folder_path(Path(job.output_dir))

    def _focus_show_job_error(self) -> None:
        job = self._focus_selected_job()
        if job is not None:
            self._show_processing_error(job.id)

    def _focus_remove_job(self) -> None:
        job = self._focus_selected_job()
        if job is not None:
            self._remove_processing_job(job.id)

    def _remove_processing_job(self, job_id: str) -> None:
        job = next((item for item in self._job_store.list() if item.id == job_id), None)
        if job is None or job.status == "running":
            return
        if self._job_store.remove(job_id):
            self.status.set("Processo removido da lista. O áudio e os documentos foram preservados.")
            self._refresh_library()
            self._refresh_processing_page()

    def _show_processing_error(self, job_id: str) -> None:
        job = next((item for item in self._job_store.list() if item.id == job_id), None)
        if job is None:
            return
        details = (
            f"Arquivo de áudio:\n{job.audio_path}\n\n"
            f"Etapa:\n{job.stage or 'Não identificada'}\n\n"
            f"{'Aviso' if job.status == 'warning' else 'Erro'} informado pelo processamento:\n{job.error or 'Sem detalhes adicionais.'}\n\n"
            f"{_log_hint()}"
        )
        dialog = ctk.CTkToplevel(self)
        dialog.title("Detalhes do processamento")
        self._fit_dialog(dialog, 640, 430, 420, 300)
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        ctk.CTkLabel(
            dialog, text="O que aconteceu", font=("Segoe UI", 15, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 8))
        error_text = ctk.CTkTextbox(
            dialog, wrap="word", fg_color=_theme_color("#0D1525"), border_width=1,
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"],
            font=("Segoe UI", 10),
        )
        error_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        error_text.insert("1.0", details)
        error_text.configure(state=tk.DISABLED)
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill=tk.X, padx=16, pady=(0, 14))

        def copy_details() -> None:
            try:
                self.clipboard_clear()
                self.clipboard_append(details)
                self.update_idletasks()
                self.status.set("Detalhes do erro copiados.")
            except tk.TclError:
                pass

        ctk.CTkButton(
            actions, text="Copiar detalhes", command=copy_details, height=32,
            corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            actions, text="Fechar", command=dialog.destroy, height=32,
            corner_radius=8, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)

    def _cancel_queued_job(self, job_id: str) -> None:
        self._job_store.update(job_id, status="cancelled", stage="Cancelado", error="Removido da fila pelo usuário")
        self._refresh_library()
        self._refresh_processing_page()

    def _retry_job(self, job_id: str) -> None:
        job = next((item for item in self._job_store.list() if item.id == job_id), None)
        if job is None or not job.audio_path.is_file():
            messagebox.showerror("Áudio indisponível", "O arquivo de áudio desse processamento não foi encontrado.")
            return
        self._job_store.update(job_id, status="queued", stage="Na fila", error="")
        self._refresh_library()
        self._refresh_processing_page()
        self._run_next_pending_job()

    def _open_selected_folder(self) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        self._open_folder_path(item.folder)

    def _open_selected_audio(self) -> None:
        item = self._selected_library_item()
        if item is None or item.mp3_path is None or not item.mp3_path.is_file():
            messagebox.showerror("Áudio indisponível", "O arquivo de áudio desta gravação não foi encontrado.")
            return
        try:
            os.startfile(str(item.mp3_path))
        except OSError as exc:
            messagebox.showerror("Não foi possível abrir o áudio", str(exc))

    def _open_folder_path(self, folder: Path) -> None:
        try:
            os.startfile(str(folder))
        except AttributeError:
            subprocess.Popen(["explorer", str(folder)])
        except OSError as exc:
            messagebox.showerror("Não foi possível abrir", str(exc))

    def _retry_warning_summary(self, job_id: str) -> None:
        job = next((item for item in self._job_store.list() if item.id == job_id), None)
        if job is None or not job.summary_failed:
            return
        transcript_path = Path(job.output_dir) / "transcription.md"
        if not transcript_path.is_file():
            messagebox.showerror("Transcrição indisponível", "A transcrição necessária para refazer o resumo não foi encontrada.")
            return
        self._open_summary_regeneration_dialog(transcript_path, job_id=job_id)

    def _export_selected_document(self, document_format: str) -> None:
        item = self._selected_library_item()
        if item is None:
            messagebox.showinfo("Biblioteca", "Selecione uma gravação primeiro.")
            return
        source = self._editor_document_path if self._library_editing else (
            item.summary_path
            if getattr(item, "summary_available", item.summary_path is not None)
            else item.transcript_path
        )
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
        if document_format == "pdf":
            try:
                os.startfile(str(destination))
            except AttributeError:
                # The packaged app is Windows-only, but this keeps source
                # previews usable on platforms without os.startfile.
                subprocess.Popen(["explorer", str(destination)])
            except OSError as exc:
                self.status.set(f"PDF exportado: {destination.name}")
                messagebox.showwarning(
                    "PDF exportado",
                    f"O arquivo foi criado, mas não foi possível abri-lo automaticamente.\n\n{exc}",
                )
                return
            self.status.set(f"PDF exportado e aberto: {destination.name}")
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
        self._fit_dialog(window, 860, 680, 500, 400)
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
            shell, corner_radius=10, fg_color=_theme_color("#080C16"), border_width=1,
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Consolas", 11), wrap="word",
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
            editor_actions, text="Nomear falantes", command=self._open_speaker_names_dialog,
            width=110, height=34, corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_copy_button = ctk.CTkButton(
            editor_actions, text="Copiar texto", command=self._copy_open_document,
            width=102, height=34, corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_copy_button.pack(side=tk.LEFT)
        if is_transcript:
            self.library_suggest_names_button.pack(side=tk.LEFT, padx=(7, 0))
        ctk.CTkButton(
            editor_actions, text="Fechar", command=self._close_transcript_editor,
            width=82, height=34, corner_radius=9, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        self.library_save_button = ctk.CTkButton(
            editor_actions, text="Salvar", command=self._save_open_document,
            width=76, height=34, corner_radius=9, fg_color=_theme_color("#244462"), hover_color=_theme_color("#315A80"),
            text_color=_COLORS["text"], font=("Segoe UI", 10, "bold"),
        )
        self.library_save_button.pack(side=tk.RIGHT, padx=(0, 7))
        self.library_regenerate_button = ctk.CTkButton(
            editor_actions, text="Salvar e gerar resumo", command=self._save_transcript_and_regenerate,
            height=34, corner_radius=9, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"],
            text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold"),
        )
        if is_transcript:
            self.library_regenerate_button.pack(side=tk.RIGHT, padx=(0, 7))
        window.bind("<Control-s>", self._save_open_document_shortcut, add="+")
        window.after(50, window.focus_force)

    def _copy_open_document(self) -> None:
        """Copy the complete editable document without requiring selection."""
        if not getattr(self, "_library_editing", False):
            messagebox.showinfo("Documento indisponível", "Abra uma transcrição ou resumo antes de copiar.")
            return
        content = self.transcript_editor.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showinfo("Documento vazio", "Não há texto para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        self.status.set("Texto completo copiado para a área de transferência.")

    def _configure_markdown_tags(self) -> None:
        """Make Markdown structure scannable while retaining editable source."""
        editor = self.transcript_editor._textbox
        editor.tag_configure("markdown_h1", foreground=_theme_color("#C7BDFF"), font=("Consolas", 14, "bold"), spacing1=12, spacing3=6)
        editor.tag_configure("markdown_h2", foreground=_theme_color("#9FC7FF"), font=("Consolas", 12, "bold"), spacing1=10, spacing3=4)
        editor.tag_configure("markdown_h3", foreground=_theme_color("#B8C8E8"), font=("Consolas", 11, "bold"), spacing1=8, spacing3=3)
        editor.tag_configure("markdown_bold", foreground=_theme_color("#FFFFFF"), font=("Consolas", 11, "bold"))
        editor.tag_configure("markdown_bullet", foreground=_theme_color("#B8C8E8"))

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
            "saving": ("Salvando…", _theme_color("#9FC7FF")),
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
        self._open_summary_regeneration_dialog(transcript_path)

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

    def _open_speaker_names_dialog(self) -> None:
        """Let the user provide names; the app never claims to identify a voice."""
        if not self._editor_is_transcript:
            return
        from record_transcript_resume.speaker_names import apply_speaker_name_map, speaker_labels

        content = self.transcript_editor.get("1.0", "end-1c")
        labels = speaker_labels(content)
        if not labels:
            messagebox.showinfo(
                "Nenhum falante separado",
                "Esta transcrição ainda não tem rótulos como Pessoa 1. Ative Separar falantes antes de processar o áudio.",
            )
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nomear falantes")
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()
        self._fit_dialog(dialog, 460, max(270, 170 + len(labels) * 48), 360, 260)
        dialog.resizable(False, False)
        shell = ctk.CTkFrame(dialog, fg_color=_COLORS["surface"], corner_radius=14)
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ctk.CTkLabel(shell, text="Nomear falantes", font=("Segoe UI", 14, "bold"), text_color=_COLORS["text"], anchor="w").pack(fill=tk.X, padx=14, pady=(14, 2))
        ctk.CTkLabel(
            shell, text="Preencha somente quem você reconhecer. Os nomes serão aplicados à transcrição e ao próximo resumo gerado.",
            font=("Segoe UI", 9), text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT, wraplength=410,
        ).pack(fill=tk.X, padx=14, pady=(0, 10))
        fields: dict[str, tk.StringVar] = {}
        for label in labels:
            row = ctk.CTkFrame(shell, fg_color="transparent")
            row.pack(fill=tk.X, padx=14, pady=(0, 7))
            ctk.CTkLabel(row, text=label, width=88, font=("Segoe UI", 10, "bold"), text_color=_COLORS["text"], anchor="w").pack(side=tk.LEFT)
            value = tk.StringVar()
            fields[label] = value
            ctk.CTkEntry(row, textvariable=value, placeholder_text="Nome (opcional)", height=32, corner_radius=8, fg_color=_theme_color("#080C16"), border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill=tk.X, padx=14, pady=(4, 14))
        ctk.CTkButton(actions, text="Cancelar", command=dialog.destroy, width=82, height=32, corner_radius=8, fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"], font=("Segoe UI", 10, "bold")).pack(side=tk.RIGHT)

        def apply_names() -> None:
            names = {label: value.get() for label, value in fields.items()}
            if not any(name.strip() for name in names.values()):
                messagebox.showinfo("Nenhum nome informado", "Informe ao menos um nome ou cancele esta janela.", parent=dialog)
                return
            self.transcript_editor.delete("1.0", tk.END)
            self.transcript_editor.insert("1.0", apply_speaker_name_map(content, names))
            self._editor_dirty = True
            self._set_editor_save_state("dirty")
            self.status.set("Nomes aplicados · salve e gere o resumo para usá-los")
            dialog.destroy()

        ctk.CTkButton(actions, text="Aplicar ao texto", command=apply_names, height=32, corner_radius=8, fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["accent_text"], font=("Segoe UI", 10, "bold")).pack(side=tk.RIGHT, padx=(0, 7))

    def _regenerate_selected_summary(self) -> None:
        item = self._selected_library_item()
        if item is None or item.transcript_path is None:
            messagebox.showinfo("Transcrição indisponível", "Esta gravação ainda não tem transcrição para resumir.")
            return
        self._open_summary_regeneration_dialog(item.transcript_path)

    def _tray_can_start_meeting(self) -> bool:
        recording = self._service is not None and self._service.state == RecordingState.RECORDING
        finalizing = self._stop_thread is not None and self._stop_thread.is_alive()
        return not recording and not finalizing

    def _tray_can_stop_meeting(self) -> bool:
        return self._service is not None and self._service.state == RecordingState.RECORDING

    def _start_recording_from_tray(self) -> None:
        """Start safely from the notification area without forcing the window open."""
        if not self._tray_can_start_meeting():
            return
        self._start_recording()
        if self._tray_can_stop_meeting():
            self._tray.notify("Voice Notes", "Gravação iniciada em segundo plano.")
        self._refresh_compact_controls()

    def _stop_recording_from_tray(self) -> None:
        """Request a normal, non-destructive stop from the notification area."""
        if not self._tray_can_stop_meeting():
            return
        self._stop_recording()
        self._tray.notify("Voice Notes", "Finalizando gravação e salvando o áudio.")
        self._refresh_compact_controls()

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
        self._sync_recording_meter()
        self._recording_processing_options = {
            "output_mode": self.recording_output_mode.get(),
            "language": _LANG_CODES.get(self.pipeline_language.get(), "pt"),
            "model_size": self.pipeline_model.get(),
            "provider": self._selected_summary_provider_code(),
            "summary_template": self._selected_summary_template_code(),
            "additional_instructions": RecorderApp._meeting_instructions(self),
            "transcription_provider": self._selected_transcription_provider_code(),
            "separate_speakers": self.diarize_speakers.get(),
        }
        self._started_at = time.monotonic()
        self._recording_deadline = self._started_at + limit_seconds if limit_seconds else None
        self._last_output = output_path
        self.status.set("Recording")
        if limit_seconds:
            self.recording_limit_hint.set(f"Parada automática em {self._format_duration(limit_seconds)}")
        else:
            self.recording_limit_hint.set("Sem parada automática")
        self.last_file.set(str(output_path))
        self._set_recording_action_state(start=tk.DISABLED, stop=tk.NORMAL, show_stop=True)
        self._refresh_compact_controls()
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
        self._set_recording_action_state(stop=tk.DISABLED)
        self.status.set("Tempo concluído · finalizando..." if automatic else "Finalizando gravação...")
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
            self._post_to_ui(self._show_stop_error, str(exc))
            return
        except Exception as exc:
            log(f"GUI: service.stop() lancou excecao inesperada: {type(exc).__name__}: {exc}")
            self._post_to_ui(self._show_stop_error, f"Erro inesperado ao finalizar: {exc}")
            return
        log(f"GUI: service.stop() OK -> {output_path.name}")
        self._post_to_ui(self._show_completed, output_path)
        log("GUI: after(_show_completed) agendado")

    def _show_stop_error(self, message: str) -> None:
        self.status.set("Falha ao finalizar gravação")
        self._sync_recording_meter()
        self.device_info_text.set("")
        self._set_recording_action_state(start=tk.NORMAL, stop=tk.DISABLED, show_stop=False)
        self.process_button.configure(state=tk.NORMAL)
        self.retry_summary_button.configure(state=tk.NORMAL)
        self.provider_selector.configure(state="readonly")
        self._set_summary_template_state(tk.NORMAL)
        self._set_navigation_state(tk.NORMAL)
        self._set_capture_preferences_state(tk.NORMAL)
        self.recording_limit_hint.set("Sem parada automática")
        messagebox.showerror("Falha ao finalizar gravação", f"{message}\n\n{_log_hint()}")

    def _show_completed(self, output_path: Path) -> None:
        from record_transcript_resume.log import log
        log(f"GUI: _show_completed chamado -> {output_path.name}")
        self._set_recording_action_state(stop=tk.DISABLED, show_stop=False)
        self.device_info_text.set("")
        self._started_at = None
        self._recording_deadline = None
        self.recording_limit_hint.set("Sem parada automática")
        self._last_output = output_path
        self._sync_recording_meter()
        self.last_file.set(str(output_path))
        try:
            audio_size = output_path.stat().st_size
        except OSError:
            audio_size = 0
        if not output_path.is_file() or audio_size <= 0:
            if self.mode.get() == "system":
                message = (
                    "Nenhum som do computador foi capturado. Reproduza algum áudio durante a gravação "
                    "e tente novamente. Nenhum processamento será iniciado."
                )
            else:
                message = (
                    "A gravação foi finalizada, mas o arquivo de áudio não foi encontrado ou está vazio "
                    "na pasta escolhida. Nenhum processamento será iniciado."
                )
            self._show_stop_error(
                message
            )
            return
        self.status.set("Áudio salvo com segurança. Processe-o quando quiser pela Biblioteca.")
        self._refresh_library()
        self._set_recording_action_state(start=tk.NORMAL)
        self._set_capture_preferences_state(tk.NORMAL)
        self._refresh_compact_controls()
        options = self._recording_processing_options
        if options.get("output_mode") in {"transcription", "both"}:
            queued = self._queue_pipeline(
                output_path,
                str(options["language"]),
                str(options["model_size"]),
                str(options["provider"]),
                str(options["summary_template"]),
                output_mode=str(options["output_mode"]),
                additional_instructions=str(options["additional_instructions"]),
                transcription_provider=str(options["transcription_provider"]),
                separate_speakers=bool(options["separate_speakers"]),
                reuse_source_folder=True,
            )
            if queued:
                self._show_page("processing")

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
        self._focus_youtube_process_button.configure(state=tk.DISABLED)
        self.status.set("Baixando áudio do YouTube...")
        self.youtube_hint.set("Baixando e convertendo para MP3…")
        self._pack_global_processing_feedback(include_actions=False)
        self.progressbar.start()
        self._youtube_download_thread = threading.Thread(
            target=self._youtube_download_worker,
            args=(
                url, self.youtube_mode.get(), self._selected_summary_template_code(),
                RecorderApp._meeting_instructions(self),
            ),
            daemon=True,
        )
        self._youtube_download_thread.start()

    def _youtube_download_worker(
        self, url: str, selected_mode: str, selected_template: str, additional_instructions: str,
    ) -> None:
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
                on_status=lambda message: self._post_to_ui(self.status.set, message),
            )
        except Exception as exc:
            log(f"GUI: download do YouTube falhou: {type(exc).__name__}: {exc}")
            self._post_to_ui(self._on_youtube_download_error, str(exc))
            return
        self.after(
            0, self._on_youtube_download_done, audio_path, output_mode, selected_template,
            additional_instructions,
        )

    def _on_youtube_download_done(
        self, audio_path: Path, output_mode: str, selected_template: str, additional_instructions: str,
    ) -> None:
        self.youtube_hint.set("Áudio pronto. Iniciando processamento…")
        if self._queue_pipeline(
            audio_path,
            _LANG_CODES.get(self.pipeline_language.get(), "pt"),
            self.pipeline_model.get(),
            self._selected_summary_provider_code(),
            selected_template,
            output_mode=output_mode,
            output_dir=Path(self.output_dir.get()),
            additional_instructions=additional_instructions,
        ):
            self._show_page("processing")
        self.youtube_process_button.configure(state=tk.NORMAL)
        self._focus_youtube_process_button.configure(state=tk.NORMAL)

    def _on_youtube_download_error(self, message: str) -> None:
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self.status.set("Não foi possível baixar o áudio")
        self.youtube_hint.set("Não foi possível baixar. Verifique o link e tente novamente.")
        self._restore_after_processing()
        self._focus_youtube_process_button.configure(state=tk.NORMAL)
        messagebox.showerror("Download do YouTube não concluído", f"{message}\n\n{_log_hint()}")

    def _process_existing_media(self) -> None:
        path = filedialog.askopenfilename(
            title="Importar áudio ou vídeo para transcrever",
            filetypes=[
                ("Áudio e vídeo", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma *.mp4 *.m4v *.mov *.mkv *.webm *.avi"),
                ("Arquivos de vídeo", "*.mp4 *.m4v *.mov *.mkv *.webm *.avi"),
                ("Arquivos de áudio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma"),
                ("Todos os arquivos", "*.*"),
            ],
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if not path:
            return
        mp3_path = Path(path)
        label = self.file_pipeline_language.get()
        lang_code = _LANG_CODES.get(label, "pt")
        model_size = self.file_pipeline_model.get()
        provider = self._summary_provider_code_for_label(self.file_summary_provider.get())
        summary_template = self._summary_template_code_for_choice(self.file_processing_profile.get(), "Reunião")
        transcription_provider = self._transcription_provider_code_for_label(self.file_transcription_source.get())
        if self._queue_pipeline(
            mp3_path, lang_code, model_size, provider, summary_template,
            output_dir=Path(self.output_dir.get() or default_output_dir()),
            transcription_provider=transcription_provider,
            separate_speakers=self.file_diarize_speakers.get(),
            preserve_source=True,
        ):
            self._show_page("processing")

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
        editor = self._active_import_text_editor()
        editor.delete("1.0", tk.END)
        editor.insert("1.0", content)

    def _active_import_text_editor(self) -> ctk.CTkTextbox:
        if self._focus_text_tools_visible and not self._maximized:
            return self._focus_import_text_editor
        return self.import_text_editor

    def _save_imported_text(self) -> Path | None:
        from record_transcript_resume.documents import create_imported_transcript

        editor = self._active_import_text_editor()
        text = editor.get("1.0", "end-1c")
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
        editor.delete("1.0", tk.END)
        self._refresh_library()
        return transcript_path

    def _save_imported_text_and_regenerate(self) -> None:
        transcript_path = self._save_imported_text()
        if transcript_path is None:
            return
        if self._focus_text_tools_visible and not self._maximized:
            self._focus_show_text_tools()
        else:
            self._toggle_text_import()
        self._open_summary_regeneration_dialog(transcript_path)

    def _queue_pipeline(
        self,
        mp3_path: Path,
        language: str,
        model_size: str,
        provider: str,
        summary_template: str,
        output_mode: str = "both",
        output_dir: Path | None = None,
        additional_instructions: str = "",
        transcription_provider: str | None = None,
        separate_speakers: bool | None = None,
        preserve_source: bool = False,
        reuse_source_folder: bool = False,
    ) -> bool:
        """Persist the job before doing any expensive work."""
        if not mp3_path.is_file():
            messagebox.showerror("Áudio não encontrado", f"Não foi possível encontrar:\n{mp3_path}")
            return False
        transcription_provider = transcription_provider or self._selected_transcription_provider_code()
        separate_speakers = self.diarize_speakers.get() if separate_speakers is None else separate_speakers
        if transcription_provider.startswith("api:") and not self._api_provider_has_token(transcription_provider.removeprefix("api:")):
            messagebox.showerror(
                "Token ausente",
                "O provider de transcrição selecionado não possui um token salvo. Use Editar em Ajustes para configurá-lo.",
            )
            return False
        job = self._job_store.enqueue(
            mp3_path, output_dir or mp3_path.parent, language, model_size, provider, summary_template, output_mode,
            transcription_provider, additional_instructions.strip(), separate_speakers, preserve_source,
            reuse_source_folder,
        )
        if additional_instructions.strip():
            self._clear_meeting_instructions()
        self.status.set(f"Processamento adicionado à fila: {mp3_path.name}")
        self._refresh_library()
        self._refresh_processing_page()
        self._run_next_pending_job()
        return True

    def _start_queued_job(self, job: ProcessingJob) -> None:
        step_total = f"1/{self._pipeline_total_steps(job.output_mode, job.separate_speakers)}"
        self.status.set(f"{step_total} · Preparando processamento")
        self.last_file.set(job.mp3_path)
        self._active_job_id = job.id
        self._start_pipeline(
            job.audio_path,
            language=job.language,
            model_size=job.model_size,
            provider=job.provider,
            summary_template=job.summary_template,
            output_mode=job.output_mode,
            transcription_provider=job.transcription_provider,
            additional_instructions=job.additional_instructions,
            separate_speakers=job.separate_speakers,
            output_dir=Path(job.output_dir),
            job_id=job.id,
            preserve_source=job.preserve_source,
            reuse_source_folder=job.reuse_source_folder,
        )

    def _resume_interrupted_jobs(self) -> None:
        """Resume audio that was safely queued before a restart or update."""
        jobs = self._job_store.recoverable()
        if not jobs:
            return
        self.status.set(f"Retomando {len(jobs)} tarefa(s) pendente(s)...")
        self._refresh_processing_page()
        self._run_next_pending_job()

    def _run_next_pending_job(self) -> None:
        if self._pipeline_thread is not None and self._pipeline_thread.is_alive():
            return
        job = next((item for item in self._job_store.list() if item.status == "queued"), None)
        if job is None:
            return
        self._start_queued_job(job)

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

        self._open_summary_regeneration_dialog(transcript_path)

    def _open_summary_regeneration_dialog(self, transcript_path: Path, *, job_id: str | None = None) -> None:
        """Let the user choose the next summary instruction before regenerating."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Gerar nova versão do resumo")
        self._fit_dialog(dialog, 620, 620, 460, 440)
        dialog.configure(fg_color=_COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()
        shell = ctk.CTkScrollableFrame(dialog, fg_color=_COLORS["surface"], corner_radius=16)
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            shell, text="Gerar nova versão do resumo", font=("Segoe UI", 15, "bold"),
            text_color=_COLORS["text"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(16, 2))
        ctk.CTkLabel(
            shell,
            text="A transcrição permanece intacta. O resumo atual só será substituído se a nova geração terminar com sucesso.",
            font=("Segoe UI", 10), text_color=_COLORS["muted"], anchor="w", justify=tk.LEFT,
            wraplength=560,
        ).pack(fill=tk.X, padx=16, pady=(0, 14))

        provider_value = tk.StringVar(value=self.summary_provider.get())
        profile_value = tk.StringVar(value=self.processing_profile.get())

        def field_label(text: str) -> None:
            ctk.CTkLabel(
                shell, text=text, font=("Segoe UI", 9, "bold"),
                text_color=_COLORS["muted"], anchor="w",
            ).pack(fill=tk.X, padx=16, pady=(0, 3))

        field_label("PROVIDER DO RESUMO")
        provider_selector = ctk.CTkComboBox(
            shell, variable=provider_value, values=self._summary_provider_options(), state="readonly",
            height=34, corner_radius=9, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        provider_selector.pack(fill=tk.X, padx=16, pady=(0, 9))

        field_label("FORMATO DO RESUMO")
        profile_selector = ctk.CTkComboBox(
            shell, variable=profile_value, values=self._summary_profile_options(), state="readonly",
            height=34, corner_radius=9, fg_color=_theme_color("#0D1525"), border_color=_theme_color("#2A3A58"),
            button_color=_theme_color("#263550"), button_hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            dropdown_fg_color=_theme_color("#162136"), dropdown_text_color=_COLORS["text"], font=("Segoe UI", 10),
        )
        profile_selector.pack(fill=tk.X, padx=16, pady=(0, 9))

        ctk.CTkLabel(
            shell, text="Escolha um formato nativo ou um perfil salvo. Para consultar ou editar prompts, use Ajustes › Resumos.",
            font=("Segoe UI", 9), text_color=_COLORS["brand_muted"], anchor="w", justify=tk.LEFT,
            wraplength=560,
        ).pack(fill=tk.X, padx=16, pady=(0, 10))

        field_label("AJUSTES DESTA NOVA VERSÃO (OPCIONAL)")
        instructions_editor = ctk.CTkTextbox(
            shell, height=92, corner_radius=9, fg_color=_theme_color("#0D1525"), border_width=1,
            border_color=_theme_color("#2A3A58"), text_color=_COLORS["text"], font=("Segoe UI", 10), wrap="word",
        )
        instructions_editor.pack(fill=tk.X, padx=16)
        instructions_editor.insert("1.0", RecorderApp._meeting_instructions(self))
        ctk.CTkLabel(
            shell, text="Ex.: reorganize por objetivos, destaque riscos e não inclua pontos sem evidência na transcrição.",
            font=("Segoe UI", 9), text_color=_COLORS["brand_muted"], anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(4, 12))

        def selected_template_code() -> str:
            return self._summary_template_code_for_choice(profile_value.get(), "Reunião")

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill=tk.X, padx=16, pady=(0, 16))
        ctk.CTkButton(
            actions, text="Cancelar", command=dialog.destroy, width=82, height=34, corner_radius=8,
            fg_color=_theme_color("#263550"), hover_color=_theme_color("#34476B"), text_color=_COLORS["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)

        def generate_summary() -> None:
            provider = self._api_provider_labels.get(
                provider_value.get(), _SUMMARY_PROVIDER_CODES.get(provider_value.get(), "codex"),
            )
            instructions = instructions_editor.get("1.0", "end-1c").strip()
            dialog.destroy()
            self._start_summary_retry(
                transcript_path, provider=provider, summary_template=selected_template_code(),
                additional_instructions=instructions, job_id=job_id,
            )

        ctk.CTkButton(
            actions, text="Gerar nova versão", command=generate_summary, height=34, corner_radius=8,
            fg_color=_COLORS["accent"], hover_color=_COLORS["accent_hover"], text_color=_COLORS["accent_text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _start_summary_retry(
        self,
        transcript_path: Path,
        *,
        provider: str | None = None,
        summary_template: str | None = None,
        additional_instructions: str | None = None,
        job_id: str | None = None,
    ) -> None:
        """Regenerate a saved summary, preserving the audio and transcription."""
        if self._pipeline_thread is not None and self._pipeline_thread.is_alive():
            messagebox.showinfo(
                "Processamento em andamento",
                "Há um processamento ativo. Você pode continuar usando o aplicativo; tente gerar este resumo quando a fila terminar.",
            )
            return
        provider = provider or self._selected_summary_provider_code()
        summary_template = summary_template or self._selected_summary_template_code()
        instructions_were_explicitly_chosen = additional_instructions is not None
        if additional_instructions is None:
            additional_instructions = RecorderApp._meeting_instructions(self)
        self.retry_summary_button.configure(state=tk.DISABLED)
        self.status.set("Gerando nova versão do resumo…")
        self.last_file.set(str(transcript_path.parent))
        self._show_summary_retry_progress()
        self._pipeline_thread = threading.Thread(
            target=self._retry_summary_worker,
            args=(transcript_path, provider, summary_template, additional_instructions, job_id),
            daemon=True,
        )
        self._pipeline_thread.start()
        if instructions_were_explicitly_chosen or additional_instructions:
            self._clear_meeting_instructions()
        self._tray.notify("Voice Notes", "Gerando uma nova versão do resumo em segundo plano.")

    def _retry_summary_worker(
        self, transcript_path: Path, provider: str, summary_template: str, additional_instructions: str,
        job_id: str | None,
    ) -> None:
        from record_transcript_resume.log import log
        from record_transcript_resume.pipeline import retry_summary

        log(f"GUI: retrying summary | file={transcript_path} provider={provider}")
        try:
            summary_path = retry_summary(
                transcript_path,
                provider=provider,  # type: ignore[arg-type]
                summary_template=summary_template,  # type: ignore[arg-type]
                additional_instructions=additional_instructions,
                on_status=lambda _message: self._post_to_ui(self._set_processing_status, "Gerando nova versão do resumo…"),
            )
        except Exception as exc:
            log(f"GUI: summary retry failed: {type(exc).__name__}: {exc}")
            self._post_to_ui(self._on_summary_retry_error, str(exc), job_id)
            return
        self._post_to_ui(self._on_summary_retry_done, summary_path, job_id)

    def _on_summary_retry_done(self, summary_path: Path, job_id: str | None = None) -> None:
        self.status.set("Resumo atualizado com sucesso")
        if job_id is not None:
            self._job_store.update(job_id, status="completed", stage="Resumo concluído", error="", summary_failed=False)
        self.last_file.set(str(summary_path.parent))
        self._restore_after_processing()
        self.youtube_process_button.configure(state=tk.NORMAL)
        self.retry_summary_button.configure(state=tk.NORMAL)
        self._refresh_library()
        self._refresh_processing_page()
        self._tray.notify("Resumo concluído", f"Nova versão salva em {summary_path.parent.name}.")

    def _on_summary_retry_error(self, message: str, job_id: str | None = None) -> None:
        self.status.set("Não foi possível gerar o resumo")
        if job_id is not None:
            self._job_store.update(job_id, status="warning", stage="Resumo ainda pendente", error=message)
            self._refresh_processing_page()
        self._restore_after_processing()
        self.retry_summary_button.configure(state=tk.NORMAL)
        self._tray.notify("Resumo não concluído", "Verifique o provider e tente gerar novamente.")
        messagebox.showerror(
            "Nova tentativa não concluída",
            f"{message}\n\nA transcrição foi preservada. Você pode corrigir o login ou trocar o provider e tentar novamente.\n\n{_log_hint()}",
        )

    def _restore_after_processing(self) -> None:
        """Hide global progress feedback without blocking unrelated app controls."""
        self._hide_cancellable_progress()
        self._refresh_compact_controls()

    def _pack_global_processing_feedback(self, *, include_actions: bool = True) -> None:
        """Place progress before the visible page, including focus-only pages."""
        anchor = next(
            (
                widget for widget in self._container.pack_slaves()
                if widget not in (self.progressbar, self._processing_actions)
            ),
            None,
        )
        progress_options: dict[str, object] = {"fill": tk.X, "padx": 20, "pady": (4, 0)}
        actions_options: dict[str, object] = {"fill": tk.X, "padx": 20, "pady": (7, 0)}
        if anchor is not None:
            progress_options["before"] = anchor
            actions_options["before"] = anchor
        self.progressbar.pack(**progress_options)
        if include_actions:
            self._processing_actions.pack(**actions_options)

    def _show_cancellable_progress(self) -> None:
        """Expose one deliberate escape route while the isolated worker starts."""
        self._processing_cancel_requested = False
        self._pipeline_process = None
        self._processing_started_at = time.monotonic()
        self._processing_activity = "Processando áudio"
        self._processing_feedback.set("Processando em segundo plano · o áudio salvo será preservado.")
        self._pack_global_processing_feedback()
        self.progressbar.start()
        self.cancel_processing_button.pack(side=tk.RIGHT)
        self.cancel_processing_button.configure(text="Preparando processamento…", state=tk.DISABLED)

    def _show_summary_retry_progress(self) -> None:
        """Provide clear progress while a provider generates a replacement summary."""
        self._processing_started_at = time.monotonic()
        self._processing_activity = "Gerando resumo"
        self._processing_feedback.set("Gerando nova versão em segundo plano · o resumo atual será preservado até concluir.")
        self._pack_global_processing_feedback()
        self.progressbar.start()
        self.cancel_processing_button.pack_forget()
        self.library_summary_progress_text.set("Gerando nova versão do resumo · 00:00")
        self._library_summary_progress.pack(
            fill=tk.X, padx=14, pady=(0, 7), after=self._library_queue_row,
        )
        self.library_summary_progressbar.start()

    def _set_processing_status(self, status: str) -> None:
        self.status.set(status)
        normalized = status.casefold()
        if "resumo" in normalized or "summary" in normalized:
            self._processing_activity = "Gerando resumo"
        elif "transcri" in normalized or "transcrib" in normalized:
            self._processing_activity = "Transcrevendo áudio"
        elif "falante" in normalized or "speaker" in normalized:
            self._processing_activity = "Separando falantes"

    def _hide_cancellable_progress(self) -> None:
        self.progressbar.stop()
        self.progressbar.pack_forget()
        self._processing_actions.pack_forget()
        self.cancel_processing_button.configure(text="Cancelar processamento", state=tk.DISABLED)
        self._pipeline_process = None
        self._processing_cancel_requested = False
        self._pipeline_has_speaker_separation = False
        self._processing_started_at = None
        self._processing_activity = ""
        self._processing_feedback.set("")
        if hasattr(self, "library_summary_progressbar"):
            self.library_summary_progressbar.stop()
            self._library_summary_progress.pack_forget()

    def _set_pipeline_process_ready(self, process: object) -> None:
        if self._processing_cancel_requested:
            return
        self._pipeline_process = process
        self.cancel_processing_button.configure(text="Cancelar processamento", state=tk.NORMAL)

    def _cancel_processing_shortcut(self, _event: tk.Event[tk.Misc] | None = None) -> str | None:
        if self._pipeline_process is None or self._processing_cancel_requested:
            return None
        self._request_cancel_processing()
        return "break"

    def _request_cancel_processing(self) -> None:
        process = self._pipeline_process
        if process is None or self._processing_cancel_requested:
            return
        if not messagebox.askyesno(
            "Cancelar processamento",
            "Interromper a transcrição ou geração do resumo agora?\n\nO áudio já salvo será preservado para você tentar novamente depois.",
        ):
            return
        self._processing_cancel_requested = True
        self.cancel_processing_button.configure(text="Cancelando…", state=tk.DISABLED)
        self.status.set("Cancelando processamento — preservando o áudio…")

        def stop_worker() -> None:
            from record_transcript_resume.windows_process import terminate_process_tree
            try:
                terminate_process_tree(process)  # type: ignore[arg-type]
            except Exception:
                # The worker also notices a normal process exit. The final UI
                # state below remains deterministic even if Windows already
                # removed the process before taskkill reaches it.
                pass

        threading.Thread(target=stop_worker, daemon=True).start()

    def _on_pipeline_cancelled(self, job_id: str | None = None) -> None:
        self.status.set("Processamento cancelado — áudio preservado")
        if job_id is not None:
            self._job_store.update(job_id, status="cancelled", stage="Cancelado", error="Interrompido pelo usuário")
        self._active_job_id = None
        self._restore_after_processing()
        self._refresh_library()
        self._refresh_processing_page()
        # The worker thread may still be returning while this callback runs.
        # Schedule a second queue check so later jobs are not stranded.
        self.after(80, self._run_next_pending_job)

    def _start_pipeline(
        self,
        mp3_path: Path,
        language: str | None,
        model_size: str = "small",
        provider: str = "codex",
        summary_template: str = "meeting",
        output_mode: str = "both",
        transcription_provider: str = "local",
        additional_instructions: str = "",
        separate_speakers: bool | None = None,
        output_dir: Path | None = None,
        job_id: str | None = None,
        preserve_source: bool = False,
        reuse_source_folder: bool = False,
    ) -> None:
        from record_transcript_resume.log import log, log_exception
        log(f"GUI: _start_pipeline | file={mp3_path.name} lang={language} model={model_size} provider={provider}")
        try:
            use_speaker_separation = self.diarize_speakers.get() if separate_speakers is None else separate_speakers
            self._pipeline_output_mode = output_mode
            total_steps = self._pipeline_total_steps(output_mode, use_speaker_separation)
            if job_id is not None:
                self._job_store.update(
                    job_id, status="running",
                    stage=f"1/{total_steps} · Preparando",
                )
            self._pipeline_has_speaker_separation = use_speaker_separation
            self._show_cancellable_progress()
            log("GUI: progressbar iniciada")

            def on_status(msg: str) -> None:
                from record_transcript_resume.log import log
                log(f"GUI: pipeline status -> {msg}")
                stage = self._pipeline_stage_label(msg)
                if job_id is not None:
                    self._job_store.update(job_id, status="running", stage=stage, error="")
                self._post_to_ui(self._set_processing_status, stage)
                self._post_to_ui(self._refresh_processing_page)

            self._pipeline_thread = threading.Thread(
                target=self._pipeline_worker,
                args=(mp3_path, output_dir or mp3_path.parent, language or "pt", model_size, provider, summary_template, output_mode, transcription_provider, additional_instructions, use_speaker_separation, self.huggingface_token.get(), job_id, on_status, preserve_source, reuse_source_folder),
                daemon=True,
            )
            self._pipeline_thread.start()
            log("GUI: pipeline thread iniciada")
        except Exception as exc:
            log_exception("GUI: ERRO em _start_pipeline", exc)
            self._hide_cancellable_progress()
            self._restore_after_processing()
            self.status.set("Pipeline error")
            if job_id is not None:
                self._job_store.update(job_id, status="failed", stage="Falhou ao iniciar", error=str(exc))
            messagebox.showerror("Pipeline error", f"{exc}\n\n{_log_hint()}")

    @staticmethod
    def _pipeline_total_steps(output_mode: str, separate_speakers: bool) -> int:
        return 2 + int(separate_speakers) + int(output_mode != "transcription")

    def _pipeline_stage_label(self, message: str) -> str:
        normalized = message.casefold()
        total = self._pipeline_total_steps(self._pipeline_output_mode, self._pipeline_has_speaker_separation)
        if "transcrib" in normalized:
            return f"1/{total} · Transcrevendo áudio"
        if "identifying speaker" in normalized or "separando falante" in normalized:
            return f"2/{total} · Separando falantes"
        if "summary" in normalized or "resumo" in normalized or "synthes" in normalized:
            step = 2 + int(self._pipeline_has_speaker_separation)
            return f"{step}/{total} · Criando resumo"
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
        transcription_provider: str,
        additional_instructions: str,
        diarize_speakers: bool,
        huggingface_token: str,
        job_id: str | None,
        on_status: object,
        preserve_source: bool,
        reuse_source_folder: bool,
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
                self._post_to_ui(self._on_pipeline_error, "Informe o token gratuito do Hugging Face em Ajustes para separar falantes.", job_id)
                return
            try:
                import keyring
                keyring.set_password("Voice Notes", "huggingface-token", huggingface_token.strip())
            except Exception:
                pass
            env["VOICE_NOTES_HF_TOKEN"] = huggingface_token.strip()
        pipeline_args = [
            str(mp3_path), str(output_dir), language, model_size, provider, summary_template,
            "1" if diarize_speakers else "0", output_mode, transcription_provider,
            additional_instructions, "1" if preserve_source else "0",
            "1" if reuse_source_folder else "0",
        ]
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
            self._post_to_ui(self._on_pipeline_error, str(exc), job_id)
            return
        self._post_to_ui(self._set_pipeline_process_ready, proc)

        def _drain_stderr() -> None:
            for line in proc.stderr:
                stripped = line.rstrip()
                if stripped:
                    log(f"GUI: pipeline stderr: {stripped[:200]}")

        threading.Thread(target=_drain_stderr, daemon=True).start()

        result_event = None
        error_msg = None
        error_type = ""

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
                error_type = str(event.get("error_type", "")).strip()

        proc.wait()

        if self._processing_cancel_requested:
            log("GUI: pipeline cancelado pelo usuário")
            self._post_to_ui(self._on_pipeline_cancelled, job_id)
        elif result_event is not None:
            from record_transcript_resume.pipeline import PipelineResult
            result = PipelineResult(
                folder=Path(result_event["folder"]),
                mp3_path=Path(result_event["mp3"]),
                transcript_path=Path(result_event["transcript"]) if result_event.get("transcript") else None,
                summary_path=Path(result_event["summary"]) if result_event.get("summary") else None,
                warnings=tuple(str(item) for item in result_event.get("warnings", []) if str(item).strip()),
                summary_failed=bool(result_event.get("summary_failed", False)),
            )
            log(f"GUI: pipeline concluido -> {result.folder.name}")
            self._post_to_ui(self._on_pipeline_done, result, job_id)
        elif error_msg is not None:
            if error_type:
                error_msg = f"{error_type}: {error_msg}"
            log(f"GUI: pipeline retornou erro: {error_msg}")
            self._post_to_ui(self._on_pipeline_error, error_msg, job_id)
        elif proc.returncode != 0:
            log(f"GUI: subprocess do pipeline encerrou com crash (code={proc.returncode})")
            self._post_to_ui(self._on_pipeline_error,
                       f"Pipeline encerrou inesperadamente (codigo={proc.returncode}). Verifique o log.", job_id)
        else:
            log("GUI: subprocess do pipeline encerrou sem resultado")
            self._post_to_ui(self._on_pipeline_error, "Pipeline encerrou sem resultado.", job_id)

    def _on_pipeline_done(self, result: object, job_id: str | None = None) -> None:
        from record_transcript_resume.log import log
        from record_transcript_resume.pipeline import PipelineResult
        assert isinstance(result, PipelineResult)
        log(f"GUI: _on_pipeline_done | folder={result.folder.name}")
        self.progressbar.stop()
        self.progressbar.pack_forget()
        completed_stage = self._pipeline_total_steps(self._pipeline_output_mode, self._pipeline_has_speaker_separation)
        if result.warnings:
            self.status.set(f"Concluído com aviso: {result.folder.name}")
            self._tray.notify("Processamento concluído com aviso", result.warnings[0])
        else:
            self.status.set(f"{completed_stage}/{completed_stage} · Concluído: {result.folder.name}")
        self.last_file.set(str(result.folder))
        if job_id is not None:
            original_job = next((job for job in self._job_store.list() if job.id == job_id), None)
            if original_job is not None:
                try:
                    self._library_metadata.transfer(
                        original_job.audio_path, result.mp3_path,
                        keep_source=original_job.preserve_source,
                    )
                except OSError:
                    pass
            stage = "Concluído com aviso" if result.warnings else f"{completed_stage}/{completed_stage} · Concluído"
            self._job_store.update(
                job_id,
                status="warning" if result.warnings else "completed",
                stage=stage,
                error="\n".join(result.warnings),
                mp3_path=str(result.mp3_path),
                output_dir=str(result.folder),
                summary_failed=result.summary_failed,
            )
        self._active_job_id = None
        self._restore_after_processing()
        self._refresh_library()
        self._refresh_processing_page()
        self.after(120, self._run_next_pending_job)

    def _on_pipeline_error(self, message: str, job_id: str | None = None) -> None:
        from record_transcript_resume.log import log
        log(f"GUI: _on_pipeline_error | {message[:120]}")
        self.progressbar.stop()
        self.progressbar.pack_forget()
        current_stage = self.status.get()
        active_job = next(
            (job for job in self._job_store.list() if job.id == job_id), None,
        ) if job_id is not None else None
        stage_context = " ".join((current_stage, active_job.stage if active_job is not None else "")).casefold()
        if "transcrev" in stage_context or "preparando processamento" in stage_context:
            failure_stage = "Falha ao transcrever o áudio"
        elif "resumo" in stage_context or "criando" in stage_context or "summar" in stage_context:
            failure_stage = "Falha ao gerar o resumo"
        elif "falante" in stage_context or "speaker" in stage_context:
            failure_stage = "Falha ao identificar falantes"
        else:
            failure_stage = "Falha no processamento"
        self.status.set(f"{failure_stage} — áudio preservado")
        if job_id is not None:
            self._job_store.update(job_id, status="failed", stage=failure_stage, error=message)
        self._active_job_id = None
        self._restore_after_processing()
        self._refresh_library()
        self._refresh_processing_page()
        self.after(120, self._run_next_pending_job)
        saved_audio = self._last_output
        if job_id is not None:
            failed_job = next((job for job in self._job_store.list() if job.id == job_id), None)
            if failed_job is not None:
                saved_audio = failed_job.audio_path
        location = f"\n\nSeu áudio foi preservado em:\n{saved_audio}" if saved_audio else ""
        if job_id is not None:
            short_error = message.replace("\n", " ").strip()
            self._tray.notify(
                "Processamento exige atenção",
                f"{failure_stage}: {short_error[:150] or 'consulte os detalhes em Processos'}",
            )
            return
        messagebox.showerror(
            "Processamento não concluído",
            f"{failure_stage}.\n\nDetalhes:\n{message}{location}\n\n{_log_hint()}",
        )

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
            canvas.create_line(4, baseline, width - 4, baseline, fill=_theme_color("#263653"), width=1)
            for index in range(bars):
                source_index = min(15, round(index * 15 / max(1, bars - 1)))
                x0 = gap + index * (bar_width + gap)
                x1 = x0 + bar_width
                level = self._eq_smooth[source_index]
                bar_height = int(level * max_height)
                canvas.create_rectangle(x0, baseline - 2, x1, baseline, fill=_theme_color("#263653"), outline="")
                if bar_height > 0:
                    canvas.create_rectangle(x0, baseline - bar_height, x1, baseline, fill=_COLORS["accent"], outline="")
                peak_y = baseline - int(self._eq_peaks[source_index] * max_height) - 1
                if self._eq_peaks[source_index] > 0.02:
                    canvas.create_rectangle(x0, peak_y, x1, peak_y + 2, fill=_theme_color("#E9ECFF"), outline="")

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
        elif self._processing_started_at is not None:
            seconds = int(time.monotonic() - self._processing_started_at)
            duration = self._format_duration(seconds)
            self.elapsed.set(duration)
            activity = self._processing_activity or "Processando"
            self.recording_limit_hint.set(f"{activity} há {duration} · você pode minimizar ou ocultar o app.")
            self._processing_feedback.set(f"{activity} em segundo plano há {duration}.")
            if hasattr(self, "library_summary_progress_text"):
                self.library_summary_progress_text.set(f"{activity} · {duration} · em segundo plano")
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
        self._set_recording_action_state(stop=tk.DISABLED)
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
        if self._local_transcription_test_running or self._provider_test_running:
            return "teste de funcionamento"
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
        self._close_browser_audio()
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
    parser.add_argument("--diagnostics-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("pipeline_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.pipeline_worker:
        from record_transcript_resume._pipeline_proc import main as pipeline_main

        return pipeline_main(args.pipeline_args)
    if args.diagnostics_worker:
        from record_transcript_resume._diagnostics_proc import main as diagnostics_main

        return diagnostics_main(args.pipeline_args)
    app = RecorderApp(start_hidden=args.start_hidden)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
