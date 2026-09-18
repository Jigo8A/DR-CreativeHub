from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from domain import Offer


def unique_offer_slug(name: str, existing_slugs: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "oferta"
    candidate = base
    suffix = 2
    while candidate in existing_slugs:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def ensure_offer_directories(root: Path, offer: Offer) -> Offer:
    root = Path(root)
    # The configured central folder is the offers root itself.
    folder = root / offer.slug
    paths = {
        "takes_folder": folder / "takes",
        "broll_path": folder / "broll",
        "api_audio_folder": folder / "audios_api",
        "manual_audio_inbox_folder": folder / "audios_manuais" / "entrada",
        "manual_audio_library_folder": folder / "audios_manuais" / "biblioteca",
        "output_folder": folder / "output",
        "internal_folder": folder / ".creative_hub",
        "transcriptions_folder": folder / ".creative_hub" / "transcricoes",
        "jobs_folder": folder / ".creative_hub" / "jobs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    api_audio_folder = offer.api_audio_folder or offer.audio_folder or str(paths["api_audio_folder"])
    return replace(
        offer,
        takes_folder=offer.takes_folder or str(paths["takes_folder"]),
        broll_path=offer.broll_path or str(paths["broll_path"]),
        audio_folder=api_audio_folder,
        api_audio_folder=api_audio_folder,
        manual_audio_inbox_folder=offer.manual_audio_inbox_folder or str(paths["manual_audio_inbox_folder"]),
        manual_audio_library_folder=offer.manual_audio_library_folder or str(paths["manual_audio_library_folder"]),
        output_folder=offer.output_folder or str(paths["output_folder"]),
    )
