"""Pipeline subprocess entry point — isolated from GUI to survive native crashes in ctranslate2."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in {4, 5, 6, 7, 8}:
        print(json.dumps({"type": "error", "msg": "args: <mp3> <output_dir> <language> <model_size> [provider] [template] [diarize] [output_mode]"}), flush=True)
        return 1

    mp3_path = Path(args[0])
    output_dir = Path(args[1])
    language = args[2]
    model_size = args[3]
    provider = args[4] if len(args) >= 5 else "codex"
    summary_template = args[5] if len(args) >= 6 else "meeting"
    diarize_speakers = len(args) >= 7 and args[6] == "1"
    output_mode = args[7] if len(args) >= 8 else "both"

    def on_status(msg: str) -> None:
        print(json.dumps({"type": "status", "msg": msg}), flush=True)

    try:
        from record_transcript_resume.pipeline import run
        result = run(
            mp3_path, output_dir, language, model_size, provider, summary_template,
            on_status, diarize_speakers, os.environ.get("VOICE_NOTES_HF_TOKEN", ""), output_mode,
        )
        print(json.dumps({
            "type": "done",
            "folder": str(result.folder),
            "mp3": str(result.mp3_path),
            "transcript": str(result.transcript_path) if result.transcript_path else "",
            "summary": str(result.summary_path) if result.summary_path else "",
        }), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"type": "error", "msg": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
