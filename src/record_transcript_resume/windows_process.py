"""Small, explicit helpers for child processes started by the desktop app."""
from __future__ import annotations

import os
import subprocess


def hidden_process_kwargs() -> dict[str, int]:
    """Prevent console windows from flashing when the GUI starts a CLI on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def terminate_process_tree(process: subprocess.Popen[object]) -> None:
    """Stop an owned worker and any provider process it may have started.

    The transcription worker is isolated from the GUI precisely so that it can
    be stopped without destabilizing the desktop application. On Windows,
    ``/T`` also closes a CLI child created by the worker while generating a
    summary.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_process_kwargs(),
        )
        return
    process.terminate()
