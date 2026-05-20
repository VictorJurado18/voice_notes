from __future__ import annotations

import unittest
from pathlib import Path

from gravador_audio.paths import default_output_dir


class PathTests(unittest.TestCase):
    def test_default_output_dir_uses_music_folder_name(self) -> None:
        output_dir = default_output_dir()

        self.assertEqual(output_dir.name, "gravador_audio")
        self.assertIn("Music", [part for part in output_dir.parts])


if __name__ == "__main__":
    unittest.main()
