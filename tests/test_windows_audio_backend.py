from __future__ import annotations

import unittest
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy

from record_transcript_resume.windows_audio_backend import (
    WindowsAudioBackend, WindowsAudioBackendConfig, _DeviceSpec,
)


class WindowsAudioBackendTests(unittest.TestCase):
    def test_ensure_channels_duplicates_mono_to_stereo(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        mono = numpy.array([[0.1], [0.2]], dtype=numpy.float32)

        stereo = backend._ensure_channels(numpy, mono)

        self.assertEqual(stereo.shape, (2, 2))
        self.assertAlmostEqual(float(stereo[0][0]), 0.1, places=6)
        self.assertAlmostEqual(float(stereo[0][1]), 0.1, places=6)

    def test_mix_chunks_averages_and_clips(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        first = numpy.array([[1.0, 1.0], [0.5, 0.5]], dtype=numpy.float32)
        second = numpy.array([[1.0, -1.0], [0.5, -0.5]], dtype=numpy.float32)

        mixed = backend._mix_chunks(numpy, [first, second])

        self.assertEqual(mixed.shape, (2, 2))
        self.assertAlmostEqual(float(mixed[0][0]), 1.0, places=6)
        self.assertAlmostEqual(float(mixed[0][1]), 0.0, places=6)

    def test_float_to_pcm16_returns_bytes(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        chunk = numpy.array([[0.0, 1.0], [-1.0, 0.5]], dtype=numpy.float32)

        pcm = backend._float_to_pcm16(numpy, chunk)

        self.assertEqual(len(pcm), 8)

    def test_resample_same_rate_returns_unchanged(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        arr = numpy.array([[0.1, 0.2], [0.3, 0.4]], dtype=numpy.float32)

        result = backend._resample(numpy, arr, src_rate=48000, dst_rate=48000)

        numpy.testing.assert_array_almost_equal(result, arr)

    def test_resample_changes_frame_count(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        arr = numpy.tile(numpy.array([0.1, -0.1], dtype=numpy.float32), (480, 1))

        result = backend._resample(numpy, arr, src_rate=44100, dst_rate=48000)

        expected_frames = max(1, int(480 * 48000 / 44100))
        self.assertEqual(result.shape[0], expected_frames)
        self.assertEqual(result.shape[1], 2)

    def test_update_eq_levels_sets_normalized_values(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        mixed = numpy.zeros((4800, 2), dtype=numpy.float32)
        # Sinal determinístico: seno 440Hz, 4800 frames
        mixed[:, 0] = numpy.sin(numpy.linspace(0, 2 * numpy.pi * 440, 4800))
        mixed[:, 1] = mixed[:, 0]

        backend._update_eq_levels(numpy, mixed)

        levels = backend.eq_levels
        self.assertEqual(len(levels), 16)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in levels), f"Valores fora de [0,1]: {levels}")

    def test_update_eq_levels_silence_returns_zeros(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig(channels=2))
        silence = numpy.zeros((4800, 2), dtype=numpy.float32)

        backend._update_eq_levels(numpy, silence)

        self.assertEqual(backend.eq_levels, [0.0] * 16)

    def test_is_thread_alive_false_before_start(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig())

        self.assertFalse(backend.is_thread_alive)

    def test_thread_error_none_before_start(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig())

        self.assertIsNone(backend.thread_error)

    def test_device_names_empty_before_start(self) -> None:
        backend = WindowsAudioBackend(WindowsAudioBackendConfig())

        self.assertEqual(backend.device_names, {})


def test_silent_loopback_stops_before_native_stream_is_closed(monkeypatch, tmp_path: Path) -> None:
    class SilentStream:
        def __init__(self) -> None:
            self.read_count = 0
            self.closed = False

        def get_read_available(self) -> int:
            return 0

        def read(self, *_args: object, **_kwargs: object) -> bytes:
            self.read_count += 1
            raise AssertionError("A silent loopback must never enter blocking read")

        def close(self) -> None:
            self.closed = True

    stream = SilentStream()
    terminated = []

    class FakePyAudio:
        def open(self, **_kwargs: object) -> SilentStream:
            return stream

        def terminate(self) -> None:
            terminated.append(True)

    monkeypatch.setitem(sys.modules, "pyaudiowpatch", SimpleNamespace(
        PyAudio=FakePyAudio, paFloat32=1,
    ))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    backend = WindowsAudioBackend(WindowsAudioBackendConfig(capture_microphone=False))
    monkeypatch.setattr(backend, "_build_encoder", lambda _module: object())
    output = tmp_path / "silence.mp3"
    worker = threading.Thread(target=backend._record_loop, args=(
        output, object(), numpy, None, _DeviceSpec(1, "Silent loopback", 2, 48_000),
    ))

    worker.start()
    time.sleep(0.06)
    backend._stop_event.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert stream.read_count == 0
    assert stream.closed is True
    assert terminated == [True]
    assert backend.thread_error is None


if __name__ == "__main__":
    unittest.main()
