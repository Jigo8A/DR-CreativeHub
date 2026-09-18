from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from artifacts import ArtifactPlan
from domain import CopyCard, Offer, default_state
from video_bridge import _headline_settings, _subtitle_settings, render_card, render_cards, settings_for_card, settings_for_offer
from voice_provider import UnavailableVoiceProvider, VoiceProviderUnavailable


@dataclass
class FakeBatchItem:
    audio_path: str
    output_path: str
    subtitle_path: str
    status: str = "completed"
    error: str | None = None


@dataclass
class FakeBatchResult:
    items: list[FakeBatchItem]


class VideoBridgeTests(unittest.TestCase):
    def test_headline_settings_do_not_activate_the_experimental_emoji_overlay(self) -> None:
        settings = default_state().settings
        settings.headline_enabled = True
        settings.headline_text = "OFERTA \U0001f680"

        headline = _headline_settings(settings)

        self.assertIsNone(headline.emoji_overlay_path)

    def test_settings_for_card_prefers_the_card_individual_headline(self) -> None:
        settings = default_state().settings
        settings.headline_enabled = True
        settings.headline_text = "GLOBAL"
        card = CopyCard(id="copy-a", headline={"headline_text": "INDIVIDUAL", "headline_duration": 2.5, "headline_font_size": 54})

        effective = settings_for_card(settings, card)

        self.assertTrue(effective.headline_enabled)
        self.assertEqual(effective.headline_text, "INDIVIDUAL")
        self.assertEqual(effective.headline_duration, 2.5)
        self.assertEqual(effective.headline_font_size, 54)

    def test_settings_for_card_disables_global_headline_without_a_saved_link(self) -> None:
        settings = default_state().settings
        settings.headline_enabled = True
        settings.headline_text = "GLOBAL"

        effective = settings_for_card(settings, CopyCard(id="copy-a"))

        self.assertFalse(effective.headline_enabled)
        self.assertEqual(effective.headline_text, "")

    def test_settings_for_offer_overrides_only_media_paths(self) -> None:
        settings = default_state().settings
        settings.subtitle_font_size = 34
        offer = Offer(
            id="kids",
            name="Kids",
            slug="kids",
            takes_folder="C:/kids/takes",
            broll_path="C:/kids/broll.mp4",
            api_audio_folder="C:/kids/audios-api",
            output_folder="C:/kids/output",
        )

        resolved = settings_for_offer(settings, offer)

        self.assertEqual(resolved.takes_folder, "C:/kids/takes")
        self.assertEqual(resolved.broll_path, "C:/kids/broll.mp4")
        self.assertEqual(resolved.output_folder, "C:/kids/output")
        self.assertEqual(resolved.manual_audio_folder, "C:/kids/audios-api")
        self.assertEqual(resolved.subtitle_font_size, 34)

    def test_subtitle_highlight_color_is_forwarded_to_the_render_engine(self) -> None:
        settings = default_state().settings
        settings.subtitle_highlight_color = "#FF00AA"

        subtitle = _subtitle_settings(settings)

        self.assertEqual(subtitle.highlight_color, (255, 0, 170))

    def test_render_cards_stages_selected_audio_and_maps_output(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.wav"
            audio.write_bytes(b"audio")
            card = CopyCard(id="copy-a", text="Copy", audio_source="manual", audio_path=str(audio), status="audio_ready")
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(root / "takes")
            Path(settings.takes_folder).mkdir()
            captured: dict = {}

            def fake_process(**kwargs):
                captured.update(kwargs)
                staged_audio = next(Path(kwargs["audio_folder"]).glob("*.wav"))
                return FakeBatchResult(
                    items=[FakeBatchItem(str(staged_audio), str(root / "output" / "creative.mp4"), str(root / "output" / "creative.ass"))]
                )

            results = render_cards([card], settings, test_only=True, process_func=fake_process)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].card_id, "copy-a")
            self.assertEqual(card.output_path, str(root / "output" / "creative.mp4"))
            self.assertTrue(Path(captured["audio_folder"]).exists())
            self.assertEqual(captured["limit"], 1)

    def test_render_card_reuses_matching_transcript_and_writes_named_video(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.mp3"
            takes = root / "takes"
            audio.write_bytes(b"audio")
            takes.mkdir()
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            card = CopyCard(id="copy-a", title="Video 22", text="Copy", audio_path=str(audio), status="audio_ready")
            plan = ArtifactPlan.from_card(card, settings)
            plan.transcript_path.parent.mkdir(parents=True)
            plan.transcript_path.write_text(
                json.dumps({"signature": plan.transcript_signature, "words": [{"text": "ola", "start": 0.0, "end": 0.2}]}),
                encoding="utf-8",
            )
            captured = {}

            def fake_process(**kwargs):
                staged_audio = next(Path(kwargs["audio_folder"]).glob("*.mp3"))
                captured["words"] = kwargs["word_loader"](staged_audio)
                captured["paths"] = kwargs["output_paths_for_audio"](staged_audio)
                captured["paths"][0].parent.mkdir(parents=True, exist_ok=True)
                captured["paths"][0].write_bytes(b"video")
                return FakeBatchResult(
                    items=[FakeBatchItem(str(staged_audio), str(captured["paths"][0]), str(captured["paths"][1]))]
                )

            result = render_card(card, settings, plan, test_only=False, process_func=fake_process)

        self.assertEqual(result.output_path, str(plan.video_path))
        self.assertEqual(captured["paths"], (plan.job_folder / plan.video_path.name, plan.job_folder / plan.video_path.with_suffix(".ass").name))
        self.assertEqual(captured["words"][0].text, "ola")

    def test_render_card_stages_ass_file_in_its_internal_job_folder(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.mp3"
            takes = root / "takes"
            audio.write_bytes(b"audio")
            takes.mkdir()
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            card = CopyCard(id="copy-a", title="Video 22", text="Copy", audio_path=str(audio))
            plan = ArtifactPlan.from_card(
                card,
                settings,
                output_folder=root / "output" / "lote-001",
                internal_folder=root / ".creative_hub",
            )
            captured = {}

            def fake_process(**kwargs):
                staged_audio = next(Path(kwargs["audio_folder"]).glob("*.mp3"))
                captured["output_folder"] = kwargs["output_folder"]
                captured["paths"] = kwargs["output_paths_for_audio"](staged_audio)
                captured["paths"][0].parent.mkdir(parents=True, exist_ok=True)
                captured["paths"][0].write_bytes(b"video")
                return FakeBatchResult(items=[FakeBatchItem(str(staged_audio), str(captured["paths"][0]), str(captured["paths"][1]))])

            result = render_card(card, settings, plan, test_only=False, process_func=fake_process)

            self.assertEqual(captured["output_folder"], plan.job_folder)
            self.assertTrue(captured["paths"][0].is_relative_to(plan.job_folder))
            self.assertTrue(captured["paths"][1].is_relative_to(plan.job_folder))
            self.assertEqual(result.output_path, str(plan.video_path))
            self.assertTrue(plan.video_path.is_file())

    def test_unavailable_voice_provider_explains_missing_connector(self) -> None:
        with self.assertRaisesRegex(VoiceProviderUnavailable, "API de voz"):
            UnavailableVoiceProvider().generate(CopyCard(id="copy-a", text="Oi"), default_state().settings)

    def test_render_cards_requires_existing_audio(self) -> None:
        settings = default_state().settings
        with self.assertRaisesRegex(ValueError, "audio pronto"):
            render_cards([CopyCard(id="copy-a", text="Oi")], settings, test_only=False)

    def test_render_cards_removes_quotes_from_broll_path_before_calling_engine(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.wav"
            broll = root / "produto.mp4"
            takes = root / "takes"
            audio.write_bytes(b"audio")
            broll.write_bytes(b"video")
            takes.mkdir()
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            settings.broll_path = f'"{broll}"'
            captured = {}

            def fake_process(**kwargs):
                captured.update(kwargs)
                return FakeBatchResult(items=[])

            render_cards([CopyCard(id="copy-a", text="Copy", audio_path=str(audio), status="audio_ready")], settings, test_only=True, process_func=fake_process)

            self.assertEqual(captured["broll_path"], broll)

    def test_render_cards_uses_assembly_detector_when_selected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.wav"
            takes = root / "takes"
            audio.write_bytes(b"audio")
            takes.mkdir()
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            settings.transcription_provider = "assemblyai"
            settings.assemblyai_api_key = "assembly-key"
            captured = {}

            def fake_process(**kwargs):
                captured.update(kwargs)
                return FakeBatchResult(items=[])

            render_cards([CopyCard(id="copy-a", text="Copy", audio_path=str(audio), status="audio_ready")], settings, test_only=True, process_func=fake_process)

            self.assertEqual(captured["speech_detector"].api_key, "assembly-key")

    def test_render_cards_does_not_forward_global_headline_without_a_link(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "copy.wav"
            takes = root / "takes"
            audio.write_bytes(b"audio")
            takes.mkdir()
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            settings.headline_enabled = True
            settings.headline_text = "OFERTA\nSOMENTE HOJE"
            settings.headline_duration = 2.5
            captured = {}

            def fake_process(**kwargs):
                captured.update(kwargs)
                return FakeBatchResult(items=[])

            render_cards([CopyCard(id="copy-a", text="Copy", audio_path=str(audio), status="audio_ready")], settings, test_only=True, process_func=fake_process)

            self.assertFalse(captured["headline_settings"].enabled)
            self.assertEqual(captured["headline_settings"].text, "")

    def test_render_cards_uses_a_separate_headline_setting_for_each_linked_copy(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            takes = root / "takes"
            takes.mkdir()
            plain_audio = root / "plain.wav"
            linked_audio = root / "linked.wav"
            plain_audio.write_bytes(b"audio")
            linked_audio.write_bytes(b"audio")
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(takes)
            settings.headline_enabled = True
            settings.headline_text = "GLOBAL"
            cards = [
                CopyCard(id="plain", text="Sem headline", audio_path=str(plain_audio)),
                CopyCard(id="linked", text="Com headline", audio_path=str(linked_audio), headline={"headline_text": "INDIVIDUAL", "headline_duration": 2}),
            ]
            calls: list[tuple[bool, str, int]] = []

            def fake_process(**kwargs):
                headline = kwargs["headline_settings"]
                audios = list(Path(kwargs["audio_folder"]).glob("*.wav"))
                calls.append((headline.enabled, headline.text, len(audios)))
                items = []
                for index, audio in enumerate(audios):
                    if kwargs.get("output_paths_for_audio"):
                        output_path, subtitle_path = kwargs["output_paths_for_audio"](audio)
                    else:
                        output_path = root / "output" / f"{index}.mp4"
                        subtitle_path = root / "output" / f"{index}.ass"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(b"video")
                    items.append(FakeBatchItem(str(audio), str(output_path), str(subtitle_path)))
                return FakeBatchResult(items=items)

            results = render_cards(cards, settings, test_only=False, process_func=fake_process)

        self.assertEqual([result.card_id for result in results], ["plain", "linked"])
        self.assertEqual(calls, [(False, "", 1), (True, "INDIVIDUAL", 1)])
