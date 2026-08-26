from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.synthesis import (
    CliResolution,
    SynthesisResult,
    _cli_executable,
    generate,
    provider_login_status,
    start_provider_login,
)


def _make_completed_process(stdout: str, returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


class SynthesisTests(unittest.TestCase):
    def test_generate_returns_result_on_valid_json(self) -> None:
        payload = {
            "folder_name": "sprint-alignment",
            "summary_md": "# Meeting\n## Context\nText.",
        }
        proc = _make_completed_process(json.dumps(payload))

        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc):
            result = generate("Test transcription.", "2026-05-21")

        self.assertIsInstance(result, SynthesisResult)
        self.assertEqual(result.folder_name, "sprint-alignment")
        self.assertIn("# Meeting", result.summary_md)

    def test_generate_uses_fallback_on_invalid_json(self) -> None:
        proc = _make_completed_process("this is not valid json")

        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc):
            result = generate("Transcription.", "2026-05-21")

        self.assertEqual(result.folder_name, "")
        self.assertIn("unavailable", result.summary_md.lower())

    def test_generate_strips_markdown_fences(self) -> None:
        payload = {"folder_name": "product-meeting", "summary_md": "# Title"}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        proc = _make_completed_process(fenced)

        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc):
            result = generate("Transcription.", "2026-05-21")

        self.assertEqual(result.folder_name, "product-meeting")

    def test_generate_raises_on_claude_not_found(self) -> None:
        with patch("record_transcript_resume.synthesis.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(SynthesisError):
                generate("Transcription.", "2026-05-21")

    def test_generate_raises_on_timeout(self) -> None:
        with patch(
            "record_transcript_resume.synthesis.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120),
        ):
            with self.assertRaises(SynthesisError):
                generate("Transcription.", "2026-05-21")

    def test_generate_uses_codex_command_by_default(self) -> None:
        proc = _make_completed_process(json.dumps({"folder_name": "meeting", "summary_md": "# Summary"}))
        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc) as run:
            generate("Transcription.", "2026-05-21")

        command = run.call_args.args[0]
        expected_cli = "codex.cmd" if os.name == "nt" else "codex"
        self.assertTrue(command[0].lower().endswith(expected_cli))
        self.assertEqual(command[1:4], ["exec", "--ephemeral", "--skip-git-repo-check"])

    def test_generate_sends_selected_template(self) -> None:
        proc = _make_completed_process(json.dumps({"folder_name": "class", "summary_md": "# Aula"}))
        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc) as run:
            generate("Transcription.", "2026-05-21", summary_template="class")

        prompt = run.call_args.kwargs["input"]
        self.assertIn("Formato do resumo: Aula", prompt)
        self.assertIn("## Próximos estudos", prompt)
        self.assertIn("Idioma obrigatório da resposta: português do Brasil", prompt)

    def test_generate_uses_saved_custom_profile(self) -> None:
        from record_transcript_resume.summary_profiles import SummaryProfile

        proc = _make_completed_process(json.dumps({"folder_name": "assessment", "summary_md": "# Assessment"}))
        profile = SummaryProfile(id="assessment", name="Assessment", instructions="Agrupe por competência e cite evidências.")
        with (
            patch("record_transcript_resume.summary_profiles.get_profile", return_value=profile),
            patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc) as run,
        ):
            generate("Transcription.", "2026-05-21", summary_template="custom:assessment")

        prompt = run.call_args.kwargs["input"]
        self.assertIn("Formato do resumo: Assessment", prompt)
        self.assertIn("Agrupe por competência", prompt)

    def test_generate_raises_when_provider_cli_fails(self) -> None:
        proc = _make_completed_process("authentication failed", returncode=1)
        proc.stderr = "authentication failed"
        with patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc):
            with self.assertRaises(SynthesisError):
                generate("Transcription.", "2026-05-21", provider="codex")

    def test_generate_delegates_to_saved_api_provider(self) -> None:
        payload = json.dumps({"folder_name": "api-summary", "summary_md": "# Resumo"})
        with patch("record_transcript_resume.api_provider.generate", return_value=payload) as api:
            result = generate("Transcription.", "2026-05-21", provider="api")

        self.assertEqual(result.folder_name, "api-summary")
        self.assertTrue(api.called)

    def test_generate_delegates_to_selected_saved_api_provider(self) -> None:
        payload = json.dumps({"folder_name": "api-summary", "summary_md": "# Resumo"})
        with patch("record_transcript_resume.api_provider.generate", return_value=payload) as api:
            generate("Transcription.", "2026-05-21", provider="api:provider-123")

        api.assert_called_once()
        self.assertEqual(api.call_args.args[0].startswith("Você recebeu a transcrição"), True)
        self.assertEqual(api.call_args.kwargs["provider_id"], "provider-123")

    def test_codex_login_status_uses_noninteractive_command(self) -> None:
        proc = _make_completed_process("Logged in")
        with (
            patch("record_transcript_resume.synthesis._resolve_cli", return_value=CliResolution("C:/Voice Notes/codex.cmd", "voice_notes")),
            patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc) as run,
        ):
            status = provider_login_status("codex")

        self.assertTrue(status.installed)
        self.assertTrue(status.authenticated)
        self.assertEqual(status.source, "voice_notes")
        self.assertEqual(run.call_args.args[0][1:], ["login", "status"])

    def test_claude_login_status_reads_cli_response_without_sending_a_prompt(self) -> None:
        proc = _make_completed_process('{"loggedIn": false}', returncode=1)
        with (
            patch("record_transcript_resume.synthesis._resolve_cli", return_value=CliResolution("C:/tools/claude.cmd", "system")),
            patch("record_transcript_resume.synthesis.subprocess.run", return_value=proc) as run,
        ):
            status = provider_login_status("claude")

        self.assertTrue(status.installed)
        self.assertFalse(status.authenticated)
        self.assertEqual(status.source, "system")
        self.assertEqual(run.call_args.args[0][1:], ["auth", "status"])

    def test_codex_login_starts_directly_without_cmd_shell(self) -> None:
        with (
            patch("record_transcript_resume.synthesis._resolve_cli", return_value=CliResolution("C:/Voice Notes/codex.cmd", "voice_notes")),
            patch("record_transcript_resume.synthesis.subprocess.Popen") as popen,
        ):
            start_provider_login("codex")

        command = popen.call_args.args[0]
        self.assertIn("codex", command[0].lower())
        self.assertEqual(command[1:], ["login"])
        self.assertNotIn("cmd.exe", " ".join(command).lower())

    def test_claude_login_starts_directly_without_cmd_shell(self) -> None:
        with (
            patch("record_transcript_resume.synthesis._resolve_cli", return_value=CliResolution("C:/Voice Notes/claude.cmd", "voice_notes")),
            patch("record_transcript_resume.synthesis.subprocess.Popen") as popen,
        ):
            start_provider_login("claude")

        command = popen.call_args.args[0]
        self.assertIn("claude", command[0].lower())
        self.assertEqual(command[1:], ["auth", "login"])

    def test_system_cli_wins_over_private_copy(self) -> None:
        with (
            patch("record_transcript_resume.synthesis._bundled_cli_path", return_value=Path("C:/Voice Notes/tools/cli/codex.cmd")),
            patch("record_transcript_resume.synthesis.shutil.which", return_value="C:/Program Files/Codex/codex.cmd"),
        ):
            executable = _cli_executable("codex")

        self.assertEqual(executable, "C:/Program Files/Codex/codex.cmd")

    def test_private_cli_is_used_when_system_copy_is_missing(self) -> None:
        with (
            patch("record_transcript_resume.synthesis._bundled_cli_path", return_value=Path("C:/Voice Notes/tools/cli/codex.cmd")),
            patch("record_transcript_resume.synthesis.shutil.which", side_effect=[None, None]),
        ):
            executable = _cli_executable("codex")

        self.assertEqual(executable, "C:\\Voice Notes\\tools\\cli\\codex.cmd")

    def test_system_executable_is_used_when_private_copy_is_missing(self) -> None:
        with (
            patch("record_transcript_resume.synthesis._bundled_cli_path", return_value=None),
            patch("record_transcript_resume.synthesis.shutil.which", side_effect=[None, "C:/Program Files/Codex/codex.exe"]),
        ):
            executable = _cli_executable("codex")

        self.assertEqual(executable, "C:/Program Files/Codex/codex.exe")


if __name__ == "__main__":
    unittest.main()
