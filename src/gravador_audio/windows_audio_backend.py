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


@dataclass(frozen=True)
class _DeviceSpec:
    index: int
    name: str
    channels: int
    rate: int


class WindowsAudioBackend(AudioBackend):
    """Records Windows microphone and speaker loopback audio to MP3 via pyaudiowpatch."""

    _N_BANDS = 16

    def __init__(self, config: WindowsAudioBackendConfig | None = None) -> None:
        self._config = config or WindowsAudioBackendConfig()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._eq_levels: list[float] = [0.0] * self._N_BANDS
        self._device_names: dict[str, str] = {}

    @property
    def eq_levels(self) -> list[float]:
        return self._eq_levels

    @property
    def device_names(self) -> dict[str, str]:
        return dict(self._device_names)

    @property
    def is_thread_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def thread_error(self) -> str | None:
        if self._error is None:
            return None
        exc = self._error
        detail = str(exc).strip() or repr(exc)
        return f"{type(exc).__name__}: {detail}"

    def start(self, output_path: Path) -> None:
        from gravador_audio.log import log
        if self._thread is not None and self._thread.is_alive():
            raise RecordingError("Ja existe uma captura de audio em andamento.")

        lameenc, numpy = self._load_dependencies()
        mic_spec, loopback_spec = self._resolve_devices()
        log(f"Dispositivos resolvidos | {self._device_names}")

        self._stop_event.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._record_loop,
            args=(output_path, lameenc, numpy, mic_spec, loopback_spec),
            name="windows-audio-recorder",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        from gravador_audio.log import log
        if self._thread is None:
            return None

        log("stop() chamado — aguardando thread finalizar")
        self._stop_event.set()
        self._thread.join()
        self._thread = None

        if self._error is not None:
            exc = self._error
            detail = str(exc).strip() or repr(exc)
            raise RecordingError(f"Falha durante captura de audio: {type(exc).__name__}: {detail}")

        return None

    def _load_dependencies(self) -> tuple[Any, Any]:
        try:
            import lameenc
            import numpy
        except ImportError as exc:
            raise AudioBackendUnavailableError(
                "Dependencias de audio nao instaladas. Instale lameenc e numpy."
            ) from exc
        return lameenc, numpy

    def _resolve_devices(self) -> tuple[_DeviceSpec | None, _DeviceSpec | None]:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as exc:
            raise AudioBackendUnavailableError(
                "pyaudiowpatch nao instalado. Execute: pip install pyaudiowpatch"
            ) from exc

        from gravador_audio.log import log

        p = pyaudio.PyAudio()
        names: dict[str, str] = {}
        mic_spec: _DeviceSpec | None = None
        loopback_spec: _DeviceSpec | None = None

        try:
            # WASAPI é usado para mic e loopback — garante taxa de amostragem correta
            try:
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            except OSError as exc:
                raise AudioBackendUnavailableError("WASAPI nao disponivel neste sistema.") from exc

            if self._config.capture_microphone:
                mic_idx = wasapi_info["defaultInputDevice"]
                if mic_idx < 0:
                    raise AudioBackendUnavailableError("Microfone padrao WASAPI nao encontrado.")
                info = p.get_device_info_by_index(mic_idx)
                channels = min(self._config.channels, int(info["maxInputChannels"]))
                rate = int(info["defaultSampleRate"])
                mic_spec = _DeviceSpec(
                    index=mic_idx,
                    name=info["name"],
                    channels=channels,
                    rate=rate,
                )
                names["microphone"] = info["name"]
                log(f"Microfone WASAPI: idx={mic_idx} '{info['name']}' ch={channels} rate={rate}")

            if self._config.capture_system_audio:
                default_out_idx = wasapi_info["defaultOutputDevice"]
                default_out = p.get_device_info_by_index(default_out_idx)
                out_name: str = default_out["name"]
                log(f"Saida padrao WASAPI: idx={default_out_idx} '{out_name}'")

                # Enumera dispositivos de loopback disponíveis
                loopback_info = None
                for lb in p.get_loopback_device_info_generator():
                    log(f"  loopback disponivel: idx={lb['index']} '{lb['name']}'")
                    if loopback_info is None or out_name.lower() in lb["name"].lower():
                        loopback_info = lb

                if loopback_info is None:
                    raise AudioBackendUnavailableError(
                        "Nenhum dispositivo de loopback WASAPI encontrado. "
                        "Verifique se o driver do seu dispositivo de audio suporta loopback."
                    )

                channels = min(self._config.channels, int(loopback_info["maxInputChannels"]))
                rate = int(loopback_info["defaultSampleRate"])
                loopback_spec = _DeviceSpec(
                    index=int(loopback_info["index"]),
                    name=loopback_info["name"],
                    channels=channels,
                    rate=rate,
                )
                names["system"] = out_name
                log(f"Loopback escolhido: idx={loopback_spec.index} '{loopback_spec.name}' ch={channels} rate={rate}")

        finally:
            p.terminate()

        if mic_spec is None and loopback_spec is None:
            raise AudioBackendUnavailableError("Nenhuma fonte de audio habilitada.")

        self._device_names = names
        return mic_spec, loopback_spec

    def _record_loop(
        self,
        output_path: Path,
        lameenc: Any,
        numpy: Any,
        mic_spec: _DeviceSpec | None,
        loopback_spec: _DeviceSpec | None,
    ) -> None:
        import queue as q_module

        try:
            import pyaudiowpatch as pyaudio
        except ImportError as exc:
            self._error = exc
            return

        from gravador_audio.log import log, log_exception

        encoder = self._build_encoder(lameenc)
        log(
            f"Thread iniciada | saida={output_path.name} "
            f"mic={'sim' if mic_spec else 'nao'} "
            f"loopback={'sim' if loopback_spec else 'nao'}"
        )

        import time as _time

        # Output chunk size: 100 ms at target sample rate.
        # Mic callback delivers ~10 ms chunks; loopback blocking-thread delivers
        # exactly this size → accumulators stay balanced.
        _OUT = int(self._config.sample_rate * 0.1)
        _OUT_SECS = _OUT / self._config.sample_rate
        _MAX_LOOP_FRAMES = self._config.sample_rate * 2

        chunk_count = 0
        p = pyaudio.PyAudio()
        mic_stream = None
        loop_stream = None
        loop_reader: threading.Thread | None = None
        mic_q: q_module.Queue = q_module.Queue()
        loop_q: q_module.Queue = q_module.Queue()
        mic_buf = numpy.zeros((0, self._config.channels), dtype=numpy.float32)
        loop_buf = numpy.zeros((0, self._config.channels), dtype=numpy.float32)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Mic: callback mode (driver delivers ~480-frame chunks at native rate)
            if mic_spec is not None:
                def _mic_cb(in_data, frame_count, time_info, status):
                    mic_q.put(bytes(in_data))
                    return (None, pyaudio.paContinue)

                mic_stream = p.open(
                    format=pyaudio.paFloat32,
                    channels=mic_spec.channels,
                    rate=mic_spec.rate,
                    input=True,
                    input_device_index=mic_spec.index,
                    stream_callback=_mic_cb,
                )
                mic_stream.start_stream()

            # Loopback: blocking mode in a dedicated thread.
            # Callback mode for G435 wireless only fires when system audio is non-silent;
            # blocking mode delivers silence frames at device rate, guaranteeing continuity.
            if loopback_spec is not None:
                _ring = int(loopback_spec.rate * 2)  # 2-second ring buffer prevents overflow
                loop_stream = p.open(
                    format=pyaudio.paFloat32,
                    channels=loopback_spec.channels,
                    rate=loopback_spec.rate,
                    input=True,
                    input_device_index=loopback_spec.index,
                    frames_per_buffer=_ring,
                )
                log(f"Loopback blocking | ring={_ring} read_chunk={_OUT}")

                def _loop_reader_fn() -> None:
                    while not self._stop_event.is_set():
                        try:
                            data = loop_stream.read(_OUT, exception_on_overflow=False)
                            loop_q.put(bytes(data))
                        except OSError:
                            break

                loop_reader = threading.Thread(
                    target=_loop_reader_fn, name="loopback-reader", daemon=True
                )
                loop_reader.start()

            log("Streams abertas com sucesso — captura iniciada")
            _start_wall = _time.monotonic()

            def _drain(q: q_module.Queue, spec: _DeviceSpec, buf: Any) -> Any:
                while True:
                    try:
                        raw = q.get_nowait()
                        part = numpy.frombuffer(raw, dtype=numpy.float32).reshape(-1, spec.channels)
                        if spec.rate != self._config.sample_rate:
                            part = self._resample(numpy, part, spec.rate, self._config.sample_rate)
                        part = self._ensure_channels(numpy, part)
                        buf = numpy.concatenate([buf, part], axis=0) if len(buf) else part
                    except q_module.Empty:
                        break
                return buf

            with output_path.open("wb") as file:
                while not self._stop_event.is_set():
                    if mic_spec is not None:
                        mic_buf = _drain(mic_q, mic_spec, mic_buf)
                    if loopback_spec is not None:
                        loop_buf = _drain(loop_q, loopback_spec, loop_buf)
                        if len(loop_buf) > _MAX_LOOP_FRAMES:
                            loop_buf = loop_buf[len(loop_buf) - _MAX_LOOP_FRAMES:]

                    any_encoded = False
                    while True:
                        # G435 loopback entrega ~2x real-time em blocking mode; gate previne encoding acelerado
                        if chunk_count >= int((_time.monotonic() - _start_wall) / _OUT_SECS) + 2:
                            break
                        has_mic = mic_spec is not None
                        has_loop = loopback_spec is not None
                        mic_ready = has_mic and len(mic_buf) >= _OUT
                        loop_ready = has_loop and len(loop_buf) >= _OUT

                        # Advance when at least one active source has a full chunk.
                        # The other source is padded with silence so neither blocks the other.
                        if not (mic_ready or loop_ready):
                            break

                        pieces: list[Any] = []
                        if has_mic:
                            if mic_ready:
                                pieces.append(mic_buf[:_OUT])
                                mic_buf = mic_buf[_OUT:]
                            else:
                                pieces.append(numpy.zeros((_OUT, self._config.channels), dtype=numpy.float32))
                        if has_loop:
                            if loop_ready:
                                pieces.append(loop_buf[:_OUT])
                                loop_buf = loop_buf[_OUT:]
                            else:
                                pieces.append(numpy.zeros((_OUT, self._config.channels), dtype=numpy.float32))

                        mixed = self._mix_chunks(numpy, pieces)
                        try:
                            self._update_eq_levels(numpy, mixed)
                        except Exception:
                            pass
                        pcm = self._float_to_pcm16(numpy, mixed)
                        encoded = encoder.encode(pcm)
                        if encoded:
                            file.write(encoded)
                        chunk_count += 1
                        any_encoded = True
                        if chunk_count == 1:
                            log(f"Primeiro chunk ok | mic_buf_rem={len(mic_buf)} loop_buf_rem={len(loop_buf)} out={_OUT}")

                    if not any_encoded:
                        _time.sleep(0.005)

                if chunk_count > 0:
                    remaining = encoder.flush()
                    if remaining:
                        file.write(remaining)

            log(f"Gravacao encerrada normalmente | chunks={chunk_count}")

        except BaseException as exc:
            log_exception(f"ERRO na thread de gravacao (chunk={chunk_count})", exc)
            self._error = exc
        finally:
            if mic_stream is not None:
                mic_stream.stop_stream()
                mic_stream.close()
            # Close loop_stream first to unblock any pending read() in the reader thread
            if loop_stream is not None:
                loop_stream.close()
            if loop_reader is not None:
                loop_reader.join(timeout=2.0)
            p.terminate()

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _resample(self, numpy: Any, arr: Any, src_rate: int, dst_rate: int) -> Any:
        if src_rate == dst_rate:
            return arr
        ratio = dst_rate / src_rate
        n_out = max(1, int(arr.shape[0] * ratio))
        x_src = numpy.linspace(0, arr.shape[0] - 1, arr.shape[0])
        x_dst = numpy.linspace(0, arr.shape[0] - 1, n_out)
        if arr.ndim == 1:
            return numpy.interp(x_dst, x_src, arr).astype(numpy.float32)
        return numpy.stack(
            [numpy.interp(x_dst, x_src, arr[:, c]).astype(numpy.float32) for c in range(arr.shape[1])],
            axis=1,
        )

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
        current = array.shape[1]
        target = self._config.channels
        if current == target:
            return array
        if current == 1 and target == 2:
            return numpy.repeat(array, 2, axis=1)
        if current > target:
            return array[:, :target]
        padding = numpy.zeros((array.shape[0], target - current), dtype=numpy.float32)
        return numpy.concatenate([array, padding], axis=1)

    def _float_to_pcm16(self, numpy: Any, chunk: Any) -> bytes:
        scaled = numpy.clip(chunk, -1.0, 1.0) * 32767
        return scaled.astype(numpy.int16).tobytes()
