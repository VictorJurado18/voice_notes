from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from gravador_audio.errors import SynthesisError

_TIMEOUT = 120

_PROMPT_TEMPLATE = """\
Voce recebeu a transcricao de uma reuniao/call gravada.

Data da gravacao: {date}

Transcricao:
{transcription}

Responda APENAS com um objeto JSON valido, sem markdown, sem explicacao:
{{"nome_pasta": "<nome curto em kebab-case, em portugues, max 60 chars, sem data>", "resumo_md": "<conteudo markdown completo do resumo>"}}

O resumo_md deve conter exatamente estas secoes em markdown:
# [Titulo da reuniao]
## Contexto
## Principais pontos discutidos
## Decisoes tomadas
## Plano de acao
## Proximos passos\
"""


@dataclass(frozen=True)
class SynthesisResult:
    nome_pasta: str
    resumo_md: str


def generate(transcription_text: str, date_str: str) -> SynthesisResult:
    prompt = _PROMPT_TEMPLATE.format(date=date_str, transcription=transcription_text)

    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise SynthesisError(
            "claude CLI nao encontrado no PATH. Instale o Claude Code."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SynthesisError(
            f"Timeout: claude -p nao respondeu em {_TIMEOUT}s."
        ) from exc

    stdout = result.stdout.strip()

    # Remove bloco ```json ... ``` se Claude retornar com markdown
    if stdout.startswith("```"):
        lines = stdout.splitlines()
        stdout = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(stdout)
        nome_pasta = str(data["nome_pasta"]).strip()
        resumo_md = str(data["resumo_md"]).strip()
        return SynthesisResult(nome_pasta=nome_pasta, resumo_md=resumo_md)
    except (json.JSONDecodeError, KeyError):
        # Fallback: nome generico, resumo com aviso
        resumo_fallback = (
            "# Resumo indisponivel\n\n"
            "A sintese automatica falhou. Transcrição salva em `transcricao.md`.\n\n"
            f"Saida bruta do Claude:\n\n```\n{result.stdout[:2000]}\n```"
        )
        return SynthesisResult(nome_pasta="", resumo_md=resumo_fallback)
