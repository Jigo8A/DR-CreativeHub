from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from emoji_assets import EmojiSpriteCache, HeadlineOverlayCache, headline_content_html, headline_requires_raster_overlay, prepare_headline_emoji_overlay


ROOT = Path(__file__).resolve().parent.parent


class EmojiAssetTests(unittest.TestCase):
    def test_uses_the_overlay_path_only_when_a_headline_contains_emoji(self) -> None:
        self.assertTrue(headline_requires_raster_overlay("Oferta \U0001f680"))
        self.assertFalse(headline_requires_raster_overlay("Oferta sem emoji"))

    def test_skips_headline_overlay_generation_when_the_text_has_no_emoji(self) -> None:
        with TemporaryDirectory() as temporary:
            result = prepare_headline_emoji_overlay(
                {"text": "Oferta sem emoji", "font_size": 48},
                Path(temporary),
                Path(temporary) / "AppleColorEmoji-Windows.ttf",
            )

        self.assertIsNone(result)

    def test_extracts_complete_emoji_clusters_without_touching_headline_text(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from emoji_assets import extract_emoji_clusters; print(json.dumps(extract_emoji_clusters('Oferta \U0001f680 com amor \u2764\ufe0f')))",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '["\\ud83d\\ude80", "\\u2764\\ufe0f"]')

    def test_wraps_each_emoji_cluster_in_the_apple_font_marker(self) -> None:
        self.assertEqual(
            headline_content_html("Oferta 🚀\ncom amor ❤️"),
            'Oferta <span class="apple-emoji">🚀</span><br>com amor <span class="apple-emoji">❤️</span>',
        )

    def test_reuses_a_cached_sprite_for_the_same_emoji_and_style(self) -> None:
        calls: list[tuple[str, int, int]] = []

        def rasterize(emoji: str, size: int, outline: int, destination: Path) -> None:
            calls.append((emoji, size, outline))
            destination.write_bytes(b"png")

        with TemporaryDirectory() as temporary:
            cache = EmojiSpriteCache(Path(temporary), rasterize)

            first = cache.sprite_for("\U0001f680", 48, 3)
            second = cache.sprite_for("\U0001f680", 48, 3)

        self.assertEqual(first, second)
        self.assertEqual(calls, [("\U0001f680", 48, 3)])

    def test_reuses_the_complete_headline_overlay_until_its_visual_settings_change(self) -> None:
        calls: list[dict[str, object]] = []

        def render(settings: dict[str, object], destination: Path) -> None:
            calls.append(settings)
            destination.write_bytes(b"png")

        with TemporaryDirectory() as temporary:
            cache = HeadlineOverlayCache(Path(temporary), render)
            settings = {"text": "Oferta \U0001f680", "size": 48, "color": "#FFFFFF"}

            first = cache.overlay_for(settings)
            second = cache.overlay_for(dict(settings))
            changed = cache.overlay_for({**settings, "size": 54})

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(calls, [settings, {**settings, "size": 54}])
