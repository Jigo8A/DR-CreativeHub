import json
import tempfile
import unittest
from pathlib import Path

from silence_engine import SpeechWord


class FakeDetector:
    def __init__(self):
        self.calls = []

    def detect_words(self, video_path):
        self.calls.append(Path(video_path).name)
        return [
            SpeechWord("hello", 0.10, 0.30),
            SpeechWord("world", 0.34, 0.70),
        ]


class CaptionBatchTests(unittest.TestCase):
    def test_output_paths_keep_original_video_untouched(self):
        from caption_batch import caption_output_paths

        with tempfile.TemporaryDirectory() as folder:
            output_folder = Path(folder) / "output"

            paths = caption_output_paths(Path("Take 1.mp4"), output_folder)

            self.assertEqual(paths.output_path, output_folder / "Take 1_legendado.mp4")
            self.assertEqual(paths.subtitle_path, output_folder / "Take 1_legendado.ass")

    def test_captions_each_video_with_one_shared_detector_and_writes_report(self):
        from caption_batch import caption_folder
        from subtitles import SubtitleSettings

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_folder = root / "input"
            output_folder = root / "output"
            input_folder.mkdir()
            first = input_folder / "Take_2.mp4"
            second = input_folder / "Take_1.mp4"
            first.write_bytes(b"original-one")
            second.write_bytes(b"original-two")
            detector = FakeDetector()
            progress = []

            def fake_burn(input_path, subtitle_path, output_path):
                output_path.write_bytes(input_path.read_bytes() + b"-captioned")
                return output_path

            result = caption_folder(
                input_folder=input_folder,
                output_folder=output_folder,
                subtitle_settings=SubtitleSettings(mode="normal"),
                speech_detector=detector,
                burn_subtitles_func=fake_burn,
                progress_callback=lambda done, total, name: progress.append((done, total, name)),
            )

            self.assertEqual(detector.calls, ["Take_1.mp4", "Take_2.mp4"])
            self.assertEqual(result.completed, 2)
            self.assertEqual(result.failed, 0)
            self.assertEqual(progress, [(1, 2, "Take_1.mp4"), (2, 2, "Take_2.mp4")])
            self.assertEqual(second.read_bytes(), b"original-two")
            self.assertTrue((output_folder / "Take_1_legendado.mp4").exists())
            self.assertTrue((output_folder / "Take_1_legendado.ass").exists())
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
            self.assertEqual(report["kind"], "caption_batch")
            self.assertEqual(report["total"], 2)

    def test_keeps_processing_after_one_video_fails(self):
        from caption_batch import caption_folder
        from subtitles import SubtitleSettings

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_folder = root / "input"
            output_folder = root / "output"
            input_folder.mkdir()
            (input_folder / "Take_1.mp4").write_bytes(b"bad")
            (input_folder / "Take_2.mp4").write_bytes(b"good")
            detector = FakeDetector()

            def fake_burn(input_path, subtitle_path, output_path):
                if input_path.name == "Take_1.mp4":
                    raise RuntimeError("burn failed")
                output_path.write_bytes(b"captioned")
                return output_path

            result = caption_folder(
                input_folder=input_folder,
                output_folder=output_folder,
                subtitle_settings=SubtitleSettings(mode="highlight"),
                speech_detector=detector,
                burn_subtitles_func=fake_burn,
            )

            statuses = {Path(item.source_path).name: item.status for item in result.items}
            self.assertEqual(statuses["Take_1.mp4"], "failed")
            self.assertEqual(statuses["Take_2.mp4"], "completed")
            self.assertEqual(result.completed, 1)
            self.assertEqual(result.failed, 1)


if __name__ == "__main__":
    unittest.main()
