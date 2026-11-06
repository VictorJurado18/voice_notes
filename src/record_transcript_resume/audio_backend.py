from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from record_transcript_resume.errors import AudioBackendUnavailableError, RecordingError


class AudioBackend(ABC):
    """Interface for a platform-specific audio recording backend."""

    @abstractmethod
    def start(self, output_path: Path) -> None:
        """Start recording to the given output path."""

    @abstractmethod
    def stop(self) -> None:
        """Stop recording and finalize the output file."""

    def pause(self) -> None:
        """Suspend writing captured audio without finalizing the output file."""
        raise RecordingError("This audio backend does not support pausing.")

    def resume(self) -> None:
        """Continue writing to the current output file."""
        raise RecordingError("This audio backend does not support resuming.")


class UnavailableAudioBackend(AudioBackend):
    """Backend used until Windows audio capture is implemented."""

    def start(self, output_path: Path) -> None:
        raise AudioBackendUnavailableError(
            "Audio capture not yet implemented. "
            "Define and approve an audio library/API for Windows before recording."
        )

    def stop(self) -> None:
        return None
