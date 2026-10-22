from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import shutil
import time

from record_transcript_resume.errors import SynthesisError, TranscriptionError
from record_transcript_resume.meeting_naming import is_meeting_folder, recording_time, rename_meeting, safe_name
from record_transcript_resume.meeting_topics import save_metadata
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
    warnings: tuple[str, ...] = ()
    summary_failed: bool = False
    audio_seconds: float = 0.0
    processing_seconds: float = 0.0
    previous_folder: Path | None = None
    content_name: str = ""
    source_folder: Path | None = None


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
    preserve_source: bool = False,
    reuse_source_folder: bool = False,
    defer_content_name: bool = False,
) -> PipelineResult:
    def _notify(msg: str) -> None:
        if callable(on_status):
            on_status(msg)

    if output_mode not in {"both", "transcription", "summary"}:
        raise ValueError(f"Unsupported output mode: {output_mode}")
    if preserve_source and reuse_source_folder:
        raise ValueError("Imported media cannot reuse its source folder.")
    if preserve_source:
        output_dir.mkdir(parents=True, exist_ok=True)
        required = mp3_path.stat().st_size + 50 * 1024 * 1024
        if shutil.disk_usage(output_dir).free < required:
            raise TranscriptionError(
                "Espaço insuficiente para copiar o arquivo importado à Biblioteca. "
                "Libere espaço na pasta de destino ou escolha outra pasta em Gravar. "
                "O arquivo original foi preservado."
            )
    date_str = datetime.now().strftime("%Y-%m-%d")
    recorded_at = recording_time(mp3_path) or datetime.fromtimestamp(mp3_path.stat().st_mtime)

    # Step 1: transcription — if it fails, do not move the MP3
    _notify("Transcribing audio...")
    transcription_started = time.monotonic()
    segments: list[Segment] = transcribe(
        mp3_path, language=language, model_size=model_size, provider=transcription_provider,
    )
    from record_transcript_resume.log import log
    log(f"Pipeline transcription finished | elapsed={_elapsed(transcription_started)} model={model_size}")
    warnings: list[str] = []
    if diarize_speakers:
        _notify("Identifying speakers...")
        diarization_started = time.monotonic()
        from record_transcript_resume.diarization import diarize
        try:
            segments = assign_speakers(segments, diarize(mp3_path, huggingface_token))
            log(f"Pipeline speaker separation finished | elapsed={_elapsed(diarization_started)}")
        except Exception as exc:
            warning = "Não foi possível separar os falantes; a transcrição continuou sem identificá-los."
            warnings.append(warning)
            _notify(warning)
            log(
                "Pipeline speaker separation skipped after failure | "
                f"elapsed={_elapsed(diarization_started)} error={type(exc).__name__}: {exc}"
            )
    transcript_text = segments_to_markdown(segments)

    synthesis = SynthesisResult(folder_name="", summary_md="")
    summary_failed = False
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
            if synthesis.summary_md.lstrip().startswith("# Summary unavailable"):
                summary_failed = True
                warning = (
                    "A transcrição foi concluída, mas o provider não retornou um resumo no formato esperado. "
                    "Consulte o resumo salvo e tente novamente após verificar o provider."
                )
                warnings.append(warning)
                _notify(warning)
        except SynthesisError as exc:
            summary_failed = True
            synthesis = SynthesisResult(
                folder_name="",
                summary_md=_fallback_summary(provider, str(exc)),
            )
            warnings.append(f"A transcrição foi concluída, mas o resumo falhou: {exc}")
            _notify(warnings[-1])
        log(f"Pipeline summary finished | elapsed={_elapsed(synthesis_started)}")

    # Never rename a shared directory or overwrite another audio's documents.
    reuse_meeting = reuse_source_folder and is_meeting_folder(mp3_path)
    folder = mp3_path.parent if reuse_meeting else _resolve_folder(
        output_dir, synthesis.folder_name if not summary_failed else "", date_str, mp3_path,
    )
    folder.mkdir(parents=True, exist_ok=True)

    # Step 4: recordings are moved into their result folder; imported media
    # remains at its original location and is copied into the library.
    new_mp3 = folder / mp3_path.name
    if preserve_source:
        temporary_copy = new_mp3.with_name(new_mp3.name + ".partial")
        try:
            shutil.copy2(mp3_path, temporary_copy)
            temporary_copy.replace(new_mp3)
        finally:
            temporary_copy.unlink(missing_ok=True)
    elif mp3_path != new_mp3:
        mp3_path.rename(new_mp3)

    # Step 5: save output files
    transcript_path: Path | None = None
    summary_path: Path | None = None
    if output_mode != "summary" or summary_failed:
        transcript_path = folder / "transcription.md"
        transcript_path.write_text(f"# Transcription\n\n{transcript_text}\n", encoding="utf-8")
    if output_mode != "transcription":
        summary_path = folder / "summary.md"
        summary_path.write_text(synthesis.summary_md + "\n", encoding="utf-8")
        if not summary_failed and synthesis.topic:
            try:
                from record_transcript_resume.meeting_topics import save_topic
                save_topic(folder, synthesis.topic)
            except OSError as exc:
                warnings.append(f"Resumo salvo, mas a descrição curta não pôde ser salva: {exc}")

    # Save documents before renaming. A locked file must not turn successful
    # transcription into a failed job or leave callers pointing at missing paths.
    content_name = ""
    try:
        save_metadata(folder, recorded_at=recorded_at.isoformat(), audio_file=new_mp3.name)
    except OSError as exc:
        warnings.append(f"Não foi possível salvar a data original da gravação: {exc}")
    else:
        if not summary_failed and output_mode != "transcription" and safe_name(synthesis.folder_name):
            content_name = safe_name(synthesis.folder_name)

    result = PipelineResult(
        folder=folder,
        mp3_path=new_mp3,
        transcript_path=transcript_path,
        summary_path=summary_path,
        warnings=tuple(warnings),
        summary_failed=summary_failed,
        content_name=content_name,
        source_folder=mp3_path.parent if reuse_meeting else None,
    )
    return result if defer_content_name else finalize_content_name(result)


def finalize_content_name(result: PipelineResult) -> PipelineResult:
    """Apply a saved result's name. The GUI calls this after worker completion,
    on the UI thread, so Cancel cannot kill the worker halfway through a rename.
    Only directory entries are renamed; audio bytes are never decoded or copied.
    """
    if not result.content_name:
        return result
    named = rename_meeting(result.mp3_path, result.content_name)
    folder = named.audio.parent
    warnings = list(result.warnings)
    if named.warning:
        warnings.append(named.warning)
    try:
        save_metadata(folder, audio_file=named.audio.name)
    except OSError as exc:
        warnings.append(f"Nome aplicado, mas os metadados não puderam ser atualizados: {exc}")
    return replace(
        result, folder=folder, mp3_path=named.audio,
        transcript_path=folder / result.transcript_path.name if result.transcript_path else None,
        summary_path=folder / result.summary_path.name if result.summary_path else None,
        previous_folder=named.moved_folder if named.moved_folder == result.source_folder else None,
        warnings=tuple(warnings), content_name="", source_folder=None,
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
    if synthesis.topic:
        try:
            from record_transcript_resume.meeting_topics import save_topic
            save_topic(summary_path.parent, synthesis.topic)
        except OSError:
            import logging
            logging.getLogger(__name__).warning("Resumo salvo sem descrição curta", exc_info=True)
    return summary_path


def _transcript_body(text: str) -> str:
    """Remove the document title written by this app before resending text."""
    for header in ("# Transcription", "# Transcrição"):
        if text.casefold().startswith(header.casefold()):
            return text[len(header):].lstrip("\r\n ")
    return text


def _resolve_folder(output_dir: Path, folder_name: str, date_str: str, mp3_path: Path) -> Path:
    base_name = _safe_folder_name(folder_name) or _safe_folder_name(mp3_path.stem) or "recording"
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
    return safe_name(value)


def _fallback_summary(provider: str, detail: str) -> str:
    return (
        "# Summary unavailable\n\n"
        f"Automatic synthesis with {provider} failed.\n\n"
        "The full transcription is in `transcription.md`.\n\n"
        f"Details: {detail}\n"
    )
