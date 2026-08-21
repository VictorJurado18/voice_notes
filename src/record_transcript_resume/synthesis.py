from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.paths import app_data_dir

_TIMEOUT = 120
SummaryProvider = Literal["codex", "claude", "api"]
SummaryTemplate = Literal["meeting", "class", "interview", "sales", "brainstorm", "executive", "study", "action_plan"]
SUPPORTED_PROVIDERS: tuple[SummaryProvider, ...] = ("codex", "claude", "api")
DEFAULT_PROVIDER: SummaryProvider = "codex"
DEFAULT_TEMPLATE: SummaryTemplate = "meeting"

SUMMARY_TEMPLATE_LABELS: dict[SummaryTemplate, str] = {
    "meeting": "Reunião",
    "class": "Aula",
    "interview": "Entrevista",
    "sales": "Call comercial",
    "brainstorm": "Brainstorm",
    "executive": "Resumo executivo",
    "study": "Estudo",
    "action_plan": "Plano de ação",
}

_TEMPLATE_SECTIONS: dict[SummaryTemplate, tuple[str, ...]] = {
    "meeting": ("Contexto", "Pontos principais", "Decisões", "Responsáveis e ações", "Próximos passos"),
    "class": ("Tema da aula", "Conceitos explicados", "Exemplos importantes", "Dúvidas e respostas", "Próximos estudos"),
    "interview": ("Perfil", "Experiência e respostas", "Pontos fortes", "Pontos de atenção", "Próximos passos"),
    "sales": ("Cliente e contexto", "Necessidades", "Proposta e objeções", "Ações e responsáveis", "Próximo contato"),
    "brainstorm": ("Objetivo", "Ideias levantadas", "Opções priorizadas", "Experimentos", "Próximos passos"),
    "executive": ("Contexto", "Síntese executiva", "Decisões", "Riscos e pontos de atenção", "Próximas ações"),
    "study": ("Visão geral", "Conceitos-chave", "Explicações e exemplos", "Perguntas para revisar", "Próximos estudos"),
    "action_plan": ("Objetivo", "Decisões", "Ações", "Responsáveis", "Prazos e próximos passos"),
}

_PROMPT_TEMPLATE = """\
Você recebeu a transcrição de uma conversa gravada.

Data da gravação: {date}
Formato do resumo: {template_label}

Transcrição:
{transcription}

Idioma obrigatório da resposta: português do Brasil. Escreva todo o título, todas as seções e todo o conteúdo do resumo em português do Brasil, mesmo que a transcrição contenha outro idioma.

Responda SOMENTE com um objeto JSON válido, sem bloco de markdown e sem explicação:
{{"folder_name": "<nome-curto-em-kebab-case-sem-data>", "summary_md": "<conteúdo-completo-do-resumo-em-markdown-em-português>"}}

O campo summary_md deve ter um título conciso e exatamente estas seções em markdown:
{sections}\
"""

_CODEX_INSTRUCTION = """\
Crie o resumo solicitado a partir da transcrição recebida pela entrada padrão.
Respeite o idioma obrigatório definido no prompt e retorne apenas o objeto JSON válido solicitado, sem explicações nem bloco de markdown.
"""


@dataclass(frozen=True)
class SynthesisResult:
    folder_name: str
    summary_md: str


@dataclass(frozen=True)
class ProviderLoginStatus:
    """Availability/authentication state used by the widget on first launch."""

    installed: bool
    authenticated: bool | None


def generate(
    transcription_text: str,
    date_str: str,
    provider: SummaryProvider = DEFAULT_PROVIDER,
    summary_template: SummaryTemplate = DEFAULT_TEMPLATE,
) -> SynthesisResult:
    if provider not in SUPPORTED_PROVIDERS:
        raise SynthesisError(f"Unsupported summary provider: {provider}")
    if summary_template not in SUMMARY_TEMPLATE_LABELS:
        raise SynthesisError(f"Unsupported summary template: {summary_template}")

    sections = "\n".join(f"## {section}" for section in _TEMPLATE_SECTIONS[summary_template])
    prompt = _PROMPT_TEMPLATE.format(
        date=date_str,
        template_label=SUMMARY_TEMPLATE_LABELS[summary_template],
        transcription=transcription_text,
        sections=sections,
    )
    if provider == "api":
        from record_transcript_resume.api_provider import generate as generate_api
        stdout = generate_api(prompt)
        return _result_from_stdout(stdout)
    command = _command_for(provider)

    try:
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            encoding="utf-8",
            env=_provider_environment(),
        )
    except FileNotFoundError as exc:
        raise SynthesisError(
            f"{provider} CLI not found in PATH. Install it and authenticate before processing."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SynthesisError(
            f"Timeout: {provider} did not respond within {_TIMEOUT}s."
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SynthesisError(
            f"{provider} CLI failed with exit code {result.returncode}: {detail[:500]}"
        )

    return _result_from_stdout(result.stdout.strip())


def _result_from_stdout(stdout: str) -> SynthesisResult:

    # Strip ```json ... ``` wrapper if Claude returns markdown
    if stdout.startswith("```"):
        lines = stdout.splitlines()
        stdout = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(stdout)
        folder_name = str(data["folder_name"]).strip()
        summary_md = str(data["summary_md"]).strip()
        return SynthesisResult(folder_name=folder_name, summary_md=summary_md)
    except (json.JSONDecodeError, KeyError, TypeError):
        fallback = (
            "# Summary unavailable\n\n"
            "Automatic synthesis failed. Transcription saved in `transcription.md`.\n\n"
            f"Raw provider output:\n\n```\n{stdout[:2000]}\n```"
        )
        return SynthesisResult(folder_name="", summary_md=fallback)


def _command_for(provider: SummaryProvider) -> list[str]:
    if provider == "claude":
        return [_cli_executable("claude"), "-p"]

    # The prompt is intentionally short; the transcription is sent through stdin.
    # This avoids Windows command-line length limits for long meetings.
    return [
        _cli_executable("codex"),
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        _CODEX_INSTRUCTION,
    ]


def _cli_executable(name: str) -> str:
    """Return a directly executable CLI path on every supported platform."""
    bundled = _bundled_cli_path(name)
    if bundled is not None:
        return str(bundled)
    if os.name == "nt":
        return shutil.which(f"{name}.cmd") or f"{name}.cmd"
    return name


def provider_login_status(provider: SummaryProvider) -> ProviderLoginStatus:
    """Check the provider without sending transcript content or consuming credits.

    Both supported CLIs expose a non-interactive status command, so opening the
    widget never sends transcription content or consumes summary credits.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported summary provider: {provider}")

    if provider == "api":
        from record_transcript_resume.api_provider import has_token
        return ProviderLoginStatus(installed=True, authenticated=has_token())
    executable = _cli_executable(provider)
    if not _command_exists(executable):
        return ProviderLoginStatus(installed=False, authenticated=False)
    status_args = ["login", "status"] if provider == "codex" else ["auth", "status"]
    try:
        result = subprocess.run(
            [executable, *status_args],
            capture_output=True,
            text=True,
            timeout=12,
            encoding="utf-8",
            env=_provider_environment(),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ProviderLoginStatus(installed=False, authenticated=False)
    if provider == "claude":
        try:
            payload = json.loads(result.stdout or "{}")
            authenticated = bool(payload.get("loggedIn"))
        except json.JSONDecodeError:
            authenticated = result.returncode == 0
        return ProviderLoginStatus(installed=True, authenticated=authenticated)
    return ProviderLoginStatus(installed=True, authenticated=result.returncode == 0)


def login_terminal_command(provider: SummaryProvider) -> str:
    """Return a ``cmd.exe`` command that opens the provider's normal login flow."""
    executable = _cli_executable(provider)
    node_dir = _bundled_node_dir()
    prefix = f'set "PATH={node_dir};%PATH%" && ' if node_dir is not None else ""
    # ``call`` is required when invoking a .cmd shim from another cmd instance.
    action = "login" if provider == "codex" else "auth login"
    return f'{prefix}call "{executable}" {action}'.rstrip()


def _bundled_cli_path(name: str) -> Path | None:
    extension = ".cmd" if os.name == "nt" else ""
    # npm places global command shims at the prefix root on Windows (rather
    # than in ``bin`` as it does on Unix-like platforms).
    candidate = app_data_dir() / "tools" / "cli" / f"{name}{extension}"
    return candidate if candidate.is_file() else None


def _bundled_node_dir() -> Path | None:
    candidate = app_data_dir() / "tools" / "node"
    return candidate if (candidate / ("node.exe" if os.name == "nt" else "node")).is_file() else None


def _provider_environment() -> dict[str, str]:
    env = os.environ.copy()
    node_dir = _bundled_node_dir()
    if node_dir is not None:
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    return env


def _command_exists(executable: str) -> bool:
    path = Path(executable)
    if path.is_file():
        return True
    return shutil.which(executable) is not None
