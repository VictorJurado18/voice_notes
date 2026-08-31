from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import time

from record_transcript_resume.errors import SynthesisError, TranscriptionError
from record_transcript_resume.synthesis import DEFAULT_PROVIDER, DEFAULT_TEMPLATE, SummaryProvider, SummaryTemplate, SynthesisResult, generate
from record_transcript_resume.transcription import Segment, assign_speakers, segments_to_markdown, transcribe


def _elapsed(started: float) -> str:
    return f"{time.monotonic() - started:.1f}s"


@dataclass(frozen=True)
class PipelineResult:
    folder: Path
    mp3_path: Path
    transcript_path: Path | None
    summary_path: Path | None


def run(
    mp3_path: Path,
    output_dir: Path,
    language: str = "pt",
    model_size: str = "small",
    provider: SummaryProvider = DEFAULT_PROVIDER,
    summary_template: SummaryTemplate = DEFAULT_TEMPLATE,
    on_status: object = None,
    diarize_speakers: bool = False,
    huggingface_token: str = "",
    output_mode: str = "both",
    transcription_provider: str = "local",
    additional_instructions: str = "",
) -> PipelineResult:
    def _notify(msg: str) -> None:
        if callable(on_status):
            on_status(msg)

    if output_mode not in {"both", "transcription", "summary"}:
        raise ValueError(f"Unsupported output mode: {output_mode}")
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Step 1: transcription — if it fails, do not move the MP3
    _notify("Transcribing audio...")
    transcription_started = time.monotonic()
    segments: list[Segment] = transcribe(
        mp3_path, language=language, model_size=model_size, provider=transcription_provider,
    )
    from record_transcript_resume.log import log
    log(f"Pipeline transcription finished | elapsed={_elapsed(transcription_started)} model={model_size}")
    if diarize_speakers:
        _notify("Identifying speakers...")
        diarization_started = time.monotonic()
        from record_transcript_resume.diarization import diarize
        segments = assign_speakers(segments, diarize(mp3_path, huggingface_token))
        log(f"Pipeline speaker separation finished | elapsed={_elapsed(diarization_started)}")
    transcript_text = segments_to_markdown(segments)

    synthesis = SynthesisResult(folder_name="", summary_md="")
    if output_mode != "transcription":
        # Synthesis failure is saved as a helpful fallback, preserving the audio.
        _notify("Generating summary...")
        synthesis_started = time.monotonic()
        try:
            synthesis = generate(
                transcript_text,
                date_str,
                provider=provider,
                summary_template=summary_template,
                additional_instructions=additional_instructions,
            )
        except SynthesisError as exc:
            synthesis = SynthesisResult(
                folder_name="",
                summary_md=_fallback_summary(provider, str(exc)),
            )
        log(f"Pipeline summary finished | elapsed={_elapsed(synthesis_started)}")

    # Step 3: resolve folder name and create it
    folder = _resolve_folder(output_dir, synthesis.folder_name, date_str, mp3_path)
    folder.mkdir(parents=True, exist_ok=True)

    # Step 4: move MP3
    new_mp3 = folder / mp3_path.name
    mp3_path.rename(new_mp3)

    # Step 5: save output files
    transcript_path: Path | None = None
    summary_path: Path | None = None
    if output_mode != "summary":
        transcript_path = folder / "transcription.md"
        transcript_path.write_text(f"# Transcription\n\n{transcript_text}\n", encoding="utf-8")
    if output_mode != "transcription":
        summary_path = folder / "summary.md"
        summary_path.write_text(synthesis.summary_md + "\n", encoding="utf-8")

    return PipelineResult(
        folder=folder,
        mp3_path=new_mp3,
        transcript_path=transcript_path,
        summary_path=summary_path,
    )


def retry_summary(
    transcript_path: Path,
    provider: SummaryProvider = DEFAULT_PROVIDER,
    summary_template: SummaryTemplate = DEFAULT_TEMPLATE,
    on_status: object = None,
    additional_instructions: str = "",
) -> Path:
    """Regenerate only ``summary.md`` from an existing saved transcription.

    The original MP3 and ``transcription.md`` stay untouched. If the provider
    still fails, the previous summary is preserved so a useful error never
    replaces an earlier successful result.
    """
    if not transcript_path.is_file():
        raise FileNotFoundError(f"Transcription file not found: {transcript_path}")
    if transcript_path.name.lower() != "transcription.md":
        raise ValueError("Select the Voice Notes transcription.md file.")

    raw_text = transcript_path.read_text(encoding="utf-8").strip()
    transcript_text = _transcript_body(raw_text)
    if not transcript_text:
        raise TranscriptionError("The selected transcription is empty.")

    if callable(on_status):
        on_status("Generating summary again...")
    synthesis = generate(
        transcript_text,
        datetime.now().strftime("%Y-%m-%d"),
        provider=provider,
        summary_template=summary_template,
        additional_instructions=additional_instructions,
    )
    if synthesis.summary_md.lstrip().startswith("# Summary unavailable"):
        raise SynthesisError("The provider did not return a valid summary. Try again after checking the login.")

    summary_path = transcript_path.with_name("summary.md")
    summary_path.write_text(synthesis.summary_md.rstrip() + "\n", encoding="utf-8")
    return summary_path


def _transcript_body(text: str) -> str:
    """Remove the document title written by this app before resending text."""
    for header in ("# Transcription", "# Transcrição"):
        if text.casefold().startswith(header.casefold()):
            return text[len(header):].lstrip("\r\n ")
    return text


def _resolve_folder(output_dir: Path, folder_name: str, date_str: str, mp3_path: Path) -> Path:
    base_name = _safe_folder_name(folder_name) or _safe_folder_name(f"recording-{mp3_path.stem}") or "recording"
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = output_dir / f"{base_name}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _safe_folder_name(value: str) -> str:
    """Return a portable folder name and never accept model-provided path syntax."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:60]


def _fallback_summary(provider: str, detail: str) -> str:
    return (
        "# Summary unavailable\n\n"
        f"Automatic synthesis with {provider} failed.\n\n"
        "The full transcription is in `transcription.md`.\n\n"
        f"Details: {detail}\n"
    )
