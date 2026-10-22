"""Reserve CPU for live recording and check Windows commit headroom."""
from __future__ import annotations
import os


def transcription_threads() -> int:
    cores = os.cpu_count() or 2
    return max(1, min(4, cores // 2))


def memory_headroom() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
                        *[(key, ctypes.c_uint64) for key in ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return min(status.avail_phys, status.avail_page)
    except (AttributeError, OSError):
        pass
    return None


def required_headroom(model: str, *, speakers: bool = False, local: bool = True) -> int:
    megabytes = {"tiny": 600, "base": 750, "small": 1300, "medium": 2700, "large-v3": 4200}.get(model, 1300) if local else 300
    return (megabytes + (1800 if speakers else 0) + 400) * 1024 * 1024


def worker_environment(env: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    threads = str(transcription_threads())
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        result[name] = threads
    result["VOICE_NOTES_CPU_THREADS"] = threads
    return result
