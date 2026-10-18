from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from record_transcript_resume.audio_backend import AudioBackend
from record_transcript_resume.errors import DiskSpaceError, InvalidRecordingStateError, OutputPathError, RecordingError

MIN_FREE_BYTES = 100 * 1024 * 1024  # 100 MB


class RecordingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True)
class RecordingConfig:
    output_dir: Path
    filename_prefix: str = "recording"
    extension: str = ".mp3"

    def build_output_path(self, now: datetime | None = None) -> Path:
        timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        safe_prefix = self.filename_prefix.strip() or "recording"
        name = f"{safe_prefix}-{timestamp}"
        return self.output_dir / name / f"{name}{self.extension}"


class RecordingService:
    def __init__(self, config: RecordingConfig, backend: AudioBackend) -> None:
        self._config = config
        self._backend = backend
        self._state = RecordingState.IDLE
        self._current_output_path: Path | None = None
        self._last_error: str | None = None

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def current_output_path(self) -> Path | None:
        return self._current_output_path

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def eq_levels(self) -> list[float]:
        from record_transcript_resume.windows_audio_backend import WindowsAudioBackend
        if isinstance(self._backend, WindowsAudioBackend):
            return self._backend.eq_levels
        return [0.0] * 16

    @property
    def device_info(self) -> dict[str, str]:
        from record_transcript_resume.windows_audio_backend import WindowsAudioBackend
        if isinstance(self._backend, WindowsAudioBackend):
            return self._backend.device_names
        return {}

    @property
    def thread_error(self) -> str | None:
        from record_transcript_resume.windows_audio_backend import WindowsAudioBackend
        if isinstance(self._backend, WindowsAudioBackend):
            return self._backend.thread_error
        return None

    @property
    def is_backend_alive(self) -> bool:
        from record_transcript_resume.windows_audio_backend import WindowsAudioBackend
        if isinstance(self._backend, WindowsAudioBackend):
            return self._backend.is_thread_alive
        return True

    def start(self) -> Path:
        if self._state == RecordingState.RECORDING:
            raise InvalidRecordingStateError("A recording is already in progress.")

        output_path = self._prepare_output_path()

        try:
            self._backend.start(output_path)
        except RecordingError as exc:
            try:
                output_path.parent.rmdir()
            except OSError:
                pass
            self._state = RecordingState.ERROR
            self._last_error = str(exc)
            self._current_output_path = None
            raise

        self._state = RecordingState.RECORDING
        self._last_error = None
        self._current_output_path = output_path
        return output_path

    def stop(self) -> Path:
        if self._state != RecordingState.RECORDING:
            raise InvalidRecordingStateError("No recording in progress to stop.")

        if self._current_output_path is None:
            self._state = RecordingState.ERROR
            self._last_error = "Output path missing during finalization."
            raise OutputPathError(self._last_error)

        self._state = RecordingState.FINALIZING

        try:
            self._backend.stop()
        except RecordingError as exc:
            self._state = RecordingState.ERROR
            self._last_error = str(exc)
            raise

        self._state = RecordingState.COMPLETED
        self._last_error = None
        return self._current_output_path

    def _prepare_output_path(self) -> Path:
        output_dir = self._config.output_dir
        if output_dir.exists() and not output_dir.is_dir():
            raise OutputPathError(f"Recording destination is not a folder: {output_dir}")

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputPathError(f"Could not create output folder: {output_dir}") from exc

        try:
            free = shutil.disk_usage(output_dir).free
        except OSError:
            free = None

        if free is not None and free < MIN_FREE_BYTES:
            free_mb = free // (1024 * 1024)
            raise DiskSpaceError(
                f"Insufficient disk space: {free_mb} MB available (minimum 100 MB)."
            )

        output_path = self._config.build_output_path()
        if output_path.exists():
            raise OutputPathError(f"Output file already exists: {output_path}")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise OutputPathError(f"Could not create recording folder: {output_path.parent}") from exc

        return output_path
