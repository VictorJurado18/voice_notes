from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gravador_audio.errors import TranscriptionError

_MODEL_SIZE = "small"


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def transcribe(audio_path: Path, language: str = "pt") -> list[Segment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper nao instalado. Execute: pip install faster-whisper"
        ) from exc

    try:
        model = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
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
