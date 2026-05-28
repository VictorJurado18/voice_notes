from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gravador_audio.errors import SynthesisError, TranscriptionError
from gravador_audio.synthesis import SynthesisResult, generate
from gravador_audio.transcription import Segment, segments_to_markdown, transcribe


@dataclass(frozen=True)
class PipelineResult:
    folder: Path
    mp3_path: Path
    transcricao_path: Path
    resumo_path: Path


def run(
    mp3_path: Path,
    output_dir: Path,
    language: str = "pt",
    model_size: str = "small",
    on_status: object = None,
) -> PipelineResult:
    def _notify(msg: str) -> None:
        if callable(on_status):
            on_status(msg)

    date_str = datetime.now().strftime("%Y-%m-%d")

    # Etapa 1: transcrição — se falhar, não move o MP3
    _notify("Transcrevendo audio...")
    segments: list[Segment] = transcribe(mp3_path, language=language, model_size=model_size)
    transcricao_texto = segments_to_markdown(segments)

    # Etapa 2: síntese — se falhar, usa fallback (nome genérico, resumo com aviso)
    _notify("Gerando resumo...")
    try:
        synthesis: SynthesisResult = generate(transcricao_texto, date_str)
    except SynthesisError:
        synthesis = SynthesisResult(nome_pasta="", resumo_md=_fallback_resumo())

    # Etapa 3: resolver nome e criar pasta
    folder = _resolve_folder(output_dir, synthesis.nome_pasta, date_str, mp3_path)
    folder.mkdir(parents=True, exist_ok=True)

    # Etapa 4: mover MP3
    new_mp3 = folder / mp3_path.name
    mp3_path.rename(new_mp3)

    # Etapa 5: salvar arquivos
    transcricao_path = folder / "transcricao.md"
    resumo_path = folder / "resumo.md"
    transcricao_path.write_text(f"# Transcricao\n\n{transcricao_texto}\n", encoding="utf-8")
    resumo_path.write_text(synthesis.resumo_md + "\n", encoding="utf-8")

    return PipelineResult(
        folder=folder,
        mp3_path=new_mp3,
        transcricao_path=transcricao_path,
        resumo_path=resumo_path,
    )


def _resolve_folder(output_dir: Path, nome_pasta: str, date_str: str, mp3_path: Path) -> Path:
    base_name = nome_pasta.strip() or f"gravacao-{mp3_path.stem}"
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = output_dir / f"{base_name}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _fallback_resumo() -> str:
    return (
        "# Resumo indisponivel\n\n"
        "A sintese automatica falhou (claude CLI indisponivel ou timeout).\n"
        "A transcricao completa esta em `transcricao.md`.\n"
    )
