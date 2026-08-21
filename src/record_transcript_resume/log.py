from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

from record_transcript_resume.paths import app_data_dir


def _log_path() -> Path:
    return app_data_dir() / "recorder.log"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


def log_exception(context: str, exc: BaseException) -> None:
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    log(f"{context}\n{''.join(tb_lines).rstrip()}")
