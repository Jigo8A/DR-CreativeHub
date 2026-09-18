from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from domain import CopyCard, HubSettings


WINDOWS_COMPONENT_MAX_LENGTH = 255


@dataclass(frozen=True)
class ArtifactPlan:
    audio_path: Path
    transcript_path: Path
    video_path: Path
    job_folder: Path | None
    audio_signature: str
    transcript_signature: str
    render_signature: str

    @classmethod
    def from_card(
        cls,
        card: CopyCard,
        settings: HubSettings,
        *,
        output_folder: Path | None = None,
        internal_folder: Path | None = None,
    ) -> "ArtifactPlan":
        resolved_output_folder = Path(output_folder) if output_folder is not None else Path(settings.output_folder)
        audio_folder = Path(settings.manual_audio_folder) if settings.manual_audio_folder else resolved_output_folder / "audios"
        audio_payload: dict[str, object] = {
            "text": card.text,
            "voice": effective_voice(card, settings),
            "provider": settings.voice_provider,
        }
        if card.audio_source == "manual":
            audio_payload["manual_audio_content"] = manual_audio_content_identity(card.audio_path)
        audio_signature = payload_signature(audio_payload)
        transcript_signature = payload_signature(
            {
                "audio": audio_signature,
                "provider": settings.transcription_provider,
                "audio_edit": audio_edit_payload(settings),
            }
        )
        render_signature = payload_signature(
            {
                "transcript": transcript_signature,
                "render": render_payload(settings),
            }
        )
        stem = safe_copy_stem(card)
        resolved_internal_folder = (
            Path(internal_folder)
            if internal_folder is not None
            else resolved_output_folder.parent / ".creative_hub"
        )
        return cls(
            audio_path=audio_folder / f"{stem}.mp3",
            transcript_path=resolved_internal_folder / "transcricoes" / f"{stem}.json",
            video_path=resolved_output_folder / f"{stem}.mp4",
            job_folder=resolved_internal_folder / "jobs" / resolved_output_folder.name / stem,
            audio_signature=audio_signature,
            transcript_signature=transcript_signature,
            render_signature=render_signature,
        )


def artifact_is_current(path: str | None, stored_signature: str | None, expected_signature: str) -> bool:
    if not path or stored_signature != expected_signature:
        return False
    try:
        return Path(path).is_file()
    except OSError:
        return False


def safe_copy_stem(card: CopyCard) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", card.title)
    title = re.sub(r"\s+", " ", title).strip().rstrip(". ")
    base = title or "copy"
    suffix = f"_{safe_short_id(card.id)}"
    maximum_base_units = WINDOWS_COMPONENT_MAX_LENGTH - len(".json") - len(suffix.encode("utf-16-le")) // 2
    return f"{truncate_utf16(base, maximum_base_units).rstrip('. ')}{suffix}"


def safe_short_id(card_id: str) -> str:
    suffix = re.sub(r'[<>:"/\\|?*\x00-\x1f\s\ud800-\udfff]', "_", card_id[:8]).rstrip(". ")
    if suffix:
        return suffix
    return hashlib.sha256(card_id.encode("utf-8", "surrogatepass")).hexdigest()[:8]


def truncate_utf16(value: str, maximum_units: int) -> str:
    result: list[str] = []
    units = 0
    index = 0
    while index < len(value):
        codepoint = ord(value[index])
        if 0xD800 <= codepoint <= 0xDBFF and index + 1 < len(value) and 0xDC00 <= ord(value[index + 1]) <= 0xDFFF:
            piece = value[index : index + 2]
            piece_units = 2
            index += 2
        elif 0xD800 <= codepoint <= 0xDFFF:
            index += 1
            continue
        else:
            piece = value[index]
            piece_units = 2 if codepoint > 0xFFFF else 1
            index += 1
        if units + piece_units > maximum_units:
            break
        result.append(piece)
        units += piece_units
    return "".join(result)


def effective_voice(card: CopyCard, settings: HubSettings) -> str:
    return card.voice_name.strip() or settings.voice_name.strip()


def manual_audio_content_identity(audio_path: str | None) -> str:
    """Return a content identity so manual-audio caches follow the actual file."""
    path = Path(str(audio_path or "").strip())
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "missing"


def payload_signature(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def audio_edit_payload(settings: HubSettings) -> dict[str, object]:
    return {
        "trim_audio_edges": settings.trim_audio_edges,
        "cut_internal_silence": settings.cut_internal_silence,
        "silence_threshold_db": settings.silence_threshold_db,
        "min_silence_duration": settings.min_silence_duration,
        "keep_silence": settings.keep_silence,
    }


def render_payload(settings: HubSettings) -> dict[str, object]:
    return {
        "takes_folder": settings.takes_folder,
        "broll_path": settings.broll_path,
        "broll_keywords": settings.broll_keywords,
        "segment_duration": settings.segment_duration,
        "background_speed": settings.background_speed,
        "speed_broll": settings.speed_broll,
        "subtitle_mode": settings.subtitle_mode,
        "subtitle_x_position": settings.subtitle_x_position,
        "subtitle_y_position": settings.subtitle_y_position,
        "subtitle_font_size": settings.subtitle_font_size,
        "subtitle_font_name": settings.subtitle_font_name,
        "subtitle_outline_enabled": settings.subtitle_outline_enabled,
        "subtitle_outline_size": settings.subtitle_outline_size,
        "subtitle_highlight_color": settings.subtitle_highlight_color,
        "subtitle_words_per_line": settings.subtitle_words_per_line,
        "subtitle_force_caps": settings.subtitle_force_caps,
        "headline_enabled": settings.headline_enabled,
        "headline_text": settings.headline_text,
        "headline_duration": settings.headline_duration,
        "headline_x_position": settings.headline_x_position,
        "headline_y_position": settings.headline_y_position,
        "headline_font_size": settings.headline_font_size,
        "headline_font_name": settings.headline_font_name,
        "headline_outline_enabled": settings.headline_outline_enabled,
        "headline_outline_size": settings.headline_outline_size,
        "headline_text_color": settings.headline_text_color,
        "headline_background_color": settings.headline_background_color,
        "headline_background_width": settings.headline_background_width,
        "headline_background_height": settings.headline_background_height,
        "headline_corner_radius": settings.headline_corner_radius,
        "background_music_path": settings.background_music_selected_path,
        "background_music_offset_db": settings.background_music_offset_db,
        "background_music_render_nonce": settings.background_music_render_nonce,
    }
