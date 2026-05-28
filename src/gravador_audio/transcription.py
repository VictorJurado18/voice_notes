from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from gravador_audio.errors import TranscriptionError

_ALL_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]


def _hf_cache_dir() -> Path:
    if env := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        return Path(env)
    if env := os.environ.get("HF_HOME"):
        return Path(env) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def available_models() -> list[str]:
    """Returns faster-whisper models already present in the HuggingFace cache.
    Always includes 'small' as minimum fallback."""
    cache = _hf_cache_dir()
    found: list[str] = []
    for name in _ALL_MODELS:
        snapshots = cache / f"models--Systran--faster-whisper-{name}" / "snapshots"
        try:
            if snapshots.exists() and any(snapshots.iterdir()):
                found.append(name)
        except OSError:
            pass
    if "small" not in found:
        found.insert(0, "small")
    return found


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def transcribe(
    audio_path: Path, language: str = "pt", model_size: str = "small"
) -> list[Segment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper nao instalado. Execute: pip install faster-whisper"
        ) from exc

    from gravador_audio.log import log
    log(f"Transcricao iniciada | modelo={model_size} idioma={language} arquivo={audio_path.name}")

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        raw_segments, _ = model.transcribe(str(audio_path), language=language)
        return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segments]
    except Exception as exc:
        raise TranscriptionError(f"Falha na transcricao: {exc}") from exc


def segments_to_markdown(segments: list[Segment]) -> str:
    lines: list[str] = []
    for seg in segments:
        h = int(seg.start // 3600)
        m = int((seg.start % 3600) // 60)
        s = int(seg.start % 60)
        timestamp = f"[{h:02d}:{m:02d}:{s:02d}]"
        lines.append(f"{timestamp} {seg.text}")
    return "\n".join(lines)
