from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from record_transcript_resume.errors import TranscriptionError

# Modelos multilíngues disponíveis pelo faster-whisper.  O large-v2 foi
# substituído por large-v3 na interface para evitar uma escolha redundante.
_ALL_MODELS = ["tiny", "base", "small", "medium", "large-v3"]


def _hf_cache_dir() -> Path:
    if env := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        return Path(env)
    if env := os.environ.get("HF_HOME"):
        return Path(env) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def available_models() -> list[str]:
    """Returns the model choices shown to the user.

    faster-whisper downloads a selected model automatically on first use, so
    hiding models that are not cached makes valid options look unavailable.
    """
    return list(_ALL_MODELS)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


def transcribe(
    audio_path: Path, language: str = "pt", model_size: str = "small"
) -> list[Segment]:
    if not audio_path.is_file():
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper not installed. Run: pip install faster-whisper"
        ) from exc

    from record_transcript_resume.log import log
    log(f"Transcription started | model={model_size} language={language} file={audio_path.name}")

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        raw_segments, _ = model.transcribe(str(audio_path), language=language)
        return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segments]
    except Exception as exc:
        raise TranscriptionError(f"Transcription failed: {exc}") from exc


def segments_to_markdown(segments: list[Segment]) -> str:
    lines: list[str] = []
    for seg in segments:
        h = int(seg.start // 3600)
        m = int((seg.start % 3600) // 60)
        s = int(seg.start % 60)
        timestamp = f"[{h:02d}:{m:02d}:{s:02d}]"
        prefix = f"**{seg.speaker}** · " if seg.speaker else ""
        lines.append(f"{timestamp} {prefix}{seg.text}")
    return "\n".join(lines)


def assign_speakers(segments: list[Segment], turns: list[tuple[float, float, str]]) -> list[Segment]:
    """Assign every Whisper segment to the diarized voice with most overlap."""
    speaker_labels: dict[str, str] = {}
    labeled: list[Segment] = []
    for segment in segments:
        overlaps: dict[str, float] = {}
        for start, end, speaker in turns:
            overlap = max(0.0, min(segment.end, end) - max(segment.start, start))
            if overlap:
                overlaps[speaker] = overlaps.get(speaker, 0.0) + overlap
        if not overlaps:
            labeled.append(segment)
            continue
        raw_speaker = max(overlaps, key=overlaps.get)
        label = speaker_labels.setdefault(raw_speaker, f"Pessoa {len(speaker_labels) + 1}")
        labeled.append(replace(segment, speaker=label))
    return labeled
