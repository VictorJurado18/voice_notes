from __future__ import annotations

from pathlib import Path

from record_transcript_resume.summary_profiles import SummaryProfile, get_profile, load_profiles, save_profile


def test_saving_profile_preserves_existing_profiles(tmp_path: Path) -> None:
    path = tmp_path / "summary-profiles.json"
    first = save_profile(SummaryProfile(name="Assessment", instructions="Priorize evidências e riscos."), path)
    second = save_profile(SummaryProfile(name="Entrevista técnica", instructions="Liste respostas por competência."), path)

    assert [item.name for item in load_profiles(path)] == ["Assessment", "Entrevista técnica"]
    assert get_profile(first.id, path) is not None
    assert get_profile(second.id, path) is not None


def test_profile_requires_name_and_instructions(tmp_path: Path) -> None:
    path = tmp_path / "summary-profiles.json"
    try:
        save_profile(SummaryProfile(name="Sem formato", instructions=""), path)
    except ValueError as exc:
        assert "organizado" in str(exc)
    else:
        raise AssertionError("Um perfil sem instruções não deveria ser salvo")


def test_profile_name_must_be_unique(tmp_path: Path) -> None:
    path = tmp_path / "summary-profiles.json"
    save_profile(SummaryProfile(name="Assessment", instructions="Estruture por competência."), path)

    try:
        save_profile(SummaryProfile(name="assessment", instructions="Outro formato."), path)
    except ValueError as exc:
        assert "existe" in str(exc)
    else:
        raise AssertionError("Perfis com o mesmo nome não deveriam ser ambíguos")
