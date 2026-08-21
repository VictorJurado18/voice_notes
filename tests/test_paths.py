from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from record_transcript_resume.paths import app_data_dir, default_output_dir


class PathTests(unittest.TestCase):
    def test_default_output_dir_uses_music_folder_name(self) -> None:
        output_dir = default_output_dir()

        self.assertEqual(output_dir.name, "record-transcript-resume")
        self.assertIn("Music", [part for part in output_dir.parts])

    def test_app_data_dir_uses_local_app_data(self) -> None:
        with patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
            self.assertEqual(
                app_data_dir(),
                Path(r"C:\Users\Test\AppData\Local") / "Voice Notes",
            )


if __name__ == "__main__":
    unittest.main()
