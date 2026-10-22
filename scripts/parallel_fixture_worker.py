"""Synthetic upstreams for verify_parallel_processing.py; no accounts or devices."""
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from record_transcript_resume import pipeline
from record_transcript_resume.transcription import Segment
from record_transcript_resume.synthesis import SynthesisResult
from record_transcript_resume._pipeline_proc import main


def synthetic_transcription(path, **kwargs):
    end = time.monotonic() + (15 if "cancel" in path.name else 3)
    block = b"synthetic cpu work" * 4096
    while time.monotonic() < end:
        hashlib.sha256(block).digest()
    return [Segment(0, 30, "Revisão do cronograma das entregas.")]


pipeline.transcribe = synthetic_transcription
pipeline.generate = lambda *args, **kwargs:SynthesisResult(
    "revisao-do-cronograma", "# Planejamento\n\nRevisão do cronograma das entregas.", "Revisão do cronograma das entregas")
raise SystemExit(main(sys.argv[1:]))
