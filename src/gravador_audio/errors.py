class RecordingError(Exception):
    """Base error for recording failures."""


class InvalidRecordingStateError(RecordingError):
    """Raised when an operation is not valid for the current state."""


class AudioBackendUnavailableError(RecordingError):
    """Raised when no real audio backend is available."""


class OutputPathError(RecordingError):
    """Raised when the output path cannot be prepared safely."""
