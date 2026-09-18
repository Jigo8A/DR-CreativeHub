from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest

from domain import CopyCard, Offer, default_state
from production import ProductionCoordinator, ProductionItem
from batches import BatchTarget
from video_bridge import RenderResult


class FakeVoiceProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, card, settings, progress_callback=None, destination=None):
        self.calls.append(card.id)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return path


class ProductionCoordinatorTests(unittest.TestCase):
    def test_default_voice_concurrency_is_four(self) -> None:
        coordinator = ProductionCoordinator(lambda: None)

        self.assertEqual(coordinator.max_voice_workers, 4)

    def test_batch_uses_each_offer_output_folder(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio_a = root / "a.mp3"
            audio_b = root / "b.mp3"
            audio_a.write_bytes(b"a")
            audio_b.write_bytes(b"b")
            calls = []

            def fake_render(card, settings, plan, test_only):
                calls.append(settings.output_folder)
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(card.id, "completed", str(plan.video_path), str(plan.video_path.with_suffix(".ass")))

            items = [
                ProductionItem(Offer(id="a", name="Produto A", slug="a", takes_folder=str(root), output_folder=str(root / "output-a")), CopyCard(id="a", title="A", text="texto", audio_source="manual", audio_path=str(audio_a))),
                ProductionItem(Offer(id="b", name="Produto B", slug="b", takes_folder=str(root), output_folder=str(root / "output-b")), CopyCard(id="b", title="B", text="texto", audio_source="manual", audio_path=str(audio_b))),
            ]

            ProductionCoordinator(lambda: None, render_card_func=fake_render).run(items, default_state().settings, "batch", lambda *_: None)

            self.assertEqual(calls, [str(root / "output-a"), str(root / "output-b")])

    def test_batch_generates_missing_audio_and_renders_every_copy(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(root / "takes")
            Path(settings.takes_folder).mkdir()
            cards = [CopyCard(id="one", title="Video 1", text="Primeira"), CopyCard(id="two", title="Video 2", text="Segunda")]
            provider = FakeVoiceProvider()
            rendered = []

            def fake_render(card, current_settings, plan, test_only):
                rendered.append((card.id, plan.video_path.name, test_only))
                plan.video_path.write_bytes(b"video")
                card.output_path = str(plan.video_path)
                return RenderResult(card.id, "completed", str(plan.video_path), None)

            results = ProductionCoordinator(lambda: provider, fake_render, max_voice_workers=2).run(cards, settings, "batch", lambda *_: None)

        self.assertEqual(set(provider.calls), {"one", "two"})
        self.assertEqual({item["card_id"] for item in results}, {"one", "two"})
        self.assertEqual({item["video"] for item in results}, {"Video 1_one.mp4", "Video 2_two.mp4"})
        self.assertTrue(all(not item[2] for item in rendered))

    def test_batch_result_exposes_audio_and_render_timings(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.takes_folder = str(root / "takes")
            Path(settings.takes_folder).mkdir()
            card = CopyCard(id="one", title="Video 1", text="Primeira")

            def fake_render(current_card, _settings, plan, _test_only):
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(current_card.id, "completed", str(plan.video_path), None)

            result = ProductionCoordinator(lambda: FakeVoiceProvider(), fake_render).run(
                [card], settings, "batch", lambda *_: None
            )[0]

        self.assertIn("audio_api", result["timings"])
        self.assertIn("render_orchestration", result["timings"])
        self.assertTrue(all(value >= 0 for value in result["timings"].values()))

    def test_batch_renders_a_manual_audio_without_copy_text_or_api_narration(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "manual.wav"
            audio.write_bytes(b"manual audio")
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            rendered = []

            def fake_render(card, _settings, plan, _test_only):
                rendered.append(card.id)
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(card.id, "completed", str(plan.video_path), None)

            card = CopyCard(id="manual", title="Audio manual", audio_source="manual", audio_path=str(audio))
            results = ProductionCoordinator(lambda: self.fail("nao deve gerar narracao por API"), fake_render).run(
                [card], settings, "batch", lambda *_: None
            )

        self.assertEqual(rendered, ["manual"])
        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(results[0]["reused"], ["audio"])

    def test_batch_renders_two_manual_cards_concurrently(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            active = 0
            peak = 0
            lock = Lock()

            def fake_render(card, _settings, plan, _test_only):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.05)
                with lock:
                    active -= 1
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(card.id, "completed", str(plan.video_path), None)

            cards = []
            for card_id in ("one", "two"):
                audio = root / f"{card_id}.mp3"
                audio.write_bytes(b"audio")
                cards.append(CopyCard(id=card_id, title=card_id, audio_source="manual", audio_path=str(audio)))

            results = ProductionCoordinator(lambda: None, fake_render, max_render_workers=2).run(
                cards, settings, "batch", lambda *_: None
            )

        self.assertEqual(peak, 2)
        self.assertEqual({item["card_id"] for item in results}, {"one", "two"})

    def test_render_concurrency_setting_can_limit_manual_cards_to_one_worker(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            settings.render_concurrency = 1
            active = 0
            peak = 0
            lock = Lock()

            def fake_render(card, _settings, plan, _test_only):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(card.id, "completed", str(plan.video_path), None)

            cards = []
            for card_id in ("one", "two"):
                audio = root / f"{card_id}.mp3"
                audio.write_bytes(b"audio")
                cards.append(CopyCard(id=card_id, title=card_id, audio_source="manual", audio_path=str(audio)))

            ProductionCoordinator(lambda: None, fake_render, max_render_workers=2).run(
                cards, settings, "batch", lambda *_: None
            )

        self.assertEqual(peak, 1)

    def test_split_pipeline_allows_four_transcriptions_before_the_render_queue(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            active_transcriptions = 0
            peak_transcriptions = 0
            active_renders = 0
            peak_renders = 0
            lock = Lock()

            def fake_prepare(card, _settings, _plan):
                nonlocal active_transcriptions, peak_transcriptions
                with lock:
                    active_transcriptions += 1
                    peak_transcriptions = max(peak_transcriptions, active_transcriptions)
                time.sleep(0.05)
                with lock:
                    active_transcriptions -= 1
                return card.id

            def fake_render(card, _settings, plan, _test_only, prepared=None):
                nonlocal active_renders, peak_renders
                self.assertEqual(prepared, card.id)
                with lock:
                    active_renders += 1
                    peak_renders = max(peak_renders, active_renders)
                time.sleep(0.02)
                with lock:
                    active_renders -= 1
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"video")
                return RenderResult(card.id, "completed", str(plan.video_path), None)

            cards = []
            for card_id in ("one", "two", "three", "four"):
                audio = root / f"{card_id}.mp3"
                audio.write_bytes(b"audio")
                cards.append(CopyCard(id=card_id, title=card_id, audio_source="manual", audio_path=str(audio)))

            results = ProductionCoordinator(
                lambda: None,
                fake_render,
                prepare_card_func=fake_prepare,
                max_transcription_workers=4,
                max_render_workers=1,
            ).run(cards, settings, "batch", lambda *_: None)

        self.assertEqual(peak_transcriptions, 4)
        self.assertEqual(peak_renders, 1)
        self.assertEqual({item["card_id"] for item in results}, {"one", "two", "three", "four"})

    def test_batch_reuses_existing_video_and_skips_voice_generation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            settings.output_folder = str(root / "output")
            card = CopyCard(id="one", title="Video 1", text="Primeira")
            provider = FakeVoiceProvider()
            coordinator = ProductionCoordinator(lambda: provider, lambda *_: self.fail("nao deve renderizar"))
            from artifacts import ArtifactPlan

            plan = ArtifactPlan.from_card(card, settings)
            plan.video_path.parent.mkdir(parents=True)
            plan.video_path.write_bytes(b"video")
            card.output_path = str(plan.video_path)
            card.render_signature = plan.render_signature

            results = coordinator.run([card], settings, "batch", lambda *_: None)

        self.assertEqual(provider.calls, [])
        self.assertEqual(results[0]["reused"], ["video"])

    def test_batch_target_renders_a_new_video_without_regenerating_api_audio(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = default_state().settings
            takes = root / "takes"
            takes.mkdir()
            api_audio = root / "audios_api" / "Video 1_one.mp3"
            api_audio.parent.mkdir()
            api_audio.write_bytes(b"audio")
            offer = Offer(
                id="kids",
                name="Kids",
                slug="kids",
                takes_folder=str(takes),
                api_audio_folder=str(api_audio.parent),
                output_folder=str(root / "output"),
            )
            card = CopyCard(id="one", title="Video 1", text="Primeira", audio_path=str(api_audio))
            from artifacts import ArtifactPlan

            from video_bridge import settings_for_offer

            offer_settings = settings_for_offer(settings, offer)
            old_plan = ArtifactPlan.from_card(card, offer_settings)
            old_plan.video_path.parent.mkdir(parents=True, exist_ok=True)
            old_plan.video_path.write_bytes(b"old video")
            card.output_path = str(old_plan.video_path)
            card.audio_signature = old_plan.audio_signature
            card.render_signature = old_plan.render_signature
            rendered = []

            def fake_render(_card, _settings, plan, _test_only):
                rendered.append(plan)
                plan.video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path.write_bytes(b"new video")
                return RenderResult(card.id, "completed", str(plan.video_path), str(plan.job_folder / "video.ass"))

            target = BatchTarget("kids", "lote-001-2026-09-17_1430", root / "output" / "lote-001-2026-09-17_1430", root / ".creative_hub")
            results = ProductionCoordinator(lambda: self.fail("nao deve gerar audio"), fake_render).run(
                [ProductionItem(offer, card)],
                settings,
                "batch",
                lambda *_: None,
                batch_targets={"kids": target},
            )

        self.assertEqual(len(rendered), 1)
        self.assertEqual(rendered[0].video_path.parent, target.output_folder)
        self.assertEqual(results[0]["reused"], ["audio"])
