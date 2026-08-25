"""Small, explicit helpers for child processes started by the desktop app."""
from __future__ import annotations

import os
import subprocess


def hidden_process_kwargs() -> dict[str, int]:
    """Prevent console windows from flashing when the GUI starts a CLI on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
