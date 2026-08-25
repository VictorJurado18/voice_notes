"""Recovery installation for the bundled summary CLIs.

The Windows installer performs this work too.  Keeping the same operation
available from the application makes a transient download failure recoverable
without asking a person to install Node.js, npm, or edit PATH.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from record_transcript_resume.paths import app_data_dir
from record_transcript_resume.windows_process import hidden_process_kwargs


def provider_setup_script() -> Path:
    """Locate the script both in a source checkout and in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "record_transcript_resume" / "resources" / "install_providers.ps1"
    return Path(__file__).resolve().parent / "resources" / "install_providers.ps1"


def provider_setup_log_path() -> Path:
    return app_data_dir() / "tools" / "provider-setup.log"


def start_provider_setup() -> subprocess.Popen[str]:
    """Start provider provisioning invisibly and return immediately."""
    script = provider_setup_script()
    if not script.is_file():
        raise FileNotFoundError(f"Provider setup script was not bundled: {script}")
    powershell = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = [
        str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-ToolsRoot", str(app_data_dir() / "tools"),
    ]
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        **hidden_process_kwargs(),
    )
