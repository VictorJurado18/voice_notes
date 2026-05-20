from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gravador_audio.audio_backend import AudioBackend, UnavailableAudioBackend
from gravador_audio.errors import AudioBackendUnavailableError, InvalidRecordingStateError
from gravador_audio.recording import RecordingConfig, RecordingService, RecordingState


class FakeAudioBackend(AudioBackend):
    def __init__(self) -> None:
        self.started_path: Path | None = None
        self.stopped = False

    def start(self, output_path: Path) -> None:
        self.started_path = output_path

    def stop(self) -> None:
        self.stopped = True


class RecordingServiceTests(unittest.TestCase):
    def test_start_sets_recording_state_and_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeAudioBackend()
            service = RecordingService(
                RecordingConfig(output_dir=Path(tmp)),
                backend=backend,
            )

            output_path = service.start()

            self.assertEqual(service.state, RecordingState.RECORDING)
            self.assertEqual(service.current_output_path, output_path)
            self.assertEqual(backend.started_path, output_path)
            self.assertEqual(output_path.suffix, ".mp3")

    def test_start_fails_when_backend_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = RecordingService(
                RecordingConfig(output_dir=Path(tmp)),
                backend=UnavailableAudioBackend(),
            )

            with self.assertRaises(AudioBackendUnavailableError):
                service.start()

            self.assertEqual(service.state, RecordingState.ERROR)
            self.assertIsNone(service.current_output_path)
            self.assertIsNotNone(service.last_error)

    def test_stop_finalizes_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeAudioBackend()
            service = RecordingService(
                RecordingConfig(output_dir=Path(tmp)),
                backend=backend,
            )
            service.start()

            output_path = service.stop()

            self.assertEqual(service.state, RecordingState.COMPLETED)
            self.assertTrue(backend.stopped)
            self.assertEqual(output_path.suffix, ".mp3")

    def test_stop_without_recording_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = RecordingService(
                RecordingConfig(output_dir=Path(tmp)),
                backend=FakeAudioBackend(),
            )

            with self.assertRaises(InvalidRecordingStateError):
                service.stop()


if __name__ == "__main__":
    unittest.main()
