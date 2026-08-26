"""Conservative, confirmable name suggestions from a diarized transcript."""
from __future__ import annotations

import re
from dataclasses import dataclass


_SPEAKER_LINE = re.compile(r"^\[[^\]]+\]\s+\*\*(Pessoa\s+\d+)\*\*\s+·\s+(.+)$", re.MULTILINE)
_SELF_INTRODUCTION = re.compile(
    r"\b(?:eu\s+sou|me\s+chamo|meu\s+nome\s+[ée]|aqui\s+[ée])\s+"
    r"([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’-]*(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’-]*)?)",
)


@dataclass(frozen=True)
class SpeakerNameSuggestion:
    speaker: str
    name: str
    reason: str


def suggest_speaker_names(transcript: str) -> list[SpeakerNameSuggestion]:
    """Return only explicit self-introductions; never guess from voice alone."""
    suggestions: list[SpeakerNameSuggestion] = []
    seen_speakers: set[str] = set()
    for match in _SPEAKER_LINE.finditer(transcript):
        speaker, spoken_text = match.groups()
        name_match = _SELF_INTRODUCTION.search(spoken_text)
        if name_match is None or speaker in seen_speakers:
            continue
        name = " ".join(part.capitalize() for part in name_match.group(1).split())
        suggestions.append(SpeakerNameSuggestion(speaker, name, "a pessoa se apresentou na própria fala"))
        seen_speakers.add(speaker)
    return suggestions


def apply_speaker_names(transcript: str, suggestions: list[SpeakerNameSuggestion]) -> str:
    """Rename speaker labels only, after the user confirms the suggestions."""
    updated = transcript
    for suggestion in suggestions:
        updated = updated.replace(f"**{suggestion.speaker}**", f"**{suggestion.name}**")
    return updated


def speaker_labels(transcript: str) -> list[str]:
    """Return the diarization labels in their first-appearance order."""
    labels: list[str] = []
    for label in _SPEAKER_LINE.findall(transcript):
        speaker = label[0] if isinstance(label, tuple) else label
        if speaker not in labels:
            labels.append(speaker)
    return labels


def apply_speaker_name_map(transcript: str, names: dict[str, str]) -> str:
    """Apply only explicitly entered names, never infer one from voice data."""
    updated = transcript
    for speaker, name in names.items():
        cleaned = name.strip()
        if cleaned:
            updated = updated.replace(f"**{speaker}**", f"**{cleaned}**")
    return updated
