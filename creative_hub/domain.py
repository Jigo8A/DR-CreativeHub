from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CopyCard:
    id: str
    title: str = ""
    text: str = ""
    audio_source: str = "api"
    voice_name: str = ""
    audio_path: str | None = None
    status: str = "draft"
    output_path: str | None = None
    subtitle_path: str | None = None
    error: str | None = None
    transcript_path: str | None = None
    audio_signature: str | None = None
    transcript_signature: str | None = None
    render_signature: str | None = None
    headline: dict[str, Any] | None = None
    background_music_mode: str = "inherit"
    background_music_track_path: str = ""
    background_music_category: str = ""


@dataclass
class HubSettings:
    creative_root_folder: str = ""
    takes_folder: str = ""
    manual_audio_folder: str = ""
    output_folder: str = ""
    broll_path: str = ""
    broll_keywords: str = ""
    segment_duration: float = 3.0
    background_speed: float = 1.0
    speed_broll: bool = False
    trim_audio_edges: bool = True
    cut_internal_silence: bool = False
    silence_threshold_db: int = -35
    min_silence_duration: float = 0.4
    keep_silence: float = 0.18
    subtitle_mode: str = "highlight"
    subtitle_x_position: float = 0.5
    subtitle_y_position: float = 0.66
    subtitle_font_size: int = 24
    subtitle_font_name: str = "Uninsta Heavy"
    subtitle_outline_enabled: bool = True
    subtitle_outline_size: int = 3
    subtitle_highlight_color: str = "#FFEF00"
    subtitle_words_per_line: int = 3
    subtitle_force_caps: bool = True
    safe_zone_visible: bool = False
    headline_enabled: bool = False
    headline_text: str = ""
    headline_duration: float = 3.0
    headline_x_position: float = 0.5
    headline_y_position: float = 0.2
    headline_font_size: int = 48
    headline_font_name: str = "Uninsta Heavy"
    headline_outline_enabled: bool = False
    headline_outline_size: int = 0
    headline_text_color: str = "#FFFFFF"
    headline_background_color: str = "#12180F"
    headline_background_width: int = 560
    headline_background_height: int = 150
    headline_corner_radius: int = 24
    voice_provider: str = ""
    voice_name: str = ""
    voice_speed: float = 1.0
    voice_api_key: str = ""
    transcription_provider: str = "local"
    assemblyai_api_key: str = ""
    render_concurrency: int = 2
    background_music_offset_db: float = -18.0
    background_music_mode: str = "none"
    background_music_track_path: str = ""
    background_music_category: str = ""
    background_music_selected_path: str = ""
    background_music_render_nonce: str = ""


@dataclass
class Offer:
    id: str
    name: str
    slug: str
    takes_folder: str = ""
    broll_path: str = ""
    audio_folder: str = ""
    api_audio_folder: str = ""
    manual_audio_inbox_folder: str = ""
    manual_audio_library_folder: str = ""
    output_folder: str = ""
    copies: list[CopyCard] = field(default_factory=list)
    background_music_mode: str = "none"
    background_music_track_path: str = ""
    background_music_category: str = ""


@dataclass
class HubState:
    settings: HubSettings = field(default_factory=HubSettings)
    offers: list[Offer] = field(default_factory=list)
    active_offer_id: str = ""

    @property
    def active_offer(self) -> Offer:
        for offer in self.offers:
            if offer.id == self.active_offer_id:
                return offer
        if not self.offers:
            self.offers.append(default_offer())
        self.active_offer_id = self.offers[0].id
        return self.offers[0]

    @property
    def copies(self) -> list[CopyCard]:
        return self.active_offer.copies


def default_state() -> HubState:
    offer = default_offer()
    return HubState(offers=[offer], active_offer_id=offer.id)


def default_offer() -> Offer:
    return Offer(id="default", name="Oferta inicial", slug="oferta-inicial")


def copy_from_dict(data: dict[str, Any]) -> CopyCard:
    return CopyCard(
        id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        text=str(data.get("text", "")),
        audio_source=str(data.get("audio_source", "api")),
        voice_name=str(data.get("voice_name", "")),
        audio_path=_optional_text(data.get("audio_path")),
        status=str(data.get("status", "draft")),
        output_path=_optional_text(data.get("output_path")),
        subtitle_path=_optional_text(data.get("subtitle_path")),
        error=_optional_text(data.get("error")),
        transcript_path=_optional_text(data.get("transcript_path")),
        audio_signature=_optional_text(data.get("audio_signature")),
        transcript_signature=_optional_text(data.get("transcript_signature")),
        render_signature=_optional_text(data.get("render_signature")),
        headline=dict(data["headline"]) if isinstance(data.get("headline"), dict) else None,
        background_music_mode=str(data.get("background_music_mode", "inherit")),
        background_music_track_path=str(data.get("background_music_track_path", "")),
        background_music_category=str(data.get("background_music_category", "")),
    )


def settings_from_dict(data: dict[str, Any]) -> HubSettings:
    defaults = HubSettings()
    values = asdict(defaults)
    for key in values:
        if key in data:
            values[key] = data[key]
    return HubSettings(**values)


def offer_from_dict(data: dict[str, Any]) -> Offer:
    raw_copies = data.get("copies") if isinstance(data.get("copies"), list) else []
    legacy_audio_folder = str(data.get("audio_folder", ""))
    api_audio_folder = str(data.get("api_audio_folder") or legacy_audio_folder)
    return Offer(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        slug=str(data.get("slug", "")),
        takes_folder=str(data.get("takes_folder", "")),
        broll_path=str(data.get("broll_path", "")),
        audio_folder=api_audio_folder,
        api_audio_folder=api_audio_folder,
        manual_audio_inbox_folder=str(data.get("manual_audio_inbox_folder", "")),
        manual_audio_library_folder=str(data.get("manual_audio_library_folder", "")),
        output_folder=str(data.get("output_folder", "")),
        copies=[copy_from_dict(item) for item in raw_copies if isinstance(item, dict) and item.get("id")],
        background_music_mode=str(data.get("background_music_mode", "none")),
        background_music_track_path=str(data.get("background_music_track_path", "")),
        background_music_category=str(data.get("background_music_category", "")),
    )


def state_from_dict(data: dict[str, Any]) -> HubState:
    raw_settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    raw_copies = data.get("copies") if isinstance(data.get("copies"), list) else []
    settings = settings_from_dict(raw_settings)
    raw_offers = data.get("offers") if isinstance(data.get("offers"), list) else []
    offers = [offer_from_dict(item) for item in raw_offers if isinstance(item, dict) and item.get("id")]
    if not offers:
        legacy_offer = default_offer()
        legacy_offer.takes_folder = settings.takes_folder
        legacy_offer.broll_path = settings.broll_path
        legacy_offer.output_folder = settings.output_folder
        legacy_offer.audio_folder = settings.manual_audio_folder
        legacy_offer.api_audio_folder = settings.manual_audio_folder
        legacy_offer.copies = [copy_from_dict(item) for item in raw_copies if isinstance(item, dict) and item.get("id")]
        offers = [legacy_offer]
    active_offer_id = str(data.get("active_offer_id", ""))
    if active_offer_id not in {offer.id for offer in offers}:
        active_offer_id = offers[0].id
    return HubState(settings=settings, offers=offers, active_offer_id=active_offer_id)


def copy_to_dict(copy: CopyCard) -> dict[str, Any]:
    return asdict(copy)


def offer_to_dict(offer: Offer) -> dict[str, Any]:
    api_audio_folder = offer.api_audio_folder or offer.audio_folder
    return {
        "id": offer.id,
        "name": offer.name,
        "slug": offer.slug,
        "takes_folder": offer.takes_folder,
        "broll_path": offer.broll_path,
        "audio_folder": api_audio_folder,
        "api_audio_folder": api_audio_folder,
        "manual_audio_inbox_folder": offer.manual_audio_inbox_folder,
        "manual_audio_library_folder": offer.manual_audio_library_folder,
        "output_folder": offer.output_folder,
        "background_music_mode": offer.background_music_mode,
        "background_music_track_path": offer.background_music_track_path,
        "background_music_category": offer.background_music_category,
        "copies": [copy_to_dict(copy) for copy in offer.copies],
    }


def settings_to_dict(settings: HubSettings, include_secret: bool = True) -> dict[str, Any]:
    payload = asdict(settings)
    payload.pop("background_music_selected_path", None)
    payload.pop("background_music_render_nonce", None)
    payload.pop("background_music_mode", None)
    payload.pop("background_music_track_path", None)
    payload.pop("background_music_category", None)
    if not include_secret:
        payload["voice_api_key"] = ""
        payload["voice_api_configured"] = bool(settings.voice_api_key.strip())
        payload["assemblyai_api_key"] = ""
        payload["assemblyai_api_configured"] = bool(settings.assemblyai_api_key.strip())
    return payload


def state_to_dict(state: HubState, include_secret: bool = True) -> dict[str, Any]:
    return {
        "settings": settings_to_dict(state.settings, include_secret=include_secret),
        "offers": [offer_to_dict(offer) for offer in state.offers],
        "active_offer_id": state.active_offer.id,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
