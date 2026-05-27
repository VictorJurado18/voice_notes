from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from gravador_audio.audio_backend import AudioBackend
from gravador_audio.errors import DiskSpaceError, InvalidRecordingStateError, OutputPathError, RecordingError

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
    filename_prefix: str = "gravacao"
    extension: str = ".mp3"

    def build_output_path(self, now: datetime | None = None) -> Path:
        timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        safe_prefix = self.filename_prefix.strip() or "gravacao"
        return self.output_dir / f"{safe_prefix}-{timestamp}{self.extension}"


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
        from gravador_audio.windows_audio_backend import WindowsAudioBackend
        if isinstance(self._backend, WindowsAudioBackend):
            return self._backend.eq_levels
        return [0.0] * 16

    def start(self) -> Path:
        if self._state == RecordingState.RECORDING:
            raise InvalidRecordingStateError("Ja existe uma gravacao em andamento.")

        output_path = self._prepare_output_path()

        try:
            self._backend.start(output_path)
        except RecordingError as exc:
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
            raise InvalidRecordingStateError("Nao ha gravacao em andamento para finalizar.")

        if self._current_output_path is None:
            self._state = RecordingState.ERROR
            self._last_error = "Caminho de saida ausente durante finalizacao."
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
            raise OutputPathError(f"Destino de gravacao nao e uma pasta: {output_dir}")

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputPathError(f"Nao foi possivel criar a pasta de saida: {output_dir}") from exc

        try:
            free = shutil.disk_usage(output_dir).free
        except OSError:
            free = None

        if free is not None and free < MIN_FREE_BYTES:
            free_mb = free // (1024 * 1024)
            raise DiskSpaceError(
                f"Espaco insuficiente em disco: {free_mb} MB disponiveis (minimo 100 MB)."
            )

        output_path = self._config.build_output_path()
        if output_path.exists():
            raise OutputPathError(f"Arquivo de saida ja existe: {output_path}")

        return output_path
