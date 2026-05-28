"""Pipeline subprocess entry point — isolated from GUI to survive native crashes in ctranslate2."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 5:
        print(json.dumps({"type": "error", "msg": "args: <mp3> <output_dir> <language> <model_size>"}), flush=True)
        return 1

    mp3_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    language = sys.argv[3]
    model_size = sys.argv[4]

    def on_status(msg: str) -> None:
        print(json.dumps({"type": "status", "msg": msg}), flush=True)

    try:
        from gravador_audio.pipeline import run
        result = run(mp3_path, output_dir, language, model_size, on_status)
        print(json.dumps({
            "type": "done",
            "folder": str(result.folder),
            "mp3": str(result.mp3_path),
            "transcricao": str(result.transcricao_path),
            "resumo": str(result.resumo_path),
        }), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"type": "error", "msg": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
