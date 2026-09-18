import json
import random
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from silence_engine import SpeechWord
from subtitles import HeadlineSettings, SubtitleSettings


class FakeDetector:
    def __init__(self):
        self.calls = []

    def detect_words(self, audio_path):
        self.calls.append(Path(audio_path).name)
        return [
            SpeechWord("intro", 0.0, 0.3),
            SpeechWord("dinamica", 1.2, 1.6),
            SpeechWord("dinâmicas", 2.0, 2.5),
        ]


class CreativeEngineTests(unittest.TestCase):
    def test_batch_forwards_the_shared_headline_to_each_render_job(self):
        from creative_engine import process_creative_batch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio_folder = root / "audios"
            takes_folder = root / "takes"
            output_folder = root / "output"
            audio_folder.mkdir()
            takes_folder.mkdir()
            (audio_folder / "copy.mp3").write_bytes(b"audio")
            (takes_folder / "take.mp4").write_bytes(b"take")
            headline = HeadlineSettings(enabled=True, text="LINHA UM\nLINHA DOIS", duration=2.5)
            received = []

            def fake_renderer(job):
                received.append(job.headline_settings)
                Path(job.output_path).write_bytes(b"creative")
                return Path(job.output_path)

            process_creative_batch(
                audio_folder=audio_folder,
                takes_folder=takes_folder,
                output_folder=output_folder,
                broll_path=None,
                keyword_variants=[],
                segment_duration=3.0,
                subtitle_settings=SubtitleSettings(mode="none"),
                headline_settings=headline,
                speech_detector=FakeDetector(),
                duration_lookup=lambda path: 3.0 if path.suffix.lower() == ".mp3" else 10.0,
                render_job_func=fake_renderer,
            )

        self.assertEqual(received, [headline])

    def test_finds_first_keyword_variant_without_requiring_accents(self):
        from creative_engine import find_keyword_trigger

        words = [
            SpeechWord("Começo", 0.2, 0.5),
            SpeechWord("dinamica,", 1.4, 1.8),
            SpeechWord("dinâmicas", 2.1, 2.6),
        ]

        trigger = find_keyword_trigger(words, ["dinâmica", "dinamicas"])

        self.assertIsNotNone(trigger)
        self.assertEqual(trigger.word, "dinamica,")
        self.assertEqual(trigger.start, 1.4)

    def test_visual_plan_covers_audio_and_uses_different_first_and_last_sources(self):
        from creative_engine import build_visual_plan

        takes = [Path("take_a.mp4"), Path("take_b.mp4"), Path("take_c.mp4")]
        durations = {path.name: 12.0 for path in takes}

        plan = build_visual_plan(
            takes=takes,
            target_duration=8.2,
            segment_duration=3.0,
            duration_lookup=lambda path: durations[path.name],
            rng=random.Random(7),
            used_ranges=set(),
        )

        self.assertEqual(len(plan), 3)
        self.assertAlmostEqual(sum(item.output_duration for item in plan), 8.2, places=2)
        self.assertNotEqual(plan[0].source_path, plan[-1].source_path)
        self.assertEqual(len({(item.source_path, item.source_start) for item in plan}), 3)

    def test_visual_plan_applies_background_speed_to_source_ranges(self):
        from creative_engine import build_visual_plan

        takes = [Path("take_a.mp4"), Path("take_b.mp4")]

        plan = build_visual_plan(
            takes=takes,
            target_duration=4.0,
            segment_duration=2.0,
            duration_lookup=lambda path: 5.0,
            rng=random.Random(4),
            used_ranges=set(),
            background_speed=1.2,
        )

        self.assertEqual([item.playback_speed for item in plan], [1.2, 1.2])
        self.assertAlmostEqual(sum(item.output_duration for item in plan), 4.0, places=2)
        for item in plan:
            self.assertLessEqual(item.source_start + (item.output_duration * item.playback_speed), 5.01)

    def test_visual_plan_discards_ranges_that_cannot_be_decoded(self):
        from creative_engine import build_visual_plan

        rejected = []

        def validator(segment):
            rejected.append(Path(segment.source_path).name)
            return Path(segment.source_path).name != "corrupted.mp4"

        plan = build_visual_plan(
            takes=[Path("corrupted.mp4"), Path("healthy.mp4")],
            target_duration=6.0,
            segment_duration=3.0,
            duration_lookup=lambda _: 12.0,
            rng=random.Random(1),
            used_ranges=set(),
            segment_validator=validator,
        )

        self.assertIn("corrupted.mp4", rejected)
        self.assertTrue(all(Path(item.source_path).name == "healthy.mp4" for item in plan))

    def test_audio_keep_segments_trim_edges_and_compact_internal_silence(self):
        from creative_engine import AudioEditSettings, calculate_audio_keep_segments

        settings = AudioEditSettings(
            trim_edges=True,
            cut_internal_silence=True,
            min_silence_duration=0.4,
            keep_silence=0.2,
        )

        segments = calculate_audio_keep_segments(
            duration=10.0,
            silences=[(0.0, 1.0), (3.0, 4.2), (8.8, 10.0)],
            settings=settings,
        )

        self.assertEqual([(round(item.start, 2), round(item.end, 2)) for item in segments], [(1.0, 3.1), (4.1, 8.8)])

    def test_batch_test_mode_processes_only_first_audio_and_writes_report(self):
        from creative_engine import process_creative_batch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio_folder = root / "audios"
            takes_folder = root / "takes"
            output_folder = root / "output"
            audio_folder.mkdir()
            takes_folder.mkdir()
            (audio_folder / "copy_2.mp3").write_bytes(b"audio-two")
            (audio_folder / "copy_1.mp3").write_bytes(b"audio-one")
            (takes_folder / "take_1.mp4").write_bytes(b"take-one")
            (takes_folder / "take_2.mp4").write_bytes(b"take-two")
            detector = FakeDetector()
            rendered = []

            def duration_lookup(path):
                return 4.0 if path.suffix.lower() == ".mp3" else 12.0

            def fake_renderer(job):
                rendered.append(job.audio_path.name)
                Path(job.output_path).write_bytes(b"creative")
                if job.subtitle_path:
                    Path(job.subtitle_path).write_text("subs", encoding="utf-8")
                return Path(job.output_path)

            result = process_creative_batch(
                audio_folder=audio_folder,
                takes_folder=takes_folder,
                output_folder=output_folder,
                broll_path=None,
                keyword_variants=["dinâmica"],
                segment_duration=3.0,
                subtitle_settings=SubtitleSettings(mode="normal"),
                speech_detector=detector,
                duration_lookup=duration_lookup,
                render_job_func=fake_renderer,
                rng=random.Random(3),
                limit=1,
            )

            self.assertEqual(rendered, ["copy_1.mp3"])
            self.assertEqual(detector.calls, ["copy_1.mp3"])
            self.assertEqual(result.total, 1)
            self.assertEqual(result.completed, 1)
            self.assertEqual(result.items[0].trigger_word, "dinamica")
            self.assertTrue(Path(result.items[0].output_path).exists())
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
            self.assertEqual(report["kind"], "creative_batch")
            self.assertTrue(report["test_only"])

    def test_batch_uses_cached_words_and_requested_output_paths(self):
        from creative_engine import process_creative_batch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio_folder = root / "audios"
            takes_folder = root / "takes"
            output_folder = root / "output"
            audio_folder.mkdir()
            takes_folder.mkdir()
            audio = audio_folder / "copy.mp3"
            audio.write_bytes(b"audio")
            (takes_folder / "take.mp4").write_bytes(b"take")
            requested_video = output_folder / "Video 22.mp4"
            requested_ass = output_folder / "Video 22.ass"
            rendered = []

            def fake_renderer(job):
                rendered.append(job)
                Path(job.output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(job.output_path).write_bytes(b"creative")
                return Path(job.output_path)

            result = process_creative_batch(
                audio_folder=audio_folder,
                takes_folder=takes_folder,
                output_folder=output_folder,
                broll_path=None,
                keyword_variants=[],
                segment_duration=3.0,
                subtitle_settings=SubtitleSettings(mode="none"),
                duration_lookup=lambda path: 3.0 if path.suffix.lower() == ".mp3" else 10.0,
                render_job_func=fake_renderer,
                word_loader=lambda _: [SpeechWord("ola", 0.0, 0.2)],
                output_paths_for_audio=lambda _: (requested_video, requested_ass),
            )

        self.assertEqual(result.items[0].output_path, str(requested_video))
        self.assertEqual(result.items[0].subtitle_path, None)
        self.assertEqual(rendered[0].words, [SpeechWord("ola", 0.0, 0.2)])

    def test_batch_report_records_timing_for_each_pipeline_stage(self):
        from creative_engine import process_creative_batch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio_folder = root / "audios"
            takes_folder = root / "takes"
            output_folder = root / "output"
            audio_folder.mkdir()
            takes_folder.mkdir()
            (audio_folder / "copy.mp3").write_bytes(b"audio")
            (takes_folder / "take.mp4").write_bytes(b"take")

            def fake_renderer(job):
                Path(job.output_path).write_bytes(b"creative")
                return Path(job.output_path)

            result = process_creative_batch(
                audio_folder=audio_folder,
                takes_folder=takes_folder,
                output_folder=output_folder,
                broll_path=None,
                keyword_variants=[],
                segment_duration=3.0,
                subtitle_settings=SubtitleSettings(mode="none"),
                duration_lookup=lambda path: 3.0 if path.suffix.lower() == ".mp3" else 10.0,
                render_job_func=fake_renderer,
                word_loader=lambda _: [SpeechWord("ola", 0.0, 0.2)],
            )

        timings = result.items[0].timings
        self.assertTrue({"audio_prepare", "audio_probe", "transcription", "visual_plan", "render", "total"}.issubset(timings))
        self.assertTrue(all(value >= 0 for value in timings.values()))

    def test_background_music_loudness_is_cached_until_the_track_changes(self):
        from creative_engine import measure_cached_background_music_loudness

        with tempfile.TemporaryDirectory() as folder:
            music = Path(folder) / "music.mp3"
            music.write_bytes(b"first version")
            with patch("creative_engine.measure_integrated_loudness", return_value=-18.5) as measure:
                first, first_hit = measure_cached_background_music_loudness(music, Path("ffmpeg"))
                second, second_hit = measure_cached_background_music_loudness(music, Path("ffmpeg"))
                music.write_bytes(b"second version with another size")
                third, third_hit = measure_cached_background_music_loudness(music, Path("ffmpeg"))

        self.assertEqual((first, second, third), (-18.5, -18.5, -18.5))
        self.assertEqual((first_hit, second_hit, third_hit), (False, True, False))
        self.assertEqual(measure.call_count, 2)

    def test_concurrent_music_loudness_requests_share_the_first_measurement(self):
        from creative_engine import measure_cached_background_music_loudness

        with tempfile.TemporaryDirectory() as folder:
            music = Path(folder) / "music.mp3"
            music.write_bytes(b"track")
            with patch("creative_engine.measure_integrated_loudness", side_effect=lambda *_: (time.sleep(0.05), -17.0)[1]) as measure:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _: measure_cached_background_music_loudness(music, Path("ffmpeg")), range(2)))

        self.assertEqual(measure.call_count, 1)
        self.assertEqual(sorted(results), [(-17.0, False), (-17.0, True)])

    def test_batch_reuses_prepared_audio_and_words_without_transcribing_again(self):
        from creative_engine import PreparedCreativeAudio, process_creative_batch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio_folder = root / "audios"
            takes_folder = root / "takes"
            output_folder = root / "output"
            audio_folder.mkdir()
            takes_folder.mkdir()
            audio = audio_folder / "copy.mp3"
            audio.write_bytes(b"audio")
            (takes_folder / "take.mp4").write_bytes(b"take")
            prepared = PreparedCreativeAudio(
                source_path=audio,
                effective_audio_path=audio,
                audio_duration=3.0,
                words=[SpeechWord("ola", 0.0, 0.2)],
                timings={"audio_prepare": 0.1, "audio_probe": 0.1, "transcription": 0.1},
            )
            detector = FakeDetector()

            def fake_renderer(job):
                Path(job.output_path).write_bytes(b"creative")
                return Path(job.output_path)

            result = process_creative_batch(
                audio_folder=audio_folder,
                takes_folder=takes_folder,
                output_folder=output_folder,
                broll_path=None,
                keyword_variants=[],
                segment_duration=3.0,
                subtitle_settings=SubtitleSettings(mode="none"),
                speech_detector=detector,
                duration_lookup=lambda path: 3.0 if path.suffix.lower() == ".mp3" else 10.0,
                render_job_func=fake_renderer,
                prepared_audios={str(audio.resolve()): prepared},
            )

        self.assertEqual(detector.calls, [])
        self.assertEqual(result.items[0].words_detected, 1)
        self.assertEqual(result.items[0].timings["transcription"], 0.1)

    def test_transcription_preview_uses_first_audio_in_natural_order(self):
        from creative_engine import transcribe_audio_preview

        with tempfile.TemporaryDirectory() as folder:
            audio_folder = Path(folder)
            (audio_folder / "copy_10.mp3").write_bytes(b"audio-ten")
            (audio_folder / "copy_2.mp3").write_bytes(b"audio-two")
            detector = FakeDetector()

            preview = transcribe_audio_preview(audio_folder, detector)

            self.assertEqual(preview.audio_path, str(audio_folder / "copy_2.mp3"))
            self.assertEqual(preview.text, "intro dinamica dinâmicas")
            self.assertEqual(preview.words_count, 3)


if __name__ == "__main__":
    unittest.main()
