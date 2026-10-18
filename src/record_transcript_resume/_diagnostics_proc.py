"""Isolated entry point for diagnostics that load native audio/model libraries."""
from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "local-transcription":
        print(json.dumps({
            "type": "error",
            "msg": "args: local-transcription <model_size>",
            "error_type": "ValueError",
        }), flush=True)
        return 1

    model_size = args[1]
    try:
        from record_transcript_resume.transcription import test_local_transcription

        test_local_transcription(model_size)
        print(json.dumps({"type": "done", "model": model_size}), flush=True)
        return 0
    except Exception as exc:
        from record_transcript_resume.log import log_exception

        try:
            log_exception(f"Local transcription diagnostic failed | model={model_size}", exc)
        except Exception:
            pass
        print(json.dumps({
            "type": "error",
            "msg": str(exc).strip() or "O teste local falhou sem uma mensagem de erro.",
            "error_type": type(exc).__name__,
        }), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
