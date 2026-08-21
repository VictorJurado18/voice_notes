"""Optional local speaker diarization using pyannote's community model."""
from __future__ import annotations

from pathlib import Path

from record_transcript_resume.errors import TranscriptionError

MODEL_ID = "pyannote/speaker-diarization-community-1"


def diarize(audio_path: Path, token: str) -> list[tuple[float, float, str]]:
    if not token.strip():
        raise TranscriptionError("A separação de falantes precisa de um token gratuito do Hugging Face.")
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise TranscriptionError("O suporte de separação de falantes não está instalado nesta versão.") from exc
    try:
        pipeline = Pipeline.from_pretrained(MODEL_ID, token=token.strip())
        output = pipeline(_audio_as_waveform(audio_path))
        annotation = getattr(output, "exclusive_speaker_diarization", None)
        if annotation is None:
            annotation = output.speaker_diarization
        return [(float(turn.start), float(turn.end), str(speaker)) for turn, speaker in annotation]
    except Exception as exc:
        raise TranscriptionError(f"Não foi possível separar os falantes: {exc}") from exc


def _audio_as_waveform(audio_path: Path) -> dict[str, object]:
    """Decode with bundled PyAV, avoiding a separate system FFmpeg install."""
    try:
        import av
        import numpy as np
        import torch
    except ImportError as exc:
        raise TranscriptionError("Dependências de áudio da separação de falantes estão indisponíveis.") from exc
    try:
        container = av.open(str(audio_path))
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
        chunks: list[object] = []
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                chunks.append(converted.to_ndarray())
        for converted in resampler.resample(None):
            chunks.append(converted.to_ndarray())
        container.close()
        if not chunks:
            raise ValueError("o arquivo não possui áudio decodificável")
        waveform = np.concatenate(chunks, axis=1).astype("float32", copy=False)
        return {"waveform": torch.from_numpy(waveform), "sample_rate": 16000}
    except Exception as exc:
        raise TranscriptionError(f"Não foi possível decodificar o áudio para separar os falantes: {exc}") from exc
