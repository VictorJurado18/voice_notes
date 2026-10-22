"""Local timing samples and deliberately approximate processing forecasts."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
from threading import RLock
from record_transcript_resume.paths import app_data_dir

_LOCK = RLock()


def media_duration(path: Path) -> float:
    """Read container metadata only. Call from a worker, never a Tk callback."""
    try:
        import av
        with av.open(str(path)) as container:
            if container.duration:
                return max(0.0, float(container.duration) / av.time_base)
            stream = next(iter(container.streams.audio), None)
            if stream is not None and stream.duration and stream.time_base:
                return max(0.0, float(stream.duration * stream.time_base))
    except Exception:
        pass
    return 0.0


def profile_key(model: str, transcription_provider: str, provider: str,
                output_mode: str, speakers: bool, cpu_threads: int = 0) -> str:
    return json.dumps([model, transcription_provider, provider if output_mode != "transcription" else "",
                       output_mode, speakers, cpu_threads], ensure_ascii=False)


@dataclass(frozen=True)
class Estimate:
    low: float
    high: float
    samples: int

    def label(self) -> str:
        def minutes(seconds):
            return max(1, math.ceil(seconds / 60))
        low, high = minutes(self.low), minutes(self.high)
        interval = f"cerca de {low} min" if low == high else f"{low}–{high} min"
        origin = f"{self.samples} processamento(s) neste computador" if self.samples else "estimativa inicial, ainda sem histórico"
        return f"{interval} · {origin}"


class ProcessingMetricsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "processing-times.json"

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, UnicodeError):
            return {}

    def record(self, key: str, audio_seconds: float, processing_seconds: float) -> None:
        if (not all(math.isfinite(x) for x in (audio_seconds, processing_seconds))
                or audio_seconds < 15 or processing_seconds <= 0):
            return
        with _LOCK:
            data = self._load()
            previous = data.get(key, [])
            rows = previous if isinstance(previous, list) else []
            data[key] = [*rows[-19:], [round(audio_seconds, 3), round(processing_seconds, 3)]]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)

    def estimate(self, key: str, audio_seconds: float, *, model: str = "small",
                 local: bool = True, speakers: bool = False, summary: bool = True) -> Estimate | None:
        if not math.isfinite(audio_seconds) or audio_seconds <= 0:
            return None
        ratios = []
        rows = self._load().get(key, [])
        for row in rows if isinstance(rows, list) else []:
            try:
                duration, elapsed = map(float, row)
                if duration >= 15 and elapsed > 0 and math.isfinite(duration + elapsed):
                    ratios.append(elapsed / duration)
            except (ValueError, TypeError):
                continue
        if ratios:
            median = statistics.median(ratios)
            uncertainty = .65 if len(ratios) < 3 else .35
            spread = max(uncertainty * median, statistics.median(abs(x-median) for x in ratios) * 2)
            return Estimate(max(10, audio_seconds * max(.01, median-spread)),
                            max(20, audio_seconds * (median+spread)), len(ratios))
        # Wide, explicitly labelled prior; downloads and system load can exceed it.
        ratio = {"tiny": .12, "base": .22, "small": .5, "medium": 1.3, "large-v3": 2.5}.get(model, .5) if local else .15
        if speakers:
            ratio += .6
        extra = 60 if summary else 15
        return Estimate(max(15, audio_seconds * ratio * .5 + extra * .3),
                        audio_seconds * ratio * 2 + extra * 2, 0)
