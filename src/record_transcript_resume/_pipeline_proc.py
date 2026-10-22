"""Pipeline subprocess entry point — isolated from GUI to survive native crashes in ctranslate2."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in {4, 5, 6, 7, 8, 9, 10, 11, 12}:
        print(json.dumps({"type": "error", "msg": "args: <media> <output_dir> <language> <model_size> [provider] [template] [diarize] [output_mode] [transcription_provider] [additional_instructions] [preserve_source] [reuse_source_folder]"}), flush=True)
        return 1

    mp3_path = Path(args[0])
    output_dir = Path(args[1])
    language = args[2]
    model_size = args[3]
    provider = args[4] if len(args) >= 5 else "codex"
    summary_template = args[5] if len(args) >= 6 else "meeting"
    diarize_speakers = len(args) >= 7 and args[6] == "1"
    output_mode = args[7] if len(args) >= 8 else "both"
    transcription_provider = args[8] if len(args) >= 9 else "local"
    additional_instructions = args[9] if len(args) >= 10 else ""
    preserve_source = len(args) >= 11 and args[10] == "1"
    reuse_source_folder = len(args) >= 12 and args[11] == "1"

    def on_status(msg: str) -> None:
        print(json.dumps({"type": "status", "msg": msg}), flush=True)

    try:
        import time
        from record_transcript_resume.processing_metrics import media_duration
        started = time.monotonic()
        audio_seconds = media_duration(mp3_path)
        if audio_seconds > 0:
            print(json.dumps({"type": "metadata", "audio_seconds": audio_seconds}), flush=True)
        from record_transcript_resume.pipeline import run
        result = run(
            mp3_path, output_dir, language, model_size, provider, summary_template,
            on_status, diarize_speakers, os.environ.get("VOICE_NOTES_HF_TOKEN", ""),
            output_mode, transcription_provider, additional_instructions,
            preserve_source, reuse_source_folder,
            defer_content_name=True,
        )
        print(json.dumps({
            "type": "done",
            "folder": str(result.folder),
            "mp3": str(result.mp3_path),
            "transcript": str(result.transcript_path) if result.transcript_path else "",
            "summary": str(result.summary_path) if result.summary_path else "",
            "warnings": list(result.warnings),
            "summary_failed": result.summary_failed,
            "audio_seconds": audio_seconds,
            "processing_seconds": time.monotonic() - started,
            "previous_folder": str(result.previous_folder) if result.previous_folder else "",
            "content_name": result.content_name,
            "source_folder": str(result.source_folder) if result.source_folder else "",
        }), flush=True)
        return 0
    except Exception as exc:
        from record_transcript_resume.log import log_exception

        try:
            log_exception("Pipeline worker failed", exc)
        except Exception:
            pass
        print(json.dumps({
            "type": "error",
            "msg": str(exc).strip() or "O processamento falhou sem uma mensagem de erro.",
            "error_type": type(exc).__name__,
        }), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
