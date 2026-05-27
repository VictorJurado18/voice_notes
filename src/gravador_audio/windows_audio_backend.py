from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gravador_audio.audio_backend import AudioBackend
from gravador_audio.errors import AudioBackendUnavailableError, RecordingError


@dataclass(frozen=True)
class WindowsAudioBackendConfig:
    sample_rate: int = 48_000
    channels: int = 2
    bit_rate_kbps: int = 192
    chunk_seconds: float = 0.2
    capture_microphone: bool = True
    capture_system_audio: bool = True


class WindowsAudioBackend(AudioBackend):
    """Records Windows microphone and speaker loopback audio to MP3."""

    _N_BANDS = 16

    def __init__(self, config: WindowsAudioBackendConfig | None = None) -> None:
        self._config = config or WindowsAudioBackendConfig()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._eq_levels: list[float] = [0.0] * self._N_BANDS

    @property
    def eq_levels(self) -> list[float]:
        return self._eq_levels

    def start(self, output_path: Path) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RecordingError("Ja existe uma captura de audio em andamento.")

        soundcard, lameenc, numpy = self._load_dependencies()
        microphone, loopback = self._resolve_devices(soundcard)

        self._stop_event.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._record_loop,
            args=(output_path, soundcard, lameenc, numpy, microphone, loopback),
            name="windows-audio-recorder",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return None

        self._stop_event.set()
        self._thread.join()
        self._thread = None

        if self._error is not None:
            raise RecordingError(f"Falha durante captura de audio: {self._error}")

        return None

    def _load_dependencies(self) -> tuple[Any, Any, Any]:
        try:
            import lameenc
            import numpy
            import soundcard
        except ImportError as exc:
            raise AudioBackendUnavailableError(
                "Dependencias de audio nao instaladas. Instale soundcard e lameenc."
            ) from exc

        return soundcard, lameenc, numpy

    def _resolve_devices(self, soundcard: Any) -> tuple[Any | None, Any | None]:
        microphone = None
        loopback = None

        if self._config.capture_microphone:
            microphone = soundcard.default_microphone()
            if microphone is None:
                raise AudioBackendUnavailableError("Microfone padrao nao encontrado.")

        if self._config.capture_system_audio:
            speaker = soundcard.default_speaker()
            if speaker is None:
                raise AudioBackendUnavailableError("Dispositivo de saida padrao nao encontrado.")
            loopback = soundcard.get_microphone(speaker.name, include_loopback=True)
            if loopback is None:
                raise AudioBackendUnavailableError(
                    "Loopback do audio do sistema nao encontrado para o speaker padrao."
                )

        if microphone is None and loopback is None:
            raise AudioBackendUnavailableError("Nenhuma fonte de audio habilitada.")

        return microphone, loopback

    def _record_loop(
        self,
        output_path: Path,
        soundcard: Any,
        lameenc: Any,
        numpy: Any,
        microphone: Any | None,
        loopback: Any | None,
    ) -> None:
        del soundcard
        chunk_frames = max(1, int(self._config.sample_rate * self._config.chunk_seconds))
        encoder = self._build_encoder(lameenc)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as file:
                mic_context = (
                    microphone.recorder(
                        samplerate=self._config.sample_rate,
                        channels=self._config.channels,
                        blocksize=chunk_frames,
                    )
                    if microphone is not None
                    else None
                )
                loop_context = (
                    loopback.recorder(
                        samplerate=self._config.sample_rate,
                        channels=self._config.channels,
                        blocksize=chunk_frames,
                    )
                    if loopback is not None
                    else None
                )

                with _optional_context(mic_context) as mic_recorder, _optional_context(
                    loop_context
                ) as loop_recorder:
                    while not self._stop_event.is_set():
                        chunks = []
                        if mic_recorder is not None:
                            chunks.append(mic_recorder.record(numframes=chunk_frames))
                        if loop_recorder is not None:
                            chunks.append(loop_recorder.record(numframes=chunk_frames))

                        mixed = self._mix_chunks(numpy, chunks)
                        try:
                            self._update_eq_levels(numpy, mixed)
                        except Exception:
                            pass
                        pcm = self._float_to_pcm16(numpy, mixed)
                        encoded = encoder.encode(pcm)
                        if encoded:
                            file.write(encoded)

                remaining = encoder.flush()
                if remaining:
                    file.write(remaining)
        except BaseException as exc:  # thread boundary: re-raise from stop()
            self._error = exc

    def _update_eq_levels(self, numpy: Any, mixed: Any) -> None:
        mono = mixed[:, 0] if mixed.ndim == 2 else mixed
        n = len(mono)
        if n == 0:
            return
        mono = numpy.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)
        fft = numpy.abs(numpy.fft.rfft(mono))
        n_fft = len(fft)
        bands: list[float] = []
        for i in range(self._N_BANDS):
            lo = int(n_fft * (i / self._N_BANDS) ** 1.8)
            hi = int(n_fft * ((i + 1) / self._N_BANDS) ** 1.8)
            hi = max(hi, lo + 1, n_fft - 1)
            hi = min(hi, n_fft)
            val = float(numpy.mean(fft[lo:hi]))
            bands.append(val if numpy.isfinite(val) else 0.0)
        peak = max(bands) if bands else 0.0
        if peak <= 0.0:
            self._eq_levels = [0.0] * self._N_BANDS
            return
        self._eq_levels = [min(1.0, b / peak) for b in bands]

    def _build_encoder(self, lameenc: Any) -> Any:
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(self._config.bit_rate_kbps)
        encoder.set_in_sample_rate(self._config.sample_rate)
        encoder.set_out_sample_rate(self._config.sample_rate)
        encoder.set_channels(self._config.channels)
        encoder.set_quality(2)
        return encoder

    def _mix_chunks(self, numpy: Any, chunks: list[Any]) -> Any:
        if not chunks:
            return numpy.zeros((0, self._config.channels), dtype=numpy.float32)

        normalized = [self._ensure_channels(numpy, chunk) for chunk in chunks]
        min_frames = min(chunk.shape[0] for chunk in normalized)
        aligned = [chunk[:min_frames] for chunk in normalized]
        mixed = sum(aligned) / len(aligned)
        return numpy.clip(mixed, -1.0, 1.0)

    def _ensure_channels(self, numpy: Any, chunk: Any) -> Any:
        array = numpy.asarray(chunk, dtype=numpy.float32)
        if array.ndim == 1:
            array = array.reshape((-1, 1))

        current_channels = array.shape[1]
        if current_channels == self._config.channels:
            return array
        if current_channels == 1 and self._config.channels == 2:
            return numpy.repeat(array, 2, axis=1)
        if current_channels > self._config.channels:
            return array[:, : self._config.channels]

        padding = numpy.zeros(
            (array.shape[0], self._config.channels - current_channels),
            dtype=numpy.float32,
        )
        return numpy.concatenate([array, padding], axis=1)

    def _float_to_pcm16(self, numpy: Any, chunk: Any) -> bytes:
        scaled = numpy.clip(chunk, -1.0, 1.0) * 32767
        return scaled.astype(numpy.int16).tobytes()


class _optional_context:
    def __init__(self, context: Any | None) -> None:
        self._context = context

    def __enter__(self) -> Any | None:
        if self._context is None:
            return None
        return self._context.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        if self._context is None:
            return None
        return self._context.__exit__(exc_type, exc, traceback)
