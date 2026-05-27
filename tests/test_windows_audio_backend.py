from __future__ import annotations

import unittest

import numpy

from gravador_audio.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig


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


if __name__ == "__main__":
    unittest.main()
