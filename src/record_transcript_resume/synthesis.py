from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.paths import app_data_dir
from record_transcript_resume.windows_process import hidden_process_kwargs

_TIMEOUT = 120
SummaryProvider = str
SummaryTemplate = str
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
{profile_instructions}

Transcrição:
{transcription}

Idioma obrigatório da resposta: português do Brasil. Escreva todo o título, todas as seções e todo o conteúdo do resumo em português do Brasil, mesmo que a transcrição contenha outro idioma.

Responda SOMENTE com um objeto JSON válido, sem bloco de markdown e sem explicação:
{{"folder_name": "<nome-curto-em-kebab-case-sem-data>", "summary_md": "<conteúdo-completo-do-resumo-em-markdown-em-português>"}}

O campo summary_md deve ter um título conciso e obedecer à estrutura em markdown abaixo:
{sections}\
"""

_CODEX_INSTRUCTION = """\
Crie o resumo solicitado a partir da transcrição recebida pela entrada padrão.
Respeite o idioma obrigatório definido no prompt e retorne apenas o objeto JSON válido solicitado, sem explicações nem bloco de markdown.
"""

_CUSTOM_PROFILE_SAFETY = """\

Mantenha todo o resumo em português do Brasil, use somente informações sustentadas pela transcrição e retorne SOMENTE um objeto JSON válido, sem explicação nem bloco de markdown:
{"folder_name": "<nome-curto-em-kebab-case-sem-data>", "summary_md": "<conteúdo-completo-do-resumo-em-markdown-em-português>"}
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
    source: Literal["voice_notes", "system", "api", "missing"] = "missing"
    executable: str = ""


@dataclass(frozen=True)
class CliResolution:
    """A CLI executable and the installation that supplied it."""

    executable: str
    source: Literal["voice_notes", "system"]


def generate(
    transcription_text: str,
    date_str: str,
    provider: SummaryProvider = DEFAULT_PROVIDER,
    summary_template: SummaryTemplate = DEFAULT_TEMPLATE,
    additional_instructions: str = "",
) -> SynthesisResult:
    is_api_provider = provider == "api" or provider.startswith("api:")
    if provider not in SUPPORTED_PROVIDERS and not is_api_provider:
        raise SynthesisError(f"Unsupported summary provider: {provider}")
    prompt = _saved_custom_profile_prompt(summary_template, date_str, transcription_text)
    if prompt is None:
        template_label, sections, profile_instructions = _summary_structure(summary_template)
        additional = additional_instructions.strip()
        if additional:
            profile_instructions += (
                "\nInstruções específicas desta gravação:\n"
                f"{additional}\n"
                "Priorize essas instruções sem inventar informações ausentes na transcrição.\n"
            )
        prompt = _PROMPT_TEMPLATE.format(
            date=date_str,
            template_label=template_label,
            transcription=transcription_text,
            profile_instructions=profile_instructions,
            sections=sections,
        )
    elif additional_instructions.strip():
        prompt += (
            "\nInstruções específicas desta gravação:\n"
            f"{additional_instructions.strip()}\n"
            "Priorize essas instruções sem inventar informações ausentes na transcrição.\n"
        )
    if is_api_provider:
        from record_transcript_resume.api_provider import generate as generate_api
        provider_id = provider.partition(":")[2] or None
        stdout = generate_api(prompt, provider_id=provider_id)
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
            **hidden_process_kwargs(),
        )
    except FileNotFoundError as exc:
        raise SynthesisError(
            f"{provider} CLI not found in Voice Notes or the system PATH. Install it and authenticate before processing."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SynthesisError(
            f"Timeout: {provider} did not respond within {_TIMEOUT}s."
        ) from exc

    if (
        provider == "codex"
        and result.returncode != 0
        and "model is not supported when using Codex with a ChatGPT account"
        in (result.stderr or "")
    ):
        # A stale model in the user's Codex configuration must not prevent
        # Voice Notes from using the CLI's supported default model.
        command.insert(2, "--ignore-user-config")
        try:
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                encoding="utf-8",
                env=_provider_environment(),
                **hidden_process_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise SynthesisError(
                f"Timeout: {provider} did not respond within {_TIMEOUT}s."
            ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        errors = [line.strip() for line in detail.splitlines() if line.strip().startswith("ERROR:")]
        detail = errors[-1] if errors else detail[-500:]
        raise SynthesisError(
            f"{provider} CLI failed with exit code {result.returncode}: {detail}"
        )

    return _result_from_stdout(result.stdout.strip())


def test_summary_provider(provider: SummaryProvider) -> None:
    """Send a tiny synthetic prompt through a CLI provider and validate output.

    This is an explicit user action because the provider may consume account
    usage. No recording, transcript, or summary file is read or written.
    """
    if provider not in {"codex", "claude"}:
        raise SynthesisError(f"Teste de conexão não disponível para o provider: {provider}")
    result = generate(
        "Esta é uma transcrição sintética para testar a conexão do Voice Notes. "
        "Não há reunião nem fatos reais a resumir.",
        datetime.now().strftime("%Y-%m-%d"),
        provider=provider,
        summary_template="meeting",
        additional_instructions="Este é um teste técnico. Mantenha todas as seções muito curtas.",
    )
    if not result.folder_name or result.summary_md.lstrip().startswith("# Summary unavailable"):
        raise SynthesisError(
            f"{provider} respondeu, mas não retornou o formato esperado pelo Voice Notes."
        )


def prompt_preview(summary_template: SummaryTemplate) -> str:
    """Return the read-only instruction used by a native or saved profile."""
    custom_prompt = _saved_custom_profile_prompt(
        summary_template, "<data da gravação>", "<transcrição da reunião>",
    )
    if custom_prompt is not None:
        return custom_prompt
    template_label, sections, profile_instructions = _summary_structure(summary_template)
    return _PROMPT_TEMPLATE.format(
        date="<data da gravação>",
        template_label=template_label,
        transcription="<transcrição da reunião>",
        profile_instructions=profile_instructions,
        sections=sections,
    )


def _saved_custom_profile_prompt(
    summary_template: SummaryTemplate, date_str: str, transcription_text: str,
) -> str | None:
    """Render an editable saved profile directly, keeping output guarantees intact."""
    if not summary_template.startswith("custom:"):
        return None
    from record_transcript_resume.summary_profiles import get_profile

    profile = get_profile(summary_template.removeprefix("custom:"))
    if profile is None:
        raise SynthesisError("O perfil personalizado selecionado não está mais disponível.")
    if profile.prompt_mode != "custom":
        return None
    prompt = profile.instructions.replace("<data da gravação>", date_str).replace(
        "<transcrição da reunião>", transcription_text,
    )
    if "<transcrição da reunião>" not in profile.instructions:
        prompt += f"\n\nTranscrição:\n{transcription_text}"
    if "<data da gravação>" not in profile.instructions:
        prompt += f"\n\nData da gravação: {date_str}"
    return prompt.rstrip() + _CUSTOM_PROFILE_SAFETY


def profile_prompt_seed(summary_template: SummaryTemplate, additions: str = "") -> str:
    """Return the complete native prompt as an editable saved-profile starting point."""
    template = summary_template if summary_template in SUMMARY_TEMPLATE_LABELS else DEFAULT_TEMPLATE
    seed = prompt_preview(template)
    if additions.strip():
        seed += f"\n\nOrientações adicionais:\n{additions.strip()}"
    return seed


def _summary_structure(summary_template: SummaryTemplate) -> tuple[str, str, str]:
    """Resolve built-in templates and persisted custom profiles at generation time."""
    if summary_template in SUMMARY_TEMPLATE_LABELS:
        sections = "\n".join(f"## {section}" for section in _TEMPLATE_SECTIONS[summary_template])
        return SUMMARY_TEMPLATE_LABELS[summary_template], sections, ""
    if summary_template.startswith("custom:"):
        from record_transcript_resume.summary_profiles import get_profile

        profile = get_profile(summary_template.removeprefix("custom:"))
        if profile is None:
            raise SynthesisError("O perfil personalizado selecionado não está mais disponível.")
        if profile.prompt_mode == "custom":
            instructions = (
                "\nPerfil personalizado escolhido pelo usuário:\n"
                f"{profile.instructions}\n"
                "Siga as instruções e a estrutura definidas neste perfil, sem inventar informações ausentes na transcrição.\n"
            )
            return profile.name, "Defina as seções em markdown de acordo com as instruções do perfil.", instructions
        base_sections = _TEMPLATE_SECTIONS.get(profile.base_template, _TEMPLATE_SECTIONS[DEFAULT_TEMPLATE])
        sections = "\n".join(f"## {section}" for section in base_sections)
        instructions = (
            "\nPerfil personalizado escolhido pelo usuário:\n"
            f"{profile.instructions}\n"
            "Use a estrutura solicitada acima. As seções abaixo são um ponto de partida; "
            "substitua, adicione ou reorganize-as quando isso for necessário para respeitar o perfil.\n"
        )
        return profile.name, sections, instructions
    raise SynthesisError(f"Unsupported summary template: {summary_template}")


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
    resolution = _resolve_cli(name)
    if resolution is not None:
        return resolution.executable
    if os.name == "nt":
        return f"{name}.cmd"
    return name


def provider_login_status(provider: SummaryProvider) -> ProviderLoginStatus:
    """Check the provider without sending transcript content or consuming credits.

    Both supported CLIs expose a non-interactive status command, so opening the
    widget never sends transcription content or consumes summary credits.
    """
    is_api_provider = provider == "api" or provider.startswith("api:")
    if provider not in SUPPORTED_PROVIDERS and not is_api_provider:
        raise ValueError(f"Unsupported summary provider: {provider}")

    if is_api_provider:
        from record_transcript_resume.api_provider import has_token
        provider_id = provider.partition(":")[2] or None
        return ProviderLoginStatus(installed=True, authenticated=has_token(provider_id), source="api")
    resolution = _resolve_cli(provider)
    if resolution is None:
        return ProviderLoginStatus(installed=False, authenticated=False)
    executable = resolution.executable
    status_args = ["login", "status"] if provider == "codex" else ["auth", "status"]
    try:
        result = subprocess.run(
            [executable, *status_args],
            capture_output=True,
            text=True,
            timeout=12,
            encoding="utf-8",
            env=_provider_environment(),
            **hidden_process_kwargs(),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ProviderLoginStatus(installed=False, authenticated=False)
    if provider == "claude":
        try:
            payload = json.loads(result.stdout or "{}")
            authenticated = bool(payload.get("loggedIn"))
        except json.JSONDecodeError:
            authenticated = result.returncode == 0
        return ProviderLoginStatus(
            installed=True, authenticated=authenticated,
            source=resolution.source, executable=executable,
        )
    return ProviderLoginStatus(
        installed=True, authenticated=result.returncode == 0,
        source=resolution.source, executable=executable,
    )


def start_provider_login(provider: SummaryProvider) -> subprocess.Popen[bytes]:
    """Start the provider's browser authentication flow without a console window.

    The command is deliberately opt-in from the widget.  It is not started at
    launch because doing so used to create an unexpected black ``cmd`` window.
    """
    if provider not in ("codex", "claude"):
        raise ValueError(f"Unsupported CLI provider: {provider}")
    resolution = _resolve_cli(provider)
    if resolution is None:
        raise FileNotFoundError(f"{provider} CLI was not found.")
    action = ["login"] if provider == "codex" else ["auth", "login"]
    return subprocess.Popen(
        [resolution.executable, *action],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_provider_environment(),
        **hidden_process_kwargs(),
    )


def _bundled_cli_path(name: str) -> Path | None:
    extension = ".cmd" if os.name == "nt" else ""
    # npm places global command shims at the prefix root on Windows (rather
    # than in ``bin`` as it does on Unix-like platforms).
    cli_home = app_data_dir() / "tools" / "cli"
    # Current installs use local npm packages; keep the old global-prefix
    # location as a migration path for installs made by earlier versions.
    candidates = (
        cli_home / "node_modules" / ".bin" / f"{name}{extension}",
        cli_home / f"{name}{extension}",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _resolve_cli(name: str) -> CliResolution | None:
    """Resolve a conventional system CLI first, then the private fallback.

    Existing Codex and Claude installations belong to the person using the
    computer, including their preferred version and authenticated account. A
    private Voice Notes copy is only a recovery path for machines without one.
    """
    candidates = (f"{name}.cmd", name) if os.name == "nt" else (name,)
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return CliResolution(found, "system")
    bundled = _bundled_cli_path(name)
    if bundled is not None:
        return CliResolution(str(bundled), "voice_notes")
    return None


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
