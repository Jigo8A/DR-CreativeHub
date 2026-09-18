import unittest
from pathlib import Path

from silence_engine import ClipPlan, SpeechWord
from subtitles import DEFAULT_FONT_DIR, HeadlineSettings, SubtitleSettings, build_ass_text, group_words, timeline_words_from_plans


class SubtitleGroupingTests(unittest.TestCase):
    def test_default_font_directory_is_packaged_with_creative_hub(self):
        self.assertEqual(DEFAULT_FONT_DIR.name, "fonts")
        self.assertEqual(DEFAULT_FONT_DIR.parent.name, "assets")
        self.assertNotIn("FabricaDeVideos", str(DEFAULT_FONT_DIR))

    def test_skips_the_ass_headline_text_when_a_raster_overlay_is_supplied(self):
        headline = HeadlineSettings(enabled=True, text="OFERTA \U0001f680", emoji_overlay_path=Path("headline.png"))

        ass_text = build_ass_text([], SubtitleSettings(), headline=headline)

        self.assertNotIn("Style: Headline,", ass_text)
        self.assertNotIn("OFERTA", ass_text)

    def test_groups_three_words_per_line(self):
        words = [
            SpeechWord("one", 0.0, 0.2),
            SpeechWord("two", 0.3, 0.5),
            SpeechWord("three", 0.6, 0.8),
            SpeechWord("four", 1.0, 1.2),
        ]

        groups = group_words(words, max_words=3)

        self.assertEqual([[word.text for word in group.words] for group in groups], [["one", "two", "three"], ["four"]])
        self.assertEqual(groups[0].start, 0.0)
        self.assertEqual(groups[0].end, 0.8)

    def test_keeps_very_long_words_from_overflowing_group(self):
        words = [
            SpeechWord("supercalifragilistic", 0.0, 0.5),
            SpeechWord("short", 0.6, 0.8),
            SpeechWord("words", 0.9, 1.1),
        ]

        groups = group_words(words, max_words=3)

        self.assertEqual([[word.text for word in group.words] for group in groups], [["supercalifragilistic"], ["short", "words"]])


class SubtitleTimelineTests(unittest.TestCase):
    def test_maps_words_from_original_takes_to_final_video_time(self):
        plans = [
            ClipPlan(
                path="take1.mp4",
                name="take1.mp4",
                original_duration=6.0,
                start=1.0,
                end=4.0,
                kept_duration=3.0,
                removed_duration=3.0,
                words=[
                    SpeechWord("skip", 0.4, 0.8),
                    SpeechWord("hello", 1.2, 1.5),
                    SpeechWord("now", 3.7, 4.4),
                ],
            ),
            ClipPlan(
                path="take2.mp4",
                name="take2.mp4",
                original_duration=3.0,
                start=0.5,
                end=2.5,
                kept_duration=2.0,
                removed_duration=1.0,
                words=[SpeechWord("again", 0.6, 1.0)],
            ),
        ]

        words = timeline_words_from_plans(plans)

        self.assertEqual([word.text for word in words], ["hello", "now", "again"])
        self.assertEqual([(word.start, word.end) for word in words], [(0.2, 0.5), (2.7, 3.0), (3.1, 3.5)])


class SubtitleAssTests(unittest.TestCase):
    def test_uses_selected_subtitle_font_and_outline_thickness(self):
        settings = SubtitleSettings(
            mode="normal",
            font_name="TikTok Sans 24pt",
            outline_size=5,
        )

        ass_text = build_ass_text([SpeechWord("teste", 0.0, 0.8)], settings)

        self.assertIn("Style: Default,TikTok Sans 24pt,24", ass_text)
        self.assertIn(",1,5,0,5,40,40,30,1", ass_text)

    def test_uses_selected_headline_font_and_outline_thickness(self):
        headline = HeadlineSettings(
            enabled=True,
            text="OFERTA",
            font_name="Roboto",
            outline_size=4,
        )

        ass_text = build_ass_text([], SubtitleSettings(mode="none"), headline=headline)

        self.assertIn("Style: Headline,Roboto,48", ass_text)
        self.assertIn(",1,4,0,5,0,0,0,1", ass_text)

    def test_adds_fixed_multiline_headline_with_rounded_solid_background(self):
        headline = HeadlineSettings(
            enabled=True,
            text="OFERTA\nSOMENTE HOJE",
            duration=3.0,
            x_position=0.5,
            y_position=0.2,
            font_size=48,
            background_width=560,
            background_height=150,
            corner_radius=24,
            background_color=(18, 24, 15),
        )

        ass_text = build_ass_text([], SubtitleSettings(mode="none"), headline=headline, width=720, height=1280)

        self.assertIn("Style: Headline,Uninsta Heavy,48", ass_text)
        self.assertIn("Dialogue: 5,0:00:00.00,0:00:03.00,HeadlineBackground", ass_text)
        self.assertIn(r"{\an5\pos(360,256)}OFERTA\NSOMENTE HOJE", ass_text)
        self.assertIn(r"{\an7\pos(80,181)\p1", ass_text)

    def test_builds_normal_ass_subtitle_at_selected_vertical_position(self):
        settings = SubtitleSettings(mode="normal", y_position=0.66, font_size=24, max_words_per_line=3)
        words = [
            SpeechWord("keep", 0.2, 0.5),
            SpeechWord("going", 0.6, 1.0),
            SpeechWord("now", 1.1, 1.5),
        ]

        ass_text = build_ass_text(words, settings, width=720, height=1280)

        self.assertIn("PlayResX: 720", ass_text)
        self.assertIn("PlayResY: 1280", ass_text)
        self.assertIn(r"{\an5\pos(360,845)}KEEP GOING NOW", ass_text)
        self.assertNotIn(r"\c&H0000EFFF&", ass_text)

    def test_builds_subtitle_at_selected_horizontal_and_vertical_position(self):
        settings = SubtitleSettings(mode="normal", x_position=0.42, y_position=0.74, font_size=24)
        words = [SpeechWord("dragged", 0.2, 0.8)]

        ass_text = build_ass_text(words, settings, width=720, height=1280)

        self.assertIn(r"{\an5\pos(302,947)}DRAGGED", ass_text)

    def test_builds_highlight_ass_subtitle_with_active_word_color(self):
        settings = SubtitleSettings(mode="highlight", y_position=0.7, font_size=24, max_words_per_line=3)
        words = [
            SpeechWord("keep", 0.2, 0.5),
            SpeechWord("going", 0.6, 1.0),
        ]

        ass_text = build_ass_text(words, settings, width=720, height=1280)

        self.assertIn(r"{\an5\pos(360,896)}{\c&H0000EFFF&}KEEP{\c&H00FFFFFF&} GOING", ass_text)
        self.assertIn(r"{\an5\pos(360,896)}KEEP {\c&H0000EFFF&}GOING{\c&H00FFFFFF&}", ass_text)


if __name__ == "__main__":
    unittest.main()
