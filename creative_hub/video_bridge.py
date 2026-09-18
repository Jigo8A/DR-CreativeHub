from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Mapping
from uuid import uuid4

from artifacts import ArtifactPlan
from domain import CopyCard, HubSettings, Offer


def resolve_mvp_root(hub_root: Path | None = None) -> Path:
    """Locate the bundled video engine next to the Creative Hub package."""
    root = hub_root or Path(__file__).resolve().parent
    return root.parent / "video_edit_mvp"


MVP_ROOT = resolve_mvp_root()
if str(MVP_ROOT) not in sys.path:
    sys.path.append(str(MVP_ROOT))

from creative_engine import (  # noqa: E402
    AudioEditSettings,
    PreparedCreativeAudio,
    prepare_creative_audio,
    process_creative_batch,
    split_keyword_variants,
)
from silence_engine import SpeechWord, WhisperSpeechDetector, resolve_ffmpeg  # noqa: E402
from subtitles import DEFAULT_FONT_DIR, HeadlineSettings, SubtitleSettings, write_ass_file  # noqa: E402
from assembly_transcriber import AssemblyAISpeechDetector


@dataclass(frozen=True)
class RenderResult:
    card_id: str
    status: str
    output_path: str | None
    subtitle_path: str | None
    error: str | None = None


@dataclass(frozen=True)
class PreparedCardRender:
    audio_folder: Path
    prepared_audio: PreparedCreativeAudio


ProcessFunc = Callable[..., object]


def settings_for_offer(settings: HubSettings, offer: Offer) -> HubSettings:
    """Apply offer-owned media locations while preserving global edit settings."""
    return replace(
        settings,
        takes_folder=offer.takes_folder,
        broll_path=offer.broll_path,
        manual_audio_folder=offer.api_audio_folder or offer.audio_folder,
        output_folder=offer.output_folder,
        background_music_mode=offer.background_music_mode,
        background_music_track_path=offer.background_music_track_path,
        background_music_category=offer.background_music_category,
    )


def settings_for_card(settings: HubSettings, card: CopyCard) -> HubSettings:
    """Apply a copy-owned headline without changing global editing defaults."""
    effective = settings
    if card.background_music_mode != "inherit":
        effective = replace(
            effective,
            background_music_mode=card.background_music_mode,
            background_music_track_path=card.background_music_track_path,
            background_music_category=card.background_music_category,
        )
    headline = card.headline
    if not isinstance(headline, Mapping) or not headline:
        return replace(effective, headline_enabled=False, headline_text="")
    allowed = {key for key in effective.__dataclass_fields__ if key.startswith("headline_")}
    values = {key: value for key, value in headline.items() if key in allowed}
    if not str(values.get("headline_text", "")).strip():
        return replace(effective, headline_enabled=False, headline_text="")
    values["headline_enabled"] = True
    return replace(effective, **values)


def render_cards(
    cards: Iterable[CopyCard],
    settings: HubSettings,
    test_only: bool,
    process_func: ProcessFunc = process_creative_batch,
) -> list[RenderResult]:
    selected = list(cards)
    ready_cards = [card for card in selected if card.audio_path and Path(card.audio_path).is_file()]
    if not ready_cards:
        raise ValueError("Nenhum card selecionado possui audio pronto.")
    if not settings.takes_folder or not Path(settings.takes_folder).is_dir():
        raise ValueError("Selecione uma pasta de takes valida antes de renderizar.")
    if not settings.output_folder:
        raise ValueError("Selecione uma pasta de saida antes de renderizar.")

    plain_cards = [card for card in ready_cards if not card.headline]
    linked_cards = [card for card in ready_cards if card.headline]
    results: dict[str, RenderResult] = {}
    if plain_cards:
        plain_settings = settings_for_card(settings, plain_cards[0])
        for result in _render_batch_cards(plain_cards, plain_settings, test_only, process_func):
            results[result.card_id] = result
    for card in linked_cards:
        effective_settings = settings_for_card(settings, card)
        plan = ArtifactPlan.from_card(card, effective_settings)
        result = render_card(card, effective_settings, plan, test_only, process_func)
        results[result.card_id] = result
    return [results[card.id] for card in ready_cards]


def render_card(
    card: CopyCard,
    settings: HubSettings,
    plan: ArtifactPlan,
    test_only: bool,
    process_func: ProcessFunc = process_creative_batch,
    prepared: PreparedCardRender | None = None,
) -> RenderResult:
    effective_settings = settings_for_card(settings, card)
    if not card.audio_path or not Path(card.audio_path).is_file():
        raise ValueError("O criativo nao possui audio pronto.")
    if not effective_settings.takes_folder or not Path(effective_settings.takes_folder).is_dir():
        raise ValueError("Selecione uma pasta de takes valida antes de renderizar.")
    if not effective_settings.output_folder:
        raise ValueError("Selecione uma pasta de saida antes de renderizar.")

    output_folder = plan.video_path.parent
    job_folder = plan.job_folder or output_folder / "_creative_hub_jobs" / uuid4().hex
    engine_output_folder = job_folder if plan.job_folder else output_folder
    audio_folder = prepared.audio_folder if prepared else _stage_audio([card], job_folder)
    detector = None if prepared else _speech_detector(effective_settings)
    prepared_audios = (
        {str(prepared.prepared_audio.source_path.resolve()): prepared.prepared_audio}
        if prepared
        else None
    )
    batch = process_func(
        audio_folder=audio_folder,
        takes_folder=Path(effective_settings.takes_folder),
        output_folder=engine_output_folder,
        broll_path=_path_from_setting(effective_settings.broll_path),
        keyword_variants=split_keyword_variants(effective_settings.broll_keywords),
        segment_duration=float(effective_settings.segment_duration),
        subtitle_settings=_subtitle_settings(effective_settings),
        headline_settings=_headline_settings(effective_settings),
        speech_detector=detector,
        limit=1 if test_only else None,
        audio_edit_settings=_audio_settings(effective_settings),
        background_speed=float(effective_settings.background_speed),
        speed_broll=bool(effective_settings.speed_broll),
        background_music_path=_path_from_setting(effective_settings.background_music_selected_path),
        background_music_offset_db=float(effective_settings.background_music_offset_db),
        word_loader=_cached_word_loader(plan, detector) if detector else None,
        prepared_audios=prepared_audios,
        output_paths_for_audio=lambda _: (
            (job_folder / f"{plan.video_path.stem}.mp4") if plan.job_folder else plan.video_path,
            (job_folder / f"{plan.video_path.stem}.ass") if plan.job_folder else plan.video_path.with_suffix(".ass"),
        ),
    )
    result = _apply_batch_results([card], batch)[0]
    if result.status == "completed":
        if plan.job_folder:
            rendered_video = Path(result.output_path or "")
            plan.video_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(rendered_video), plan.video_path)
            result = replace(result, output_path=str(plan.video_path))
            card.output_path = result.output_path
        card.transcript_path = str(plan.transcript_path)
        card.transcript_signature = plan.transcript_signature
        card.render_signature = plan.render_signature
    return result


def prepare_card_for_render(card: CopyCard, settings: HubSettings, plan: ArtifactPlan) -> PreparedCardRender:
    effective_settings = settings_for_card(settings, card)
    if not card.audio_path or not Path(card.audio_path).is_file():
        raise ValueError("O criativo nao possui audio pronto.")
    if not effective_settings.takes_folder or not Path(effective_settings.takes_folder).is_dir():
        raise ValueError("Selecione uma pasta de takes valida antes de renderizar.")
    if not effective_settings.output_folder:
        raise ValueError("Selecione uma pasta de saida antes de renderizar.")

    output_folder = plan.video_path.parent
    job_folder = plan.job_folder or output_folder / "_creative_hub_jobs" / uuid4().hex
    audio_folder = _stage_audio([card], job_folder)
    staged_audio = next(path for path in audio_folder.iterdir() if path.is_file())
    detector = _speech_detector(effective_settings)
    prepared_audio = prepare_creative_audio(
        audio=staged_audio,
        output_folder=job_folder,
        batch_stamp=uuid4().hex[:12],
        audio_edit_settings=_audio_settings(effective_settings),
        speech_detector=detector,
        word_loader=_cached_word_loader(plan, detector),
    )
    return PreparedCardRender(audio_folder=audio_folder, prepared_audio=prepared_audio)


def _render_batch_cards(
    cards: list[CopyCard],
    settings: HubSettings,
    test_only: bool,
    process_func: ProcessFunc,
) -> list[RenderResult]:
    output_folder = Path(settings.output_folder)
    audio_folder = _stage_audio(cards, output_folder / "_creative_hub_jobs" / uuid4().hex)
    batch = process_func(
        audio_folder=audio_folder,
        takes_folder=Path(settings.takes_folder),
        output_folder=output_folder,
        broll_path=_path_from_setting(settings.broll_path),
        keyword_variants=split_keyword_variants(settings.broll_keywords),
        segment_duration=float(settings.segment_duration),
        subtitle_settings=_subtitle_settings(settings),
        headline_settings=_headline_settings(settings),
        speech_detector=_speech_detector(settings),
        limit=1 if test_only else None,
        audio_edit_settings=_audio_settings(settings),
        background_speed=float(settings.background_speed),
        speed_broll=bool(settings.speed_broll),
        background_music_path=_path_from_setting(settings.background_music_selected_path),
        background_music_offset_db=float(settings.background_music_offset_db),
    )
    return _apply_batch_results(cards, batch)


def render_headline_preview(settings: HubSettings) -> bytes:
    headline = _headline_settings(settings)
    if not headline.enabled or not headline.text.strip():
        raise ValueError("Ative a headline e escreva um texto para gerar a previa.")
    with TemporaryDirectory(prefix="creative_hub_headline_") as directory:
        temporary = Path(directory)
        subtitle_path = temporary / "headline.ass"
        preview_path = temporary / "headline.png"
        write_ass_file(subtitle_path, [], SubtitleSettings(), headline=headline)
        filter_value = (
            f"subtitles='{_escape_ass_path(subtitle_path)}':fontsdir='{_escape_ass_path(DEFAULT_FONT_DIR)}',"
            "format=rgba,colorkey=black:0.01:0"
        )
        command = [
            str(resolve_ffmpeg()),
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=720x1280:d=0.1",
        ]
        if headline.emoji_overlay_path:
            overlay = _escape_ass_path(headline.emoji_overlay_path)
            command.extend(
                [
                    "-filter_complex",
                    f"[0:v]{filter_value}[base];movie='{overlay}',format=rgba[headline];[base][headline]overlay=0:0:eof_action=repeat[preview]",
                    "-map",
                    "[preview]",
                ]
            )
        else:
            command.extend(["-vf", filter_value])
        command.extend(["-frames:v", "1", "-pix_fmt", "rgba", str(preview_path)])
        subprocess.run(command, check=True)
        return preview_path.read_bytes()


def _stage_audio(cards: list[CopyCard], job_folder: Path) -> Path:
    stage_folder = job_folder / "audio"
    stage_folder.mkdir(parents=True, exist_ok=True)
    for index, card in enumerate(cards, start=1):
        source = Path(card.audio_path or "")
        destination = stage_folder / f"{index:03d}_{card.id}{source.suffix.lower()}"
        shutil.copy2(source, destination)
    return stage_folder


def _path_from_setting(value: str) -> Path | None:
    normalized = str(value or "").strip().strip('"')
    return Path(normalized) if normalized else None


def _speech_detector(settings: HubSettings):
    provider = settings.transcription_provider.strip().lower() or "local"
    if provider == "local":
        return WhisperSpeechDetector()
    if provider == "assemblyai":
        if not settings.assemblyai_api_key.strip():
            raise ValueError("Informe a chave da API AssemblyAI nas configuracoes de transcricao.")
        return AssemblyAISpeechDetector(settings.assemblyai_api_key)
    raise ValueError("Selecione um provedor de transcricao valido.")


def _cached_word_loader(plan: ArtifactPlan, detector):
    def load(audio_path: Path) -> list[SpeechWord]:
        cached = _read_cached_words(plan)
        if cached is not None:
            return cached
        words = detector.detect_words(audio_path)
        _write_cached_words(plan, words)
        return words

    return load


def _read_cached_words(plan: ArtifactPlan) -> list[SpeechWord] | None:
    try:
        payload = json.loads(plan.transcript_path.read_text(encoding="utf-8"))
        if payload.get("signature") != plan.transcript_signature:
            return None
        return [SpeechWord(str(word["text"]), float(word["start"]), float(word["end"])) for word in payload["words"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cached_words(plan: ArtifactPlan, words: list[SpeechWord]) -> None:
    plan.transcript_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "signature": plan.transcript_signature,
        "words": [{"text": word.text, "start": word.start, "end": word.end} for word in words],
    }
    temporary = plan.transcript_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(plan.transcript_path)


def _apply_batch_results(cards: list[CopyCard], batch: object) -> list[RenderResult]:
    items = list(getattr(batch, "items", []))
    results: list[RenderResult] = []
    for card, item in zip(cards, items):
        output_path = getattr(item, "output_path", None)
        subtitle_path = getattr(item, "subtitle_path", None)
        status = str(getattr(item, "status", "failed"))
        error = getattr(item, "error", None)
        card.status = "rendered" if status == "completed" else "error"
        card.output_path = output_path
        card.subtitle_path = subtitle_path
        card.error = error
        results.append(RenderResult(card.id, status, output_path, subtitle_path, error))
    for card in cards[len(items):]:
        card.status = "error"
        card.error = "O motor nao retornou resultado para este criativo."
        results.append(RenderResult(card.id, "failed", None, None, card.error))
    return results


def _subtitle_settings(settings: HubSettings) -> SubtitleSettings:
    return SubtitleSettings(
        mode=settings.subtitle_mode,
        x_position=float(settings.subtitle_x_position),
        y_position=float(settings.subtitle_y_position),
        font_size=int(settings.subtitle_font_size),
        font_name=settings.subtitle_font_name,
        outline_size=int(settings.subtitle_outline_size) if settings.subtitle_outline_enabled else 0,
        highlight_color=_hex_to_rgb(settings.subtitle_highlight_color, (255, 239, 0)),
        max_words_per_line=int(settings.subtitle_words_per_line),
        force_all_caps=bool(settings.subtitle_force_caps),
    )


def _headline_settings(settings: HubSettings) -> HeadlineSettings:
    headline = HeadlineSettings(
        enabled=bool(settings.headline_enabled),
        text=settings.headline_text,
        duration=float(settings.headline_duration),
        x_position=float(settings.headline_x_position),
        y_position=float(settings.headline_y_position),
        font_size=int(settings.headline_font_size),
        font_name=settings.headline_font_name,
        outline_size=int(settings.headline_outline_size) if settings.headline_outline_enabled else 0,
        text_color=_hex_to_rgb(settings.headline_text_color, (255, 255, 255)),
        background_color=_hex_to_rgb(settings.headline_background_color, (18, 24, 15)),
        background_width=int(settings.headline_background_width),
        background_height=int(settings.headline_background_height),
        corner_radius=int(settings.headline_corner_radius),
    )
    return headline


def _hex_to_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def _escape_ass_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _audio_settings(settings: HubSettings) -> AudioEditSettings:
    return AudioEditSettings(
        trim_edges=bool(settings.trim_audio_edges),
        cut_internal_silence=bool(settings.cut_internal_silence),
        silence_threshold_db=int(settings.silence_threshold_db),
        min_silence_duration=float(settings.min_silence_duration),
        keep_silence=float(settings.keep_silence),
    )
