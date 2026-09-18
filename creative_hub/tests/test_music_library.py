import random
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class MusicLibraryTests(unittest.TestCase):
    def test_scans_only_direct_category_folders_and_supported_audio(self) -> None:
        from music_library import scan_music_library

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            category = root / "infantil"
            category.mkdir()
            (category / "ukulele.mp3").write_bytes(b"audio")
            (category / "ukulele-loop.mp4").write_bytes(b"container")
            (category / "nota.txt").write_text("ignore", encoding="utf-8")
            (category / "aninhada").mkdir()
            (category / "aninhada" / "outra.mp3").write_bytes(b"audio")

            library = scan_music_library(root)

        self.assertEqual([track.path.name for track in library["infantil"]], ["ukulele-loop.mp4", "ukulele.mp3"])

    def test_category_resolution_returns_a_track_and_uses_the_render_nonce(self) -> None:
        from music_library import MusicTrack, resolve_background_music

        library = {
            "infantil": [
                MusicTrack("infantil", Path("a.mp3")),
                MusicTrack("infantil", Path("b.mp3")),
            ]
        }

        selection = resolve_background_music("category", "", "infantil", library, random.Random(7), nonce="render-1")

        self.assertEqual(selection.mode, "category")
        self.assertIn(selection.path.name, {"a.mp3", "b.mp3"})
        self.assertEqual(selection.nonce, "render-1")

    def test_invalid_track_and_empty_category_explain_the_problem(self) -> None:
        from music_library import resolve_background_music

        with self.assertRaisesRegex(ValueError, "Categoria de musica sem faixas"):
            resolve_background_music("category", "", "vazia", {}, random.Random())

        with self.assertRaisesRegex(ValueError, "faixa de musica"):
            resolve_background_music("track", "C:/ausente.mp3", "", {}, random.Random())
