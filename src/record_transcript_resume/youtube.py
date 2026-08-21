"""Authorized YouTube audio download helpers used by the desktop widget."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from record_transcript_resume.errors import RecordingError


def normalize_youtube_url(url: str) -> str:
    """Accept copied YouTube links even when the scheme was omitted."""
    value = url.strip()
    if value and "://" not in value:
        return f"https://{value}"
    return value


def is_supported_youtube_url(url: str) -> bool:
    """Return whether *url* points to a normal YouTube video host."""
    try:
        host = (urlparse(normalize_youtube_url(url)).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return False
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _friendly_download_error(message: str) -> str:
    """Turn common yt-dlp failures into an actionable message in Portuguese."""
    normalized = message.casefold()
    if "sign in to confirm" in normalized or "not a bot" in normalized:
        return (
            "O YouTube bloqueou este download para confirmação de acesso. "
            "Tente novamente mais tarde ou use um vídeo público sem essa restrição."
        )
    if "private video" in normalized:
        return "Este vídeo é privado. Use um vídeo público ou entre na conta que possui acesso."
    if "video unavailable" in normalized or "this video is not available" in normalized:
        return "Este vídeo não está disponível no YouTube. Confira o link e a disponibilidade."
    if "drm protected" in normalized:
        return "Este vídeo é protegido pelo YouTube e não disponibiliza áudio para download."
    if "ffmpeg" in normalized:
        return "Não foi possível converter o áudio. Reinstale o Voice Notes para restaurar o conversor de MP3."
    return message or "Não foi possível baixar o áudio deste vídeo."


def download_audio(url: str, destination: Path, on_status: object = None) -> Path:
    """Download an authorized video as MP3 without invoking a shell command."""
    url = normalize_youtube_url(url)
    if not is_supported_youtube_url(url):
        raise RecordingError("Use um link válido do youtube.com ou youtu.be.")
    try:
        import imageio_ffmpeg
        import yt_dlp
    except ImportError as exc:
        raise RecordingError("O suporte a YouTube não está instalado nesta versão.") from exc

    destination.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())

    def notify(message: str) -> None:
        if callable(on_status):
            on_status(message)

    def hook(event: dict[str, object]) -> None:
        if event.get("status") == "downloading":
            percent = str(event.get("_percent_str", "")).strip()
            notify(f"Baixando áudio do YouTube{f' · {percent}' if percent else '…'}")
        elif event.get("status") == "finished":
            notify("Convertendo áudio para MP3…")

    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "outtmpl": str(destination / "%(title).120B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        # imageio-ffmpeg distributes a versioned executable name, so pass the
        # executable itself instead of its directory (which has no ffmpeg.exe).
        "ffmpeg_location": str(ffmpeg_path),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            if not isinstance(info, dict):
                raise RecordingError("O YouTube não retornou informações válidas sobre o vídeo.")
            original_name = Path(downloader.prepare_filename(info))
    except Exception as exc:
        message = str(exc).strip()
        raise RecordingError(_friendly_download_error(message)) from exc

    mp3_path = original_name.with_suffix(".mp3")
    if not mp3_path.is_file():
        raise RecordingError("A conversão para MP3 não produziu um arquivo válido.")
    return mp3_path
