from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DistributionFileTests(unittest.TestCase):
    def test_gitignore_excludes_state_and_generated_content(self) -> None:
        content = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for rule in (
            "creative_hub/data/state.json",
            "**/node_modules/",
            "*.log",
            "__pycache__/",
            "*.mp4",
            ".venv/",
        ):
            self.assertIn(rule, content)

    def test_root_requirements_include_video_engine_dependency(self) -> None:
        content = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("faster-whisper==1.2.1", content)

    def test_distribution_does_not_include_agent_session_metadata(self) -> None:
        session_root = ROOT / "creative_hub" / ".superpowers"
        self.assertEqual([path for path in session_root.rglob("*") if path.is_file()], [])
