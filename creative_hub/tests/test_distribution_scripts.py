from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DistributionScriptTests(unittest.TestCase):
    def test_distribution_scripts_exist_without_personal_paths(self) -> None:
        for name in ("diagnostico.ps1", "install.ps1", "abrir-hub.ps1"):
            content = (ROOT / "scripts" / name).read_text(encoding="utf-8")

            self.assertNotIn("FabricaDeVideos", content)
            self.assertNotIn("PCGamerInfor", content)

    def test_root_readme_documents_installation_flow(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        for text in ("install.ps1", "abrir-hub.ps1", "FFmpeg", "OpenSpeaker", "AssemblyAI"):
            self.assertIn(text, content)

    def test_diagnostic_returns_a_plain_boolean_when_sourced(self) -> None:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "& { . .\\scripts\\diagnostico.ps1; $ready = Test-CreativeHubPrerequisites; if ($ready -is [bool]) { exit 0 }; exit 1 }",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
