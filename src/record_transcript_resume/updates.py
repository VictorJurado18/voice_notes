"""Versioned installer updates published through the project's GitHub Releases."""
from __future__ import annotations

import json
import re
import subprocess
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from record_transcript_resume.paths import app_data_dir
from record_transcript_resume.windows_process import hidden_process_kwargs

RELEASES_API_URL = "https://api.github.com/repos/VictorJurado18/voice-notes-releases/releases/latest"
_SETUP_NAME = re.compile(r"^VoiceNotes-Setup-(?P<version>.+)\.exe$", re.IGNORECASE)


def _installed_version() -> str:
    """Read the build version from the project metadata bundled with the app."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        root = Path(__file__).resolve().parents[2]
    try:
        contents = (root / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', contents, re.MULTILINE)
        if match is not None:
            return match.group(1)
    except OSError:
        pass
    return "0.0.0"


APP_VERSION = _installed_version()


@dataclass(frozen=True)
class ApplicationUpdate:
    available: bool
    message: str
    version: str = ""
    download_url: str = ""
    sha256: str = ""


def _version_key(value: str) -> tuple[int, ...]:
    """Compare the numeric application versions used by the Windows installer."""
    cleaned = value.strip().lstrip("vV")
    match = re.fullmatch(r"(\d+(?:\.\d+)*)", cleaned)
    if match is None:
        raise ValueError(f"Invalid application version: {value}")
    return tuple(int(part) for part in match.group(1).split("."))


def _latest_release_payload() -> dict[str, object]:
    call = request.Request(
        RELEASES_API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "VoiceNotesUpdater/1.0"},
    )
    with request.urlopen(call, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid release response")
    return payload


def check_for_updates() -> ApplicationUpdate:
    """Compare this executable's version to the latest published installer."""
    try:
        release = _latest_release_payload()
        tag = str(release.get("tag_name", "")).strip()
        version = tag.lstrip("vV")
        assets = release.get("assets", [])
        if not isinstance(assets, list):
            raise ValueError("Release has invalid assets")
        asset_url = ""
        sha256 = ""
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            match = _SETUP_NAME.match(str(asset.get("name", "")))
            if match is not None:
                version = match.group("version")
                asset_url = str(asset.get("browser_download_url", ""))
                digest = str(asset.get("digest", ""))
                if digest.startswith("sha256:"):
                    sha256 = digest.removeprefix("sha256:").lower()
                break
        if not asset_url:
            return ApplicationUpdate(False, "A versão publicada não possui o instalador VoiceNotes-Setup.")
        if _version_key(version) <= _version_key(APP_VERSION):
            return ApplicationUpdate(False, f"Voice Notes {APP_VERSION} já está atualizado.")
        return ApplicationUpdate(True, f"Nova versão disponível: {version}.", version, asset_url, sha256)
    except error.HTTPError as exc:
        if exc.code == 404:
            return ApplicationUpdate(False, "Ainda não há uma Release publicada para verificar atualizações.")
        return ApplicationUpdate(False, f"Não foi possível consultar atualizações (HTTP {exc.code}).")
    except (error.URLError, OSError, ValueError, json.JSONDecodeError):
        return ApplicationUpdate(False, "Não foi possível consultar atualizações agora. Verifique sua conexão.")


def download_and_start_update(update: ApplicationUpdate) -> ApplicationUpdate:
    """Download the published setup and start it hidden after user confirmation."""
    if not update.available or not update.download_url or not update.version:
        return ApplicationUpdate(False, "Nenhuma atualização válida foi selecionada.")
    try:
        updates_dir = app_data_dir() / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        installer = updates_dir / f"VoiceNotes-Setup-{update.version}.exe"
        download = request.Request(update.download_url, headers={"User-Agent": "VoiceNotesUpdater/1.0"})
        with request.urlopen(download, timeout=120) as response, installer.open("wb") as destination:
            while chunk := response.read(1024 * 1024):
                destination.write(chunk)
        if update.sha256:
            actual_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
            if actual_hash.lower() != update.sha256.lower():
                installer.unlink(missing_ok=True)
                return ApplicationUpdate(False, "O arquivo baixado não passou na verificação de segurança.")
        subprocess.Popen(
            [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            cwd=str(installer.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_process_kwargs(),
        )
        return ApplicationUpdate(True, f"Atualizando para a versão {update.version}…", update.version, update.download_url, update.sha256)
    except (error.URLError, OSError):
        return ApplicationUpdate(False, "Não foi possível baixar ou iniciar a atualização.")
