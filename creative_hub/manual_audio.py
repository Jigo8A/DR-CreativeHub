from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from domain import CopyCard, Offer


AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}


@dataclass
class ManualImportResult:
    imported: list[CopyCard] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    empty: bool = False


def import_manual_audio(offer: Offer, now: datetime) -> ManualImportResult:
    inbox = _required_directory(offer.manual_audio_inbox_folder, "entrada de audios manuais")
    library = _required_directory(offer.manual_audio_library_folder, "biblioteca de audios manuais")
    sources = sorted(
        (path for path in inbox.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES),
        key=lambda path: path.name.casefold(),
    )
    if not sources:
        return ManualImportResult(empty=True)

    archive_folder = library / now.strftime("%Y-%m-%d_%H%M")
    archived_paths = {
        _resolved_path(copy.audio_path)
        for copy in offer.copies
        if copy.audio_path
    }
    result = ManualImportResult()

    for source in sources:
        destination = archive_folder / source.name
        resolved_destination = destination.resolve()
        if resolved_destination in archived_paths:
            result.skipped.append(f"{source.name}: audio ja esta vinculado a uma copy.")
            continue
        if destination.exists():
            result.skipped.append(f"{source.name}: ja existe na biblioteca de audios.")
            continue

        try:
            archive_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        except (OSError, shutil.Error) as exc:
            _restore_source_after_failed_move(source, destination)
            result.skipped.append(f"{source.name}: {exc}")
            continue

        result.imported.append(
            CopyCard(
                id=uuid.uuid4().hex,
                title=source.stem,
                audio_source="manual",
                audio_path=str(destination),
                status="audio_ready",
            )
        )
        archived_paths.add(resolved_destination)

    return result


def rollback_manual_audio_import(offer: Offer, result: ManualImportResult) -> None:
    inbox = _required_directory(offer.manual_audio_inbox_folder, "entrada de audios manuais")
    library = _required_directory(offer.manual_audio_library_folder, "biblioteca de audios manuais")
    failures: list[str] = []

    for card in reversed(result.imported):
        archived = Path(card.audio_path or "")
        if not archived.is_file():
            continue
        source = inbox / archived.name
        if source.exists():
            failures.append(f"{archived.name}: ja existe um arquivo com este nome na entrada.")
            continue
        try:
            shutil.move(str(archived), str(source))
            _remove_empty_archive_parents(archived.parent, library)
        except (OSError, shutil.Error) as exc:
            failures.append(f"{archived.name}: {exc}")

    if failures:
        raise RuntimeError("Nao foi possivel reverter a importacao manual: " + " ".join(failures))


def _required_directory(value: str, label: str) -> Path:
    path = Path(str(value).strip().strip('"')) if str(value).strip() else None
    if path is None or not path.is_dir():
        raise ValueError(f"Defina uma pasta valida para {label}.")
    return path


def _resolved_path(value: str | None) -> Path:
    return Path(str(value)).expanduser().resolve()


def _restore_source_after_failed_move(source: Path, destination: Path) -> None:
    if source.exists() or not destination.exists():
        return
    try:
        shutil.move(str(destination), str(source))
    except (OSError, shutil.Error):
        pass


def _remove_empty_archive_parents(folder: Path, library: Path) -> None:
    current = folder
    while current != library and current.is_dir():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
