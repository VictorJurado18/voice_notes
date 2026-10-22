from __future__ import annotations

import os
import tempfile
import wave
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
    audio_path: Path, language: str = "pt", model_size: str = "small", provider: str = "local"
) -> list[Segment]:
    if not audio_path.is_file():
        raise TranscriptionError(f"Arquivo de áudio não encontrado: {audio_path}")
    if provider.startswith("api:"):
        from record_transcript_resume.api_provider import transcribe_audio

        try:
            return [segment for segment in transcribe_audio(audio_path, language, provider.removeprefix("api:")) if isinstance(segment, Segment)]
        except Exception as exc:
            raise TranscriptionError(str(exc)) from exc
    if provider != "local":
        raise TranscriptionError(f"Unsupported transcription provider: {provider}")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "O componente Whisper local não está instalado. Reinstale o Voice Notes para restaurá-lo."
        ) from exc

    from record_transcript_resume.log import log
    log(f"Transcription started | model={model_size} language={language} file={audio_path.name}")

    try:
        from record_transcript_resume.resource_policy import transcription_threads
        model = WhisperModel(model_size, device="cpu", compute_type="int8",
                             cpu_threads=transcription_threads(), num_workers=1)
        # Meetings often contain long pauses. The library's conservative VAD
        # skips only silence longer than two seconds, preserving spoken content
        # and timestamps while avoiding needless CPU inference over silence.
        raw_segments, _ = model.transcribe(
            str(audio_path), language=language, vad_filter=True,
        )
        return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segments]
    except Exception as exc:
        technical_detail = str(exc).strip() or type(exc).__name__
        if "unable to open file 'model.bin'" in technical_detail.casefold():
            explanation = (
                f"Não foi possível abrir os arquivos do modelo Whisper '{model_size}'. "
                "O modelo pode estar incompleto, bloqueado ou inacessível. "
                "Em Ajustes > Transcrição, clique em Testar modelo; se o teste falhar, "
                "confira a conexão com a internet e o espaço livre e tente novamente."
            )
        elif isinstance(exc, MemoryError):
            explanation = (
                f"A memória disponível não foi suficiente para transcrever com o modelo '{model_size}'. "
                "Escolha um modelo menor em Ajustes > Transcrição e tente novamente."
            )
        else:
            explanation = f"Falha ao transcrever o áudio com o modelo Whisper '{model_size}'."
        raise TranscriptionError(f"{explanation}\nDetalhe técnico: {technical_detail}") from exc


def test_local_transcription(model_size: str = "small") -> None:
    """Load the selected local model and run a short, private audio smoke check.

    The generated silent WAV lives in a temporary directory and is removed when
    the check finishes. The model may be downloaded on first use, just like a
    normal transcription.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper não está instalado. Reinstale o Voice Notes para restaurar o Whisper local."
        ) from exc

    try:
        with tempfile.TemporaryDirectory(prefix="voice-notes-whisper-check-") as temp_dir:
            sample_path = Path(temp_dir) / "silence.wav"
            with wave.open(str(sample_path), "wb") as sample:
                sample.setnchannels(1)
                sample.setsampwidth(2)
                sample.setframerate(16_000)
                sample.writeframes(b"\x00\x00" * 16_000)

            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, _info = model.transcribe(
                str(sample_path), language="pt", beam_size=1, vad_filter=False,
            )
            # faster-whisper performs inference lazily; consume its iterator so
            # this check covers model loading and an actual decode pass.
            for _segment in segments:
                pass
    except Exception as exc:
        raise TranscriptionError(
            f"O teste do Whisper local ({model_size}) falhou: {type(exc).__name__}: {exc}"
        ) from exc


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
