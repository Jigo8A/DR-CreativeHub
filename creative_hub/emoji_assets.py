from __future__ import annotations

from html import escape
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable, Mapping

_EMOJI_RANGES = (
    (0x00A9, 0x00AE),
    (0x203C, 0x3299),
    (0x1F000, 0x1FAFF),
)
_VARIATION_SELECTOR = 0xFE0F
_ZERO_WIDTH_JOINER = 0x200D
_SKIN_TONE_RANGE = (0x1F3FB, 0x1F3FF)

EmojiRasterizer = Callable[[str, int, int, Path], None]
HeadlineOverlayRenderer = Callable[[dict[str, object], Path], None]


def extract_emoji_clusters(text: str) -> list[str]:
    """Return complete emoji sequences while leaving ordinary headline text alone."""
    clusters: list[str] = []
    index = 0
    while index < len(text):
        if not _is_emoji(text[index]):
            index += 1
            continue
        end = _emoji_cluster_end(text, index)
        clusters.append(text[index:end])
        index = end
    return clusters


def headline_requires_raster_overlay(text: str) -> bool:
    return bool(extract_emoji_clusters(text))


def headline_content_html(text: str) -> str:
    """Escape headline text while forcing each emoji sequence into the Apple font."""
    parts: list[str] = []
    index = 0
    while index < len(text):
        if _is_emoji(text[index]):
            end = _emoji_cluster_end(text, index)
            parts.append(f'<span class="apple-emoji">{escape(text[index:end])}</span>')
            index = end
            continue
        parts.append("<br>" if text[index] == "\n" else escape(text[index]))
        index += 1
    return "".join(parts)


def prepare_headline_emoji_overlay(
    settings: Mapping[str, object],
    cache_directory: Path,
    emoji_font_path: Path,
    browser_path: Path | None = None,
) -> Path | None:
    """Create a transparent full-headline overlay only when emoji are present."""
    style = _headline_style(settings)
    if not headline_requires_raster_overlay(style["text"]):
        return None
    cache = HeadlineOverlayCache(
        cache_directory,
        lambda values, destination: _render_headline_overlay(
            values,
            destination,
            emoji_font_path,
            browser_path,
        ),
    )
    return cache.overlay_for(style)


class EmojiSpriteCache:
    """Caches the transparent emoji images used by the video compositor."""

    def __init__(self, directory: Path, rasterize: EmojiRasterizer) -> None:
        self.directory = directory
        self.rasterize = rasterize

    def sprite_for(self, emoji: str, size: int, outline: int = 0) -> Path:
        identity = f"{emoji}|{int(size)}|{int(outline)}".encode("utf-8")
        destination = self.directory / f"{sha256(identity).hexdigest()}.png"
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.rasterize(emoji, int(size), int(outline), destination)
        return destination


class HeadlineOverlayCache:
    """Stores one rendered full-headline image per visual configuration."""

    def __init__(self, directory: Path, render: HeadlineOverlayRenderer) -> None:
        self.directory = directory
        self.render = render

    def overlay_for(self, settings: Mapping[str, object]) -> Path:
        values = dict(settings)
        identity = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        destination = self.directory / f"headline-{sha256(identity).hexdigest()}.png"
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.render(values, destination)
        return destination


def _is_emoji(value: str) -> bool:
    codepoint = ord(value)
    return any(start <= codepoint <= end for start, end in _EMOJI_RANGES)


def _is_emoji_modifier(value: str) -> bool:
    codepoint = ord(value)
    return codepoint == _VARIATION_SELECTOR or _SKIN_TONE_RANGE[0] <= codepoint <= _SKIN_TONE_RANGE[1]


def _emoji_cluster_end(text: str, index: int) -> int:
    end = index + 1
    while end < len(text) and _is_emoji_modifier(text[end]):
        end += 1
    while end + 1 < len(text) and ord(text[end]) == _ZERO_WIDTH_JOINER and _is_emoji(text[end + 1]):
        end += 2
        while end < len(text) and _is_emoji_modifier(text[end]):
            end += 1
    return end


def _headline_style(settings: Mapping[str, object]) -> dict[str, object]:
    return {
        "renderer": "apple-emoji-v2",
        "text": str(settings.get("text", settings.get("headline_text", ""))),
        "duration": float(settings.get("duration", settings.get("headline_duration", 3))),
        "x_position": float(settings.get("x_position", settings.get("headline_x_position", .5))),
        "y_position": float(settings.get("y_position", settings.get("headline_y_position", .2))),
        "font_size": int(settings.get("font_size", settings.get("headline_font_size", 48))),
        "font_name": str(settings.get("font_name", settings.get("headline_font_name", "Arial"))),
        "outline_size": int(settings.get("outline_size", settings.get("headline_outline_size", 0))),
        "text_color": _css_color(settings.get("text_color", settings.get("headline_text_color", "#FFFFFF"))),
        "background_color": _css_color(settings.get("background_color", settings.get("headline_background_color", "#12180F"))),
        "background_width": int(settings.get("background_width", settings.get("headline_background_width", 560))),
        "background_height": int(settings.get("background_height", settings.get("headline_background_height", 150))),
        "corner_radius": int(settings.get("corner_radius", settings.get("headline_corner_radius", 24))),
    }


def _render_headline_overlay(
    style: dict[str, object],
    destination: Path,
    emoji_font_path: Path,
    browser_path: Path | None,
) -> None:
    if not emoji_font_path.exists():
        raise FileNotFoundError("Fonte de emoji Apple nao encontrada nos assets do Creative Hub.")
    browser = browser_path or _find_chromium()
    if not browser:
        raise FileNotFoundError("Chrome ou Edge nao encontrado para renderizar emojis Apple.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    width = max(1, min(720, int(style["background_width"])))
    height = max(1, min(1280, int(style["background_height"])))
    left = round(720 * float(style["x_position"]) - width / 2)
    top = round(1280 * float(style["y_position"]) - height / 2)
    outline = max(0, int(style["outline_size"]))
    text_shadow = "none" if not outline else ",".join(
        f"{x}px {y}px 0 #000" for x, y in ((-outline, 0), (outline, 0), (0, -outline), (0, outline), (-outline, -outline), (outline, outline), (-outline, outline), (outline, -outline))
    )
    content = headline_content_html(str(style["text"]))
    html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><style>
@font-face {{ font-family: AppleColorEmoji; src: url('{emoji_font_path.resolve().as_uri()}'); }}
html,body {{ background: transparent; height: 1280px; margin: 0; overflow: hidden; width: 720px; }}
#headline {{ align-items: center; background: {style['background_color']}; border-radius: {max(0, int(style['corner_radius']))}px; box-sizing: border-box; color: {style['text_color']}; display: flex; font-family: '{escape(str(style['font_name']))}', AppleColorEmoji, sans-serif; font-size: {max(1, int(style['font_size']))}px; font-weight: 700; height: {height}px; justify-content: center; left: {left}px; line-height: 1.06; position: absolute; text-align: center; text-shadow: {text_shadow}; top: {top}px; white-space: pre-line; width: {width}px; }}
.apple-emoji {{ font-family: AppleColorEmoji !important; font-style: normal; font-weight: 400; text-shadow: none; }}
</style></head><body><div id=\"headline\">{content}</div></body></html>"""
    with TemporaryDirectory(prefix="creative_hub_emoji_") as directory:
        page = Path(directory) / "headline.html"
        page.write_text(html, encoding="utf-8")
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--default-background-color=00000000",
            "--window-size=720,1280",
            f"--screenshot={destination.resolve()}",
            page.resolve().as_uri(),
        ]
        subprocess.run(command, check=True, capture_output=True)
    if not destination.exists() or not destination.stat().st_size:
        raise RuntimeError("Nao foi possivel gerar a imagem da headline com emoji.")


def _css_color(value: object) -> str:
    if isinstance(value, str):
        return value if value.startswith("#") else f"#{value}"
    if isinstance(value, tuple) and len(value) == 3:
        return "#" + "".join(f"{max(0, min(255, int(channel))):02X}" for channel in value)
    return "#FFFFFF"


def _find_chromium() -> Path | None:
    candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)
