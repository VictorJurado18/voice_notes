from __future__ import annotations

from record_transcript_resume.speaker_names import apply_speaker_names, suggest_speaker_names


def test_suggests_only_name_spoken_by_the_same_labeled_speaker() -> None:
    transcript = "[00:00:01] **Pessoa 1** · Olá, eu sou João da equipe.\n[00:00:03] **Pessoa 2** · Prazer, João."

    suggestions = suggest_speaker_names(transcript)

    assert [(item.speaker, item.name) for item in suggestions] == [("Pessoa 1", "João")]
    assert "**João**" in apply_speaker_names(transcript, suggestions)


def test_does_not_guess_names_only_called_by_other_people() -> None:
    transcript = "[00:00:01] **Pessoa 1** · João, você pode explicar?\n[00:00:03] **Pessoa 2** · Posso sim."

    assert suggest_speaker_names(transcript) == []
