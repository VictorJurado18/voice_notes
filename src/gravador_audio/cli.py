from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from gravador_audio.errors import RecordingError
from gravador_audio.paths import default_output_dir
from gravador_audio.recording import RecordingConfig, RecordingService
from gravador_audio.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gravador-audio",
        description="Controla a gravacao local de audio no Windows.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help="Pasta onde a gravacao sera salva.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Duracao da gravacao em segundos.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=48_000,
        help="Taxa de amostragem da captura.",
    )
    parser.add_argument(
        "--bit-rate",
        type=int,
        default=192,
        help="Bitrate MP3 em kbps.",
    )
    parser.add_argument(
        "--microphone-only",
        action="store_true",
        help="Captura apenas o microfone.",
    )
    parser.add_argument(
        "--system-only",
        action="store_true",
        help="Captura apenas o audio do sistema.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
