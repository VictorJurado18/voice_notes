"""Durable local queue for transcription and summary jobs.

The queue intentionally stores only paths and processing choices. Audio and
transcription contents remain in their normal folders and are never copied to
the app-data directory.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from record_transcript_resume.paths import app_data_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ProcessingJob:
    id: str
    mp3_path: str
    output_dir: str
    language: str
    model_size: str
    provider: str
    summary_template: str
    status: str
    stage: str
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    output_mode: str = "both"
    transcription_provider: str = "local"
    additional_instructions: str = ""
    separate_speakers: bool = False
    preserve_source: bool = False
    reuse_source_folder: bool = False
    summary_failed: bool = False

    @property
    def audio_path(self) -> Path:
        return Path(self.mp3_path)


class JobStore:
    """Small JSON-backed queue that survives widget restarts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "processing-jobs.json"

    def list(self) -> list[ProcessingJob]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        jobs: list[ProcessingJob] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            try:
                jobs.append(ProcessingJob(**entry))
            except TypeError:
                continue
        return jobs

    def enqueue(
        self,
        mp3_path: Path,
        output_dir: Path,
        language: str,
        model_size: str,
        provider: str,
        summary_template: str,
        output_mode: str = "both",
        transcription_provider: str = "local",
        additional_instructions: str = "",
        separate_speakers: bool = False,
        preserve_source: bool = False,
        reuse_source_folder: bool = False,
    ) -> ProcessingJob:
        jobs = self.list()
        normalized = str(mp3_path.resolve())
        for job in jobs:
            if job.mp3_path == normalized and job.status in {"queued", "running"}:
                return job
        now = _now()
        job = ProcessingJob(
            id=uuid4().hex,
            mp3_path=normalized,
            output_dir=str(output_dir.resolve()),
            language=language,
            model_size=model_size,
            provider=provider,
            summary_template=summary_template,
            status="queued",
            stage="Na fila",
            created_at=now,
            updated_at=now,
            output_mode=output_mode,
            transcription_provider=transcription_provider,
            additional_instructions=additional_instructions,
            separate_speakers=separate_speakers,
            preserve_source=preserve_source,
            reuse_source_folder=reuse_source_folder,
        )
        self._save([*jobs, job])
        return job

    def update(self, job_id: str, **changes: str) -> ProcessingJob | None:
        updated: ProcessingJob | None = None
        jobs: list[ProcessingJob] = []
        for job in self.list():
            if job.id == job_id:
                updated = replace(job, **changes, updated_at=_now())
                jobs.append(updated)
            else:
                jobs.append(job)
        if updated is not None:
            self._save(jobs)
        return updated

    def remove(self, job_id: str) -> bool:
        """Remove one queue record without touching its audio or documents."""
        jobs = self.list()
        remaining = [job for job in jobs if job.id != job_id]
        if len(remaining) == len(jobs):
            return False
        self._save(remaining)
        return True

    def relocate_tree(self, source: Path, destination: Path) -> None:
        """Update saved job paths after a library folder is moved or renamed."""
        source = source.resolve()
        destination = destination.resolve()

        def relocated(value: str) -> str:
            path = Path(value)
            try:
                relative = path.resolve().relative_to(source)
            except ValueError:
                return value
            return str(destination / relative)

        jobs = self.list()
        changed = [
            replace(job, mp3_path=relocated(job.mp3_path), output_dir=relocated(job.output_dir))
            for job in jobs
        ]
        if changed != jobs:
            self._save(changed)

    def recoverable(self) -> list[ProcessingJob]:
        """Return interrupted jobs whose original audio still exists.

        A job that had already moved its MP3 is deliberately not restarted: its
        completed folder can be opened from the library instead of risking a
        duplicate transcription.
        """
        recoverable: list[ProcessingJob] = []
        for job in self.list():
            if job.status not in {"queued", "running"}:
                continue
            if not job.audio_path.is_file():
                self.update(job.id, status="needs_attention", stage="Verifique a biblioteca", error="Áudio já não está na pasta original.")
                continue
            recovered = self.update(job.id, status="queued", stage="Retomando após reinício", error="")
            if recovered is not None:
                recoverable.append(recovered)
        return recoverable

    def _save(self, jobs: list[ProcessingJob]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([asdict(job) for job in jobs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
