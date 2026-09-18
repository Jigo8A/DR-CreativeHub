from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from artifacts import ArtifactPlan, artifact_is_current
from domain import CopyCard, HubSettings


class ArtifactPlanTests(unittest.TestCase):
    def test_artifact_plan_uses_a_windows_safe_title_and_stable_duplicate_suffix(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            card = CopyCard(id="abcd1234ef", title="Video: 22 / oferta?", text="Copy")

            plan = ArtifactPlan.from_card(card, HubSettings(output_folder=str(output)))

        self.assertEqual(plan.audio_path, output / "audios" / "Video 22 oferta_abcd1234.mp3")
        self.assertEqual(plan.transcript_path, output.parent / ".creative_hub" / "transcricoes" / "Video 22 oferta_abcd1234.json")
        self.assertEqual(plan.video_path, output / "Video 22 oferta_abcd1234.mp4")
        self.assertEqual(plan.job_folder, output.parent / ".creative_hub" / "jobs" / output.name / "Video 22 oferta_abcd1234")

    def test_artifact_plan_keeps_transcript_and_staging_outside_final_batch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch = root / "output" / "lote-001-2026-09-17_1430"
            internal = root / ".creative_hub"
            card = CopyCard(id="copy-1", title="Video 22", text="Copy")

            plan = ArtifactPlan.from_card(
                card,
                HubSettings(output_folder=str(root / "output")),
                output_folder=batch,
                internal_folder=internal,
            )

        self.assertEqual(plan.video_path.parent, batch)
        self.assertEqual(plan.transcript_path.parent, internal / "transcricoes")
        self.assertEqual(plan.job_folder, internal / "jobs" / batch.name / "Video 22_copy-1")

    def test_artifact_plan_sanitizes_a_malformed_persisted_id_suffix(self) -> None:
        card = CopyCard(id="ab/cd?e*zz", title="Oferta", text="Copy")

        plan = ArtifactPlan.from_card(card, HubSettings(output_folder="out"))

        self.assertEqual(plan.audio_path, Path("out") / "audios" / "Oferta_ab_cd_e_.mp3")

    def test_artifact_plan_caps_long_filename_components_without_losing_the_suffix(self) -> None:
        card = CopyCard(id="abcd1234ef", title="A" * 400, text="Copy")

        plan = ArtifactPlan.from_card(card, HubSettings(output_folder="out"))

        self.assertLessEqual(len(plan.audio_path.name), 255)
        self.assertLessEqual(len(plan.transcript_path.name), 255)
        self.assertLessEqual(len(plan.video_path.name), 255)
        self.assertTrue(plan.video_path.name.endswith("_abcd1234.mp4"))

    def test_artifact_plan_caps_non_bmp_titles_by_utf16_units(self) -> None:
        card = CopyCard(id="abcd1234ef", title="\U0001F680" * 400, text="Copy")

        plan = ArtifactPlan.from_card(card, HubSettings(output_folder="out"))

        for filename in (plan.audio_path.name, plan.transcript_path.name, plan.video_path.name):
            self.assertLessEqual(len(filename.encode("utf-16-le")) // 2, 255)
        self.assertTrue(plan.video_path.name.endswith("_abcd1234.mp4"))

    def test_artifact_plan_counts_non_bmp_id_suffix_by_utf16_units(self) -> None:
        emoji_prefix = "\U0001F680" * 8
        card = CopyCard(id=f"{emoji_prefix}extra", title="A" * 400, text="Copy")

        plan = ArtifactPlan.from_card(card, HubSettings(output_folder="out"))

        for filename in (plan.audio_path.name, plan.transcript_path.name, plan.video_path.name):
            self.assertLessEqual(len(filename.encode("utf-16-le")) // 2, 255)
        self.assertTrue(plan.video_path.name.endswith(f"_{emoji_prefix}.mp4"))

    def test_artifact_plan_replaces_an_unpaired_surrogate_in_the_id_suffix(self) -> None:
        card = CopyCard(id="abc\ud800defghi", title="Oferta", text="Copy")

        plan = ArtifactPlan.from_card(card, HubSettings(output_folder="out"))

        self.assertEqual(plan.video_path.name, "Oferta_abc_defg.mp4")
        plan.video_path.name.encode("utf-16-le")

    def test_artifact_plan_uses_card_voice_before_the_default_voice(self) -> None:
        card = CopyCard(id="copy-1", text="Copy", voice_name="card-voice")
        settings = HubSettings(output_folder="out", voice_name="default-voice", voice_provider="provider")

        card_plan = ArtifactPlan.from_card(card, settings)
        default_plan = ArtifactPlan.from_card(replace(card, voice_name=""), settings)

        self.assertNotEqual(card_plan.audio_signature, default_plan.audio_signature)

    def test_audio_edit_changes_only_dependent_signatures(self) -> None:
        card = CopyCard(id="copy-1", text="Copy")
        settings = HubSettings(output_folder="out")

        original = ArtifactPlan.from_card(card, settings)
        changed = ArtifactPlan.from_card(card, replace(settings, keep_silence=0.3))

        self.assertEqual(changed.audio_signature, original.audio_signature)
        self.assertNotEqual(changed.transcript_signature, original.transcript_signature)
        self.assertNotEqual(changed.render_signature, original.render_signature)

    def test_render_setting_changes_only_the_render_signature(self) -> None:
        card = CopyCard(id="copy-1", text="Copy")
        settings = HubSettings(output_folder="out")

        original = ArtifactPlan.from_card(card, settings)
        changed = ArtifactPlan.from_card(card, replace(settings, subtitle_font_size=42))

        self.assertEqual(changed.audio_signature, original.audio_signature)
        self.assertEqual(changed.transcript_signature, original.transcript_signature)
        self.assertNotEqual(changed.render_signature, original.render_signature)

    def test_manual_audio_content_changes_all_dependent_signatures(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_audio = root / "primeiro.wav"
            second_audio = root / "segundo.wav"
            first_audio.write_bytes(b"primeiro audio")
            second_audio.write_bytes(b"segundo audio")
            card = CopyCard(id="copy-1", title="Video", audio_source="manual", audio_path=str(first_audio))
            settings = HubSettings(output_folder=str(root / "output"))

            first = ArtifactPlan.from_card(card, settings)
            card.audio_path = str(second_audio)
            second = ArtifactPlan.from_card(card, settings)

        self.assertNotEqual(first.audio_signature, second.audio_signature)
        self.assertNotEqual(first.transcript_signature, second.transcript_signature)
        self.assertNotEqual(first.render_signature, second.render_signature)

    def test_artifact_is_not_current_when_the_file_was_deleted(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "audio.mp3"

            self.assertFalse(artifact_is_current(str(path), "signature", "signature"))

    def test_artifact_is_current_only_for_an_existing_file_with_the_expected_signature(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "audio.mp3"
            path.write_bytes(b"audio")

            self.assertTrue(artifact_is_current(str(path), "signature", "signature"))
            self.assertFalse(artifact_is_current(str(path), "other", "signature"))
