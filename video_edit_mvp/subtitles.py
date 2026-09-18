from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from silence_engine import ClipPlan, SpeechWord, resolve_ffmpeg


DEFAULT_FONT_DIR = Path(__file__).resolve().parent.parent / "creative_hub" / "assets" / "fonts"


@dataclass(frozen=True)
class SubtitleSettings:
    mode: str = "none"
    x_position: float = 0.5
    y_position: float = 0.66
    font_size: int = 24
    max_words_per_line: int = 3
    force_all_caps: bool = True
    font_name: str = "Uninsta Heavy"
    base_color: tuple[int, int, int] = (255, 255, 255)
    highlight_color: tuple[int, int, int] = (255, 239, 0)
    stroke_color: tuple[int, int, int] = (0, 0, 0)
    outline_size: int = 3


@dataclass(frozen=True)
class HeadlineSettings:
    enabled: bool = False
    text: str = ""
    duration: float = 3.0
    x_position: float = 0.5
    y_position: float = 0.2
    font_size: int = 48
    text_color: tuple[int, int, int] = (255, 255, 255)
    background_color: tuple[int, int, int] = (18, 24, 15)
    background_width: int = 560
    background_height: int = 150
    corner_radius: int = 24
    font_name: str = "Uninsta Heavy"
    outline_size: int = 0
    emoji_overlay_path: Path | None = None


@dataclass(frozen=True)
class SubtitleGroup:
    words: list[SpeechWord]
    start: float
    end: float


def group_words(words: list[SpeechWord], max_words: int = 3) -> list[SubtitleGroup]:
    groups: list[SubtitleGroup] = []
    i = 0
    limit = max(1, max_words)
    while i < len(words):
        window = words[i : i + limit]
        take = limit
        if any(len(word.text) > 12 for word in window):
            take = 1 if len(window[0].text) > 12 else min(2, limit)
        group = words[i : i + take]
        groups.append(SubtitleGroup(words=group, start=group[0].start, end=group[-1].end))
        i += take
    return groups


def timeline_words_from_plans(plans: Iterable[ClipPlan]) -> list[SpeechWord]:
    words: list[SpeechWord] = []
    offset = 0.0
    for plan in plans:
        for word in plan.words:
            if word.end <= plan.start or word.start >= plan.end:
                continue
            start = max(word.start, plan.start) - plan.start + offset
            end = min(word.end, plan.end) - plan.start + offset
            if end > start:
                words.append(SpeechWord(text=word.text, start=round(start, 3), end=round(end, 3)))
        offset += plan.kept_duration
    return words


def build_ass_text(
    words: list[SpeechWord],
    settings: SubtitleSettings,
    width: int = 720,
    height: int = 1280,
    headline: HeadlineSettings | None = None,
) -> str:
    x = round(width * _clamp(settings.x_position, 0.0, 1.0))
    y = round(height * _clamp(settings.y_position, 0.0, 1.0))
    header = _ass_header(settings, width, height, headline)
    events = _headline_events(headline, width, height)
    for group in group_words(words, settings.max_words_per_line):
        if settings.mode == "highlight":
            events.extend(_highlight_events(group, settings, x, y))
        else:
            line = _format_line(group.words, settings)
            events.append(_event(group.start, group.end, x, y, line))
    return header + "\n".join(events) + ("\n" if events else "")


def write_ass_file(
    path: Path,
    words: list[SpeechWord],
    settings: SubtitleSettings,
    width: int = 720,
    height: int = 1280,
    headline: HeadlineSettings | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass_text(words, settings, width, height, headline), encoding="utf-8")
    return path


def burn_subtitles(
    input_path: Path,
    subtitle_path: Path,
    output_path: Path,
    ffmpeg_path: Path | None = None,
    fonts_dir: Path = DEFAULT_FONT_DIR,
    headline_overlay_path: Path | None = None,
    headline_duration: float = 0.0,
) -> Path:
    ffmpeg = ffmpeg_path or resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_value = f"subtitles='{_escape_filter_path(subtitle_path)}'"
    if fonts_dir.exists():
        filter_value += f":fontsdir='{_escape_filter_path(fonts_dir)}'"
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(input_path),
    ]
    if headline_overlay_path:
        duration = max(0.1, float(headline_duration))
        overlay = _escape_filter_path(headline_overlay_path)
        command.extend(
            [
                "-filter_complex",
                f"[0:v]{filter_value}[captioned];movie='{overlay}',format=rgba[headline];[captioned][headline]overlay=0:0:eof_action=repeat:enable='between(t,0,{duration})'[video]",
                "-map",
                "[video]",
                "-map",
                "0:a?",
            ]
        )
    else:
        command.extend(["-vf", filter_value])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    subprocess.run(command, check=True)
    return output_path


def _highlight_events(group: SubtitleGroup, settings: SubtitleSettings, x: int, y: int) -> list[str]:
    events: list[str] = []
    cursor = group.start
    for index, word in enumerate(group.words):
        if word.start > cursor:
            events.append(_event(cursor, word.start, x, y, _format_line(group.words, settings, index)))
        events.append(_event(word.start, word.end, x, y, _format_line(group.words, settings, index)))
        cursor = word.end
    if cursor < group.end:
        events.append(_event(cursor, group.end, x, y, _format_line(group.words, settings, len(group.words) - 1)))
    return events


def _format_line(words: list[SpeechWord], settings: SubtitleSettings, active_index: int | None = None) -> str:
    parts = []
    for index, word in enumerate(words):
        text = _clean_text(word.text.upper() if settings.force_all_caps else word.text)
        if active_index == index:
            parts.append(rf"{{\c{_ass_color(settings.highlight_color)}&}}{text}{{\c{_ass_color(settings.base_color)}&}}")
        else:
            parts.append(text)
    return " ".join(parts)


def _event(start: float, end: float, x: int, y: int, text: str) -> str:
    return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{{\\an5\\pos({x},{y})}}{text}"


def _headline_events(settings: HeadlineSettings | None, width: int, height: int) -> list[str]:
    if not settings or not settings.enabled or not settings.text.strip() or settings.emoji_overlay_path:
        return []
    box_width = max(1, min(width, int(settings.background_width)))
    box_height = max(1, min(height, int(settings.background_height)))
    radius = max(0, min(int(settings.corner_radius), box_width // 2, box_height // 2))
    x = round(width * _clamp(settings.x_position, 0.0, 1.0))
    y = round(height * _clamp(settings.y_position, 0.0, 1.0))
    left = x - box_width // 2
    top = y - box_height // 2
    duration = max(0.1, float(settings.duration))
    text = _headline_text(settings.text)
    background = _headline_box_path(box_width, box_height, radius)
    color = _ass_color(settings.background_color)
    return [
        f"Dialogue: 5,{_ass_time(0)},{_ass_time(duration)},HeadlineBackground,,0,0,0,,{{\\an7\\pos({left},{top})\\p1\\1c{color}}}{background}",
        f"Dialogue: 6,{_ass_time(0)},{_ass_time(duration)},Headline,,0,0,0,,{{\\an5\\pos({x},{y})}}{text}",
    ]


def _headline_text(value: str) -> str:
    lines = [
        _clean_text(line).strip()
        for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    return r"\N".join(line for line in lines if line) or " "


def _headline_box_path(width: int, height: int, radius: int) -> str:
    if radius <= 0:
        return f"m 0 0 l {width} 0 l {width} {height} l 0 {height}"
    half = max(1, round(radius / 2))
    return (
        f"m {radius} 0 l {width - radius} 0 "
        f"b {width - half} 0 {width} {half} {width} {radius} "
        f"l {width} {height - radius} "
        f"b {width} {height - half} {width - half} {height} {width - radius} {height} "
        f"l {radius} {height} "
        f"b {half} {height} 0 {height - half} 0 {height - radius} "
        f"l 0 {radius} b 0 {half} {half} 0 {radius} 0"
    )


def _ass_header(settings: SubtitleSettings, width: int, height: int, headline: HeadlineSettings | None = None) -> str:
    styles = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                f"Style: Default,{settings.font_name},{settings.font_size},{_ass_color(settings.base_color)},"
                f"{_ass_color(settings.highlight_color)},{_ass_color(settings.stroke_color)},&H80000000,"
                f"1,0,0,0,100,100,0,0,1,{max(0, int(settings.outline_size))},0,5,40,40,30,1"
            ),
    ]
    if headline and headline.enabled and headline.text.strip() and not headline.emoji_overlay_path:
        styles.extend(
            [
                (
                    f"Style: Headline,{headline.font_name},{headline.font_size},{_ass_color(headline.text_color)},"
                    f"{_ass_color(headline.text_color)},&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{max(0, int(headline.outline_size))},0,5,0,0,0,1"
                ),
                "Style: HeadlineBackground,Arial,1,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
            ]
        )
    styles.extend(["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    return "\n".join(styles) + "\n"


def _ass_time(value: float) -> str:
    value = max(0.0, value)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    centiseconds = int(round((value - int(value)) * 100))
    if centiseconds == 100:
        seconds += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _ass_color(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    return f"&H00{blue:02X}{green:02X}{red:02X}"


def _clean_text(value: str) -> str:
    return value.replace("{", "").replace("}", "").replace("\\", "").strip()


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
