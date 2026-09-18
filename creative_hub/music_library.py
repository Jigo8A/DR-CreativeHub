from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path


AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".mp4"}
MUSIC_ROOT = Path(__file__).resolve().parent / "assets" / "musicas"


@dataclass(frozen=True)
class MusicTrack:
    category: str
    path: Path


@dataclass(frozen=True)
class ResolvedBackgroundMusic:
    mode: str
    path: Path | None
    category: str = ""
    nonce: str = ""


def scan_music_library(root: Path = MUSIC_ROOT) -> dict[str, list[MusicTrack]]:
    if not root.is_dir():
        return {}
    library: dict[str, list[MusicTrack]] = {}
    for category_folder in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
        tracks = [
            MusicTrack(category_folder.name, path)
            for path in sorted(category_folder.iterdir(), key=lambda item: item.name.lower())
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
        ]
        library[category_folder.name] = tracks
    return library


def resolve_background_music(
    mode: str,
    track_path: str,
    category: str,
    library: dict[str, list[MusicTrack]],
    rng: random.Random,
    *,
    nonce: str = "",
) -> ResolvedBackgroundMusic:
    normalized_mode = str(mode or "none").strip().lower()
    if normalized_mode == "none":
        return ResolvedBackgroundMusic(mode="none", path=None)
    if normalized_mode == "track":
        path = Path(str(track_path or "").strip().strip('"'))
        if not path.is_file():
            raise ValueError("A faixa de musica selecionada nao foi encontrada.")
        return ResolvedBackgroundMusic(mode="track", path=path)
    if normalized_mode == "category":
        tracks = library.get(str(category or "").strip(), [])
        if not tracks:
            raise ValueError("Categoria de musica sem faixas disponiveis.")
        track = rng.choice(tracks)
        return ResolvedBackgroundMusic(mode="category", path=track.path, category=track.category, nonce=nonce)
    raise ValueError("Selecione um modo de musica valido.")
