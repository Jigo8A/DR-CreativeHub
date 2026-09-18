from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Literal

from artifacts import WINDOWS_COMPONENT_MAX_LENGTH, truncate_utf16
from domain import Offer


WINDOWS_RESERVED_COMPONENTS = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


@dataclass(frozen=True)
class BatchTarget:
    offer_id: str
    name: str
    output_folder: Path
    internal_folder: Path


def build_batch_targets(
    offers: list[Offer],
    mode: Literal["automatic", "custom"],
    names: dict[str, str],
    now: datetime,
) -> dict[str, BatchTarget]:
    if mode not in {"automatic", "custom"}:
        raise ValueError("Modo de lote invalido.")

    targets: dict[str, BatchTarget] = {}
    for offer in offers:
        output_root = _output_root(offer)
        name = _automatic_name(output_root, now) if mode == "automatic" else sanitize_batch_name(names.get(offer.id, ""))
        internal_folder = output_root.parent / ".creative_hub"
        target = BatchTarget(offer.id, name, output_root / name, internal_folder)
        targets[offer.id] = target

    _validate_targets(targets.values(), mode)
    for target in targets.values():
        target.output_folder.mkdir(parents=True, exist_ok=True)
        (target.internal_folder / "jobs" / target.name).mkdir(parents=True, exist_ok=True)
    return targets


def sanitize_batch_name(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value))
    sanitized = re.sub(r"\s+", " ", sanitized).strip().rstrip(". ")
    sanitized = truncate_utf16(sanitized, WINDOWS_COMPONENT_MAX_LENGTH).rstrip(". ")
    if not sanitized:
        raise ValueError("Informe um nome valido para o lote.")
    stem = sanitized.split(".", 1)[0].rstrip(" ").upper()
    if stem in WINDOWS_RESERVED_COMPONENTS:
        raise ValueError("O nome do lote usa um componente reservado do Windows.")
    return sanitized


def _output_root(offer: Offer) -> Path:
    value = str(offer.output_folder or "").strip()
    if not value:
        raise ValueError(f"A oferta {offer.name or offer.id} nao possui pasta de output.")
    return Path(value)


def _automatic_name(output_root: Path, now: datetime) -> str:
    largest = 0
    try:
        folders = list(output_root.iterdir())
    except FileNotFoundError:
        folders = ()
    for folder in folders:
        match = re.fullmatch(r"lote-(\d+)-.+", folder.name, flags=re.IGNORECASE)
        if folder.is_dir() and match:
            largest = max(largest, int(match.group(1)))
    return f"lote-{largest + 1:03d}-{now:%Y-%m-%d_%H%M}"


def _validate_targets(targets, mode: Literal["automatic", "custom"]) -> None:
    destinations: set[str] = set()
    for target in targets:
        key = str(target.output_folder.resolve()).casefold()
        if key in destinations:
            raise ValueError("Duas ofertas nao podem usar a mesma pasta de lote.")
        destinations.add(key)
        if mode == "custom" and target.output_folder.exists():
            raise ValueError(f"O lote personalizado {target.name} ja existe para esta oferta.")
