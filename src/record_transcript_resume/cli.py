from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from record_transcript_resume.errors import RecordingError, TranscriptionError
from record_transcript_resume.paths import default_output_dir
from record_transcript_resume.recording import RecordingConfig, RecordingService
from record_transcript_resume.synthesis import DEFAULT_PROVIDER, SUPPORTED_PROVIDERS
from record_transcript_resume.windows_audio_backend import WindowsAudioBackend, WindowsAudioBackendConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="record-transcript-resume",
        description="Controls local audio recording on Windows.",
    )
    subparsers = parser.add_subparsers(dest="command")

    record = subparsers.add_parser("record", help="Record audio for a fixed duration.")
    record.add_argument("--output-dir", default=str(default_output_dir()), help="Output folder.")
    record.add_argument("--duration", type=float, default=10.0, help="Duration in seconds.")
    record.add_argument("--sample-rate", type=int, default=48_000, help="Sample rate.")
    record.add_argument("--bit-rate", type=int, default=192, help="MP3 bitrate in kbps.")
    record.add_argument("--microphone-only", action="store_true", help="Capture microphone only.")
    record.add_argument("--system-only", action="store_true", help="Capture system audio only.")
    record.add_argument("--no-pipeline", action="store_true", help="Skip transcription and summary after recording.")
    record.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=DEFAULT_PROVIDER, help="Summary provider. Default: codex.")

    process = subparsers.add_parser("process", help="Transcribe and summarize an existing MP3.")
    process.add_argument("file", type=Path, help="Path to the MP3 file.")
    process.add_argument("--language", default="pt", help="Language code for transcription (e.g. pt, en, es). Default: pt.")
    process.add_argument("--model", default="small", help="Whisper model (e.g. small, medium, large-v3). Default: small.")
    process.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=DEFAULT_PROVIDER, help="Summary provider. Default: codex.")

    return parser


def _run_record(args: argparse.Namespace) -> int:
    if args.duration <= 0:
        print("Duration must be greater than zero.", file=sys.stderr)
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
        print(f"Recording to: {output_path}")
        time.sleep(args.duration)
        service.stop()
    except RecordingError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Recording finished: {service.current_output_path}")

    if args.no_pipeline:
        return 0

    return _run_pipeline(service.current_output_path, language="pt", provider=args.provider)  # type: ignore[arg-type]


def _run_process(args: argparse.Namespace) -> int:
    mp3_path: Path = args.file
    if not mp3_path.exists():
        print(f"File not found: {mp3_path}", file=sys.stderr)
        return 2
    if mp3_path.suffix.lower() != ".mp3":
        print(f"File is not an MP3: {mp3_path}", file=sys.stderr)
        return 2
    return _run_pipeline(mp3_path, language=args.language, model_size=args.model, provider=args.provider)


def _run_pipeline(mp3_path: Path, language: str, model_size: str = "small", provider: str = DEFAULT_PROVIDER) -> int:
    from record_transcript_resume.pipeline import run

    def on_status(msg: str) -> None:
        print(msg)

    try:
        result = run(mp3_path, mp3_path.parent, language=language, model_size=model_size, provider=provider, on_status=on_status)
    except TranscriptionError as exc:
        print(f"Transcription error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1

    print(f"Folder created: {result.folder}")
    print(f"  transcription.md : {result.transcript_path}")
    print(f"  summary.md       : {result.summary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None or args.command == "record":
        if args.command is None:
            args2 = argparse.Namespace(
                duration=getattr(args, "duration", 10.0),
                output_dir=getattr(args, "output_dir", str(default_output_dir())),
                sample_rate=getattr(args, "sample_rate", 48_000),
                bit_rate=getattr(args, "bit_rate", 192),
                microphone_only=getattr(args, "microphone_only", False),
                system_only=getattr(args, "system_only", False),
                no_pipeline=getattr(args, "no_pipeline", False),
                provider=getattr(args, "provider", DEFAULT_PROVIDER),
            )
            return _run_record(args2)
        return _run_record(args)

    if args.command == "process":
        return _run_process(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
