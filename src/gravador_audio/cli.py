from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from gravador_audio.errors import RecordingError, TranscriptionError
from gravador_audio.paths import default_output_dir
from gravador_audio.recording import RecordingConfig, RecordingService
from gravador_audio.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gravador-audio",
        description="Controla a gravacao local de audio no Windows.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Subcomando: gravar (comportamento original, agora explícito)
    gravar = subparsers.add_parser("gravar", help="Grava audio por uma duracao fixa.")
    gravar.add_argument("--output-dir", default=str(default_output_dir()), help="Pasta de saida.")
    gravar.add_argument("--duration", type=float, default=10.0, help="Duracao em segundos.")
    gravar.add_argument("--sample-rate", type=int, default=48_000, help="Taxa de amostragem.")
    gravar.add_argument("--bit-rate", type=int, default=192, help="Bitrate MP3 em kbps.")
    gravar.add_argument("--microphone-only", action="store_true", help="Captura apenas o microfone.")
    gravar.add_argument("--system-only", action="store_true", help="Captura apenas o audio do sistema.")
    gravar.add_argument("--no-pipeline", action="store_true", help="Nao executar transcricao/sintese apos gravar.")

    # Subcomando: processar
    processar = subparsers.add_parser("processar", help="Transcreve e sintetiza um MP3 existente.")
    processar.add_argument("arquivo", type=Path, help="Caminho para o arquivo MP3.")
    processar.add_argument("--idioma", default="pt", help="Codigo do idioma para transcricao (ex: pt, en, es). Padrao: pt.")

    return parser


def _run_gravar(args: argparse.Namespace) -> int:
    if args.duration <= 0:
        print("A duracao deve ser maior que zero.", file=sys.stderr)
        return 2

    backend_config = WindowsAudioBackendConfig(
        sample_rate=args.sample_rate,
        bit_rate_kbps=args.bit_rate,
        capture_microphone=not args.system_only,
        capture_system_audio=not args.microphone_only,
    )
    service = RecordingService(
        config=RecordingConfig(output_dir=Path(args.output_dir)),
        backend=WindowsAudioBackend(backend_config),
    )

    try:
        output_path = service.start()
        print(f"Gravando em: {output_path}")
        time.sleep(args.duration)
        service.stop()
    except RecordingError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Gravacao finalizada: {service.current_output_path}")

    if args.no_pipeline:
        return 0

    return _run_pipeline(service.current_output_path, language="pt")  # type: ignore[arg-type]


def _run_processar(args: argparse.Namespace) -> int:
    mp3_path: Path = args.arquivo
    if not mp3_path.exists():
        print(f"Arquivo nao encontrado: {mp3_path}", file=sys.stderr)
        return 2
    if mp3_path.suffix.lower() != ".mp3":
        print(f"Arquivo nao e MP3: {mp3_path}", file=sys.stderr)
        return 2
    return _run_pipeline(mp3_path, language=args.idioma)


def _run_pipeline(mp3_path: Path, language: str) -> int:
    from gravador_audio.pipeline import run

    def on_status(msg: str) -> None:
        print(msg)

    try:
        result = run(mp3_path, mp3_path.parent, language=language, on_status=on_status)
    except TranscriptionError as exc:
        print(f"Erro na transcricao: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Erro no pipeline: {exc}", file=sys.stderr)
        return 1

    print(f"Pasta criada: {result.folder}")
    print(f"  transcricao.md : {result.transcricao_path}")
    print(f"  resumo.md      : {result.resumo_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Compatibilidade: sem subcomando roda o comportamento original (gravar)
    if args.command is None or args.command == "gravar":
        if args.command is None:
            # Redireciona flags legadas para o subcomando gravar
            args2 = argparse.Namespace(
                duration=getattr(args, "duration", 10.0),
                output_dir=getattr(args, "output_dir", str(default_output_dir())),
                sample_rate=getattr(args, "sample_rate", 48_000),
                bit_rate=getattr(args, "bit_rate", 192),
                microphone_only=getattr(args, "microphone_only", False),
                system_only=getattr(args, "system_only", False),
                no_pipeline=getattr(args, "no_pipeline", False),
            )
            return _run_gravar(args2)
        return _run_gravar(args)

    if args.command == "processar":
        return _run_processar(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
