from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from threading import Lock
import time
from typing import Callable, Literal, Mapping
from uuid import uuid4

from artifacts import ArtifactPlan, artifact_is_current
from batches import BatchTarget
from domain import CopyCard, HubSettings, Offer
from music_library import resolve_background_music, scan_music_library
from video_bridge import PreparedCardRender, RenderResult, prepare_card_for_render, render_card, settings_for_card, settings_for_offer


ProgressCallback = Callable[[str, int, list[dict]], None]
RenderCard = Callable[[CopyCard, HubSettings, ArtifactPlan, bool], RenderResult]
PrepareCard = Callable[[CopyCard, HubSettings, ArtifactPlan], PreparedCardRender]


@dataclass(frozen=True)
class ProductionItem:
    offer: Offer | None
    card: CopyCard


class ProductionCoordinator:
    def __init__(
        self,
        voice_provider_factory,
        render_card_func: RenderCard = render_card,
        max_voice_workers: int = 4,
        max_render_workers: int = 2,
        max_transcription_workers: int = 4,
        prepare_card_func: PrepareCard | None = None,
    ) -> None:
        self.voice_provider_factory = voice_provider_factory
        self.render_card_func = render_card_func
        self.max_voice_workers = max(1, int(max_voice_workers))
        self.max_render_workers = max(1, int(max_render_workers))
        self.max_transcription_workers = max(1, int(max_transcription_workers))
        self.prepare_card_func = prepare_card_func if prepare_card_func is not None else (
            prepare_card_for_render if render_card_func is render_card else None
        )

    def run(
        self,
        cards: list[CopyCard | ProductionItem],
        settings: HubSettings,
        mode: Literal["batch", "test"],
        progress: ProgressCallback,
        batch_targets: Mapping[str, BatchTarget] | None = None,
    ) -> list[dict]:
        if mode not in {"batch", "test"}:
            raise ValueError("Modo de producao invalido.")
        eligible = [self._item(item) for item in cards]
        eligible = [item for item in eligible if is_production_eligible(item.card)]
        if not eligible:
            raise ValueError("Nenhuma copy pronta para producao foi encontrada.")

        render_workers = self._render_worker_count(settings)
        plans = {item.card.id: self._plan(settings, item, batch_targets) for item in eligible}
        results: list[dict] = []
        results_lock = Lock()
        pending_audio = []
        ready_to_render: list[tuple[ProductionItem, ArtifactPlan, list[str]]] = []

        for item in eligible:
            card = item.card
            plan = plans[card.id]
            if self._render_is_current(card, plan):
                card.status = "rendered"
                card.error = None
                results.append(self._result(item, plan, "completed", ["video"]))
                progress(self._status("Reaproveitado", item), self._percent(len(results), len(eligible)), results)
                continue
            if card.audio_source == "manual":
                if not card.audio_path or not Path(card.audio_path).is_file():
                    self._failure(item, plan, results, "O audio manual nao foi encontrado.", progress, len(eligible))
                    continue
                card.audio_signature = plan.audio_signature
                ready_to_render.append((item, plan, ["audio"]))
            elif artifact_is_current(card.audio_path, card.audio_signature, plan.audio_signature):
                ready_to_render.append((item, plan, ["audio"]))
            else:
                pending_audio.append((item, plan))

        if self.prepare_card_func:
            self._run_split_pipeline(
                ready_to_render,
                pending_audio,
                settings,
                mode,
                results,
                results_lock,
                progress,
                len(eligible),
                render_workers,
            )
            return results

        self._run_legacy_pipeline(
            ready_to_render,
            pending_audio,
            settings,
            mode,
            results,
            results_lock,
            progress,
            len(eligible),
            render_workers,
        )
        return results

    def _render_worker_count(self, settings: HubSettings) -> int:
        try:
            requested = int(getattr(settings, "render_concurrency", self.max_render_workers))
        except (TypeError, ValueError):
            requested = self.max_render_workers
        return max(1, min(self.max_render_workers, requested))

    def _run_legacy_pipeline(self, ready_to_render, pending_audio, settings, mode, results, results_lock, progress, total, render_workers) -> None:
        with ThreadPoolExecutor(max_workers=render_workers) as render_executor:
            render_futures = [
                render_executor.submit(
                    self._render,
                    item,
                    plan,
                    self._settings(settings, item),
                    mode == "test",
                    reused,
                    results,
                    results_lock,
                    progress,
                    total,
                )
                for item, plan, reused in ready_to_render
            ]

            if pending_audio:
                provider = self.voice_provider_factory()
                with ThreadPoolExecutor(max_workers=self.max_voice_workers) as voice_executor:
                    voice_futures = {
                        voice_executor.submit(self._generate_audio, provider, item.card, plan, self._settings(settings, item)): (item, plan)
                        for item, plan in pending_audio
                    }
                    for future in as_completed(voice_futures):
                        item, plan = voice_futures[future]
                        try:
                            future.result()
                            render_futures.append(
                                render_executor.submit(
                                    self._render,
                                    item,
                                    plan,
                                    self._settings(settings, item),
                                    mode == "test",
                                    [],
                                    results,
                                    results_lock,
                                    progress,
                                    total,
                                )
                            )
                        except Exception as exc:
                            self._failure(item, plan, results, str(exc), progress, total, results_lock)

            for future in as_completed(render_futures):
                future.result()

    def _run_split_pipeline(self, ready_to_render, pending_audio, settings, mode, results, results_lock, progress, total, render_workers) -> None:
        futures = {}
        with (
            ThreadPoolExecutor(max_workers=self.max_voice_workers) as voice_executor,
            ThreadPoolExecutor(max_workers=self.max_transcription_workers) as transcription_executor,
            ThreadPoolExecutor(max_workers=render_workers) as render_executor,
        ):
            def submit_transcription(item, plan, reused):
                future = transcription_executor.submit(self._prepare_render, item, plan, self._settings(settings, item))
                futures[future] = ("transcription", item, plan, reused)

            def submit_render(item, plan, reused, prepared):
                future = render_executor.submit(
                    self._render,
                    item,
                    plan,
                    self._settings(settings, item),
                    mode == "test",
                    reused,
                    results,
                    results_lock,
                    progress,
                    total,
                    prepared,
                )
                futures[future] = ("render", item, plan, reused)

            for item, plan, reused in ready_to_render:
                submit_transcription(item, plan, reused)

            if pending_audio:
                provider = self.voice_provider_factory()
                for item, plan in pending_audio:
                    future = voice_executor.submit(self._generate_audio, provider, item.card, plan, self._settings(settings, item))
                    futures[future] = ("voice", item, plan, [])

            while futures:
                completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in completed:
                    stage, item, plan, reused = futures.pop(future)
                    try:
                        value = future.result()
                    except Exception as exc:
                        self._failure(item, plan, results, str(exc), progress, total, results_lock)
                        continue
                    if stage == "voice":
                        submit_transcription(item, plan, reused)
                    elif stage == "transcription":
                        submit_render(item, plan, reused, value)

    def _prepare_render(self, item, plan, settings) -> PreparedCardRender:
        item.card.status = "transcribing"
        if not self.prepare_card_func:
            raise RuntimeError("A preparacao de transcricao nao esta configurada.")
        return self.prepare_card_func(item.card, settings, plan)

    def _generate_audio(self, provider, card: CopyCard, plan: ArtifactPlan, settings: HubSettings) -> None:
        card.status = "generating"
        effective_settings = replace(settings, voice_name=card.voice_name or settings.voice_name)
        started = time.perf_counter()
        path = provider.generate(card, effective_settings, destination=plan.audio_path)
        timings = dict(getattr(card, "_production_timings", {}))
        timings["audio_api"] = round(time.perf_counter() - started, 4)
        card._production_timings = timings
        card.audio_path = str(path)
        card.audio_signature = plan.audio_signature
        card.audio_source = "api"
        card.error = None

    def _render(self, item, plan, settings, test_only, reused, results, results_lock, progress, total, prepared=None) -> None:
        card = item.card
        try:
            card.status = "rendering"
            started = time.perf_counter()
            result = self.render_card_func(card, settings, plan, test_only, prepared=prepared) if prepared else self.render_card_func(card, settings, plan, test_only)
            timings = dict(getattr(card, "_production_timings", {}))
            timings["render_orchestration"] = round(time.perf_counter() - started, 4)
            card._production_timings = timings
            if result.status != "completed":
                raise RuntimeError(result.error or "Nao foi possivel renderizar o criativo.")
            card.status = "rendered"
            card.output_path = result.output_path
            card.subtitle_path = result.subtitle_path
            card.render_signature = plan.render_signature
            card.error = None
            self._write_performance_report(item, plan)
            with results_lock:
                results.append(self._result(item, plan, "completed", reused))
                progress(self._status("Renderizando", item), self._percent(len(results), total), results)
        except Exception as exc:
            self._failure(item, plan, results, str(exc), progress, total, results_lock)

    def _failure(self, item, plan, results, error, progress, total, results_lock=None) -> None:
        card = item.card
        card.status = "error"
        card.error = error
        if results_lock:
            with results_lock:
                results.append(self._result(item, plan, "failed", [], error))
                progress(self._status("Erro", item), self._percent(len(results), total), results)
            return
        results.append(self._result(item, plan, "failed", [], error))
        progress(self._status("Erro", item), self._percent(len(results), total), results)

    @staticmethod
    def _result(item, plan, status, reused, error=None) -> dict:
        card = item.card
        return {
            "card_id": card.id,
            "offer_id": item.offer.id if item.offer else None,
            "offer_name": item.offer.name if item.offer else None,
            "status": status,
            "audio": plan.audio_path.name,
            "transcript": plan.transcript_path.name,
            "video": plan.video_path.name,
            "reused": reused,
            "timings": dict(getattr(card, "_production_timings", {})),
            "error": error,
        }

    @staticmethod
    def _write_performance_report(item: ProductionItem, plan: ArtifactPlan) -> None:
        if plan.job_folder is None:
            return
        plan.job_folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": "creative_hub_performance",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "card_id": item.card.id,
            "offer_id": item.offer.id if item.offer else None,
            "timings": dict(getattr(item.card, "_production_timings", {})),
        }
        (plan.job_folder / "performance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _percent(completed: int, total: int) -> int:
        return min(100, round((completed / max(1, total)) * 100))

    @staticmethod
    def _item(value: CopyCard | ProductionItem) -> ProductionItem:
        return value if isinstance(value, ProductionItem) else ProductionItem(None, value)

    @staticmethod
    def _settings(settings: HubSettings, item: ProductionItem) -> HubSettings:
        offer_settings = settings_for_offer(settings, item.offer) if item.offer else settings
        effective = settings_for_card(offer_settings, item.card)
        return replace(
            effective,
            background_music_selected_path=getattr(item.card, "_background_music_selected_path", ""),
            background_music_render_nonce=getattr(item.card, "_background_music_render_nonce", ""),
        )

    @classmethod
    def _plan(
        cls,
        settings: HubSettings,
        item: ProductionItem,
        batch_targets: Mapping[str, BatchTarget] | None,
    ) -> ArtifactPlan:
        effective_settings = cls._settings(settings, item)
        mode = effective_settings.background_music_mode
        nonce = uuid4().hex if mode == "category" else ""
        selection = resolve_background_music(
            mode,
            effective_settings.background_music_track_path,
            effective_settings.background_music_category,
            scan_music_library(),
            random.Random(),
            nonce=nonce,
        )
        item.card._background_music_selected_path = str(selection.path or "")
        item.card._background_music_render_nonce = selection.nonce
        effective_settings = cls._settings(settings, item)
        target = batch_targets.get(item.offer.id) if batch_targets and item.offer else None
        if target is None:
            return ArtifactPlan.from_card(item.card, effective_settings)
        return ArtifactPlan.from_card(
            item.card,
            effective_settings,
            output_folder=target.output_folder,
            internal_folder=target.internal_folder,
        )

    @staticmethod
    def _render_is_current(card: CopyCard, plan: ArtifactPlan) -> bool:
        if not artifact_is_current(card.output_path, card.render_signature, plan.render_signature):
            return False
        try:
            return Path(card.output_path or "").resolve() == plan.video_path.resolve()
        except OSError:
            return False

    @staticmethod
    def _status(action: str, item: ProductionItem) -> str:
        prefix = f"{item.offer.name}: " if item.offer else ""
        return f"{action}: {prefix}{item.card.title or item.card.id}"


def is_production_eligible(card: CopyCard) -> bool:
    return bool(card.text.strip()) or (card.audio_source == "manual" and bool(card.audio_path))
