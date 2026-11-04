"""Track meaningful captured sound independently of the display equalizer."""

from __future__ import annotations

import time


# Roughly -46 dBFS. Quiet speech clears this gate; ordinary capture noise does not.
MIN_MEANINGFUL_RMS = 0.005


class SilenceTracker:
    def __init__(self, threshold: float = MIN_MEANINGFUL_RMS) -> None:
        self.threshold = threshold
        self.reset()

    def reset(self, now: float | None = None) -> None:
        self.last_sound_at = time.monotonic() if now is None else now

    def observe(self, rms: float, now: float | None = None) -> None:
        if rms >= self.threshold:
            self.last_sound_at = time.monotonic() if now is None else now

    def silent_for(self, now: float | None = None) -> float | None:
        return max(0.0, (time.monotonic() if now is None else now) - self.last_sound_at)
