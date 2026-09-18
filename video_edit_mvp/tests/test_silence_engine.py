import unittest
from pathlib import Path

from silence_engine import (
    DEFAULT_FFMPEG,
    DEFAULT_FFPROBE,
    DEFAULT_WHISPER_CACHE,
    SilenceEvent,
    SpeechWord,
    calculate_active_range,
    calculate_speech_active_range,
    resolve_ffmpeg,
    resolve_ffprobe,
    sort_take_paths,
)


class RuntimeDependencyTests(unittest.TestCase):
    def test_defaults_are_independent_from_the_original_factory(self):
        for path in (DEFAULT_FFMPEG, DEFAULT_FFPROBE, DEFAULT_WHISPER_CACHE):
            self.assertNotIn("FabricaDeVideos", str(path))

    def test_ffprobe_is_resolved_next_to_the_selected_ffmpeg(self):
        ffmpeg = resolve_ffmpeg()

        self.assertEqual(resolve_ffprobe(ffmpeg), ffmpeg.with_name("ffprobe.exe"))


class SortTakePathsTests(unittest.TestCase):
    def test_sorts_take_files_by_take_number(self):
        files = [
            Path("Take_10_-_later.mp4"),
            Path("Take_2_-_middle.mp4"),
            Path("Take_1_-_first.mp4"),
        ]

        sorted_files = sort_take_paths(files)

        self.assertEqual([p.name for p in sorted_files], [
            "Take_1_-_first.mp4",
            "Take_2_-_middle.mp4",
            "Take_10_-_later.mp4",
        ])

    def test_sorts_numbered_takes_before_other_video_names(self):
        files = [
            Path("Woman_delivering_warning_message_20260913111359.mp4"),
            Path("Take_2_-_Sunday_September_20260913111359.mp4"),
            Path("Mulher_fala_aviso_final_20260913111359.mp4"),
            Path("Take_1_-_Keep_your_20260913111359.mp4"),
        ]

        sorted_files = sort_take_paths(files)

        self.assertEqual([p.name for p in sorted_files], [
            "Take_1_-_Keep_your_20260913111359.mp4",
            "Take_2_-_Sunday_September_20260913111359.mp4",
            "Mulher_fala_aviso_final_20260913111359.mp4",
            "Woman_delivering_warning_message_20260913111359.mp4",
        ])

    def test_falls_back_to_natural_name_sort_when_no_take_number_exists(self):
        files = [
            Path("clip_10.mp4"),
            Path("clip_2.mp4"),
            Path("clip_1.mp4"),
        ]

        sorted_files = sort_take_paths(files)

        self.assertEqual([p.name for p in sorted_files], [
            "clip_1.mp4",
            "clip_2.mp4",
            "clip_10.mp4",
        ])


class ActiveRangeTests(unittest.TestCase):
    def test_trims_leading_and_trailing_silence_with_padding(self):
        events = [
            SilenceEvent("start", 0.0),
            SilenceEvent("end", 0.99),
            SilenceEvent("start", 5.38),
            SilenceEvent("end", 8.0),
        ]

        active = calculate_active_range(
            duration=8.0,
            events=events,
            start_padding=0.15,
            end_padding=0.10,
        )

        self.assertAlmostEqual(active.start, 0.84, places=2)
        self.assertAlmostEqual(active.end, 5.48, places=2)
        self.assertAlmostEqual(active.duration, 4.64, places=2)

    def test_keeps_internal_silence_and_only_trims_edges(self):
        events = [
            SilenceEvent("start", 0.0),
            SilenceEvent("end", 0.5),
            SilenceEvent("start", 2.0),
            SilenceEvent("end", 2.5),
            SilenceEvent("start", 7.2),
            SilenceEvent("end", 8.0),
        ]

        active = calculate_active_range(duration=8.0, events=events)

        self.assertAlmostEqual(active.start, 0.35, places=2)
        self.assertAlmostEqual(active.end, 7.30, places=2)

    def test_does_not_cut_a_mid_take_pause_as_the_end(self):
        events = [
            SilenceEvent("start", 3.0),
            SilenceEvent("end", 3.6),
        ]

        active = calculate_active_range(duration=8.0, events=events)

        self.assertAlmostEqual(active.start, 0.0, places=2)
        self.assertAlmostEqual(active.end, 8.0, places=2)


class SpeechRangeTests(unittest.TestCase):
    def test_uses_first_and_last_word_timestamps_with_padding(self):
        words = [
            SpeechWord("Keep", 1.10, 1.35),
            SpeechWord("watching", 1.45, 2.10),
            SpeechWord("now", 5.20, 5.45),
        ]

        active = calculate_speech_active_range(
            duration=8.0,
            words=words,
            start_padding=0.20,
            end_padding=0.55,
        )

        self.assertAlmostEqual(active.start, 0.90, places=2)
        self.assertAlmostEqual(active.end, 6.00, places=2)
        self.assertAlmostEqual(active.duration, 5.10, places=2)

    def test_ignores_words_outside_clip_bounds(self):
        words = [
            SpeechWord("bad", -2.0, -1.0),
            SpeechWord("real", 0.60, 1.0),
            SpeechWord("end", 7.4, 7.8),
            SpeechWord("bad", 9.0, 9.5),
        ]

        active = calculate_speech_active_range(duration=8.0, words=words)

        self.assertAlmostEqual(active.start, 0.45, places=2)
        self.assertAlmostEqual(active.end, 8.0, places=2)

    def test_returns_none_when_no_words_are_detected(self):
        self.assertIsNone(calculate_speech_active_range(duration=8.0, words=[]))


if __name__ == "__main__":
    unittest.main()
