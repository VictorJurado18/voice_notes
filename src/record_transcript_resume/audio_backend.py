from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from record_transcript_resume.errors import AudioBackendUnavailableError


class AudioBackend(ABC):
    """Interface for a platform-specific audio recording backend."""

    @abstractmethod
    def start(self, output_path: Path) -> None:
        """Start recording to the given output path."""

    @abstractmethod
    def stop(self) -> None:
        """Stop recording and finalize the output file."""


class UnavailableAudioBackend(AudioBackend):
    """Backend used until Windows audio capture is implemented."""

    def start(self, output_path: Path) -> None:
        raise AudioBackendUnavailableError(
            "Audio capture not yet implemented. "
            "Define and approve an audio library/API for Windows before recording."
        )

    def stop(self) -> None:
        return None
