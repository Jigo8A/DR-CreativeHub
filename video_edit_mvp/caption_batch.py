from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from silence_engine import SpeechWord, WhisperSpeechDetector, list_video_files, resolve_ffmpeg
from subtitles import SubtitleSettings, burn_subtitles, write_ass_file


@dataclass(frozen=True)
class CaptionOutputPaths:
    output_path: Path
    subtitle_path: Path


@dataclass(frozen=True)
class CaptionBatchItem:
    source_path: str
    output_path: str | None
    subtitle_path: str | None
    status: str
    words_detected: int
    error: str | None = None


@dataclass(frozen=True)
class CaptionBatchResult:
    kind: str
    report_path: str
    items: list[CaptionBatchItem]
    total: int
    completed: int
    failed: int


BurnSubtitlesFunc = Callable[[Path, Path, Path], Path]
ProgressCallback = Callable[[int, int, str], None]


def caption_output_paths(video_path: Path, output_folder: Path) -> CaptionOutputPaths:
    stem = f"{video_path.stem}_legendado"
    return CaptionOutputPaths(
        output_path=output_folder / f"{stem}.mp4",
        subtitle_path=output_folder / f"{stem}.ass",
    )


def caption_single_video(
    video_path: Path,
    output_folder: Path,
    subtitle_settings: SubtitleSettings,
    speech_detector: WhisperSpeechDetector,
    burn_subtitles_func: BurnSubtitlesFunc | None = None,
) -> CaptionBatchItem:
    output_folder.mkdir(parents=True, exist_ok=True)
    paths = caption_output_paths(video_path, output_folder)
    words = speech_detector.detect_words(video_path)
    settings = subtitle_settings
    if settings.mode == "none":
        settings = SubtitleSettings(
            mode="normal",
            x_position=settings.x_position,
            y_position=settings.y_position,
            font_size=settings.font_size,
            max_words_per_line=settings.max_words_per_line,
            force_all_caps=settings.force_all_caps,
            font_name=settings.font_name,
            base_color=settings.base_color,
            highlight_color=settings.highlight_color,
            stroke_color=settings.stroke_color,
        )

    write_ass_file(paths.subtitle_path, words, settings)
    burn = burn_subtitles_func
    if burn is None:
        ffmpeg = resolve_ffmpeg()
        burn = lambda source, subtitle, output: burn_subtitles(source, subtitle, output, ffmpeg_path=ffmpeg)
    burn(video_path, paths.subtitle_path, paths.output_path)

    return CaptionBatchItem(
        source_path=str(video_path),
        output_path=str(paths.output_path),
        subtitle_path=str(paths.subtitle_path),
        status="completed",
        words_detected=len(words),
    )


def caption_folder(
    input_folder: Path,
    output_folder: Path,
    subtitle_settings: SubtitleSettings,
    speech_detector: WhisperSpeechDetector | None = None,
    burn_subtitles_func: BurnSubtitlesFunc | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CaptionBatchResult:
    videos = list_video_files(input_folder)
    detector = speech_detector or WhisperSpeechDetector()
    output_folder.mkdir(parents=True, exist_ok=True)

    items: list[CaptionBatchItem] = []
    total = len(videos)
    for index, video in enumerate(videos, start=1):
        try:
            item = caption_single_video(
                video_path=video,
                output_folder=output_folder,
                subtitle_settings=subtitle_settings,
                speech_detector=detector,
                burn_subtitles_func=burn_subtitles_func,
            )
        except Exception as exc:
            item = CaptionBatchItem(
                source_path=str(video),
                output_path=None,
                subtitle_path=None,
                status="failed",
                words_detected=0,
                error=str(exc),
            )
        items.append(item)
        if progress_callback is not None:
            progress_callback(index, total, video.name)

    completed = sum(1 for item in items if item.status == "completed")
    failed = total - completed
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_folder / f"legendas_lote_{stamp}.json"
    result = CaptionBatchResult(
        kind="caption_batch",
        report_path=str(report_path),
        items=items,
        total=total,
        completed=completed,
        failed=failed,
    )
    report_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
