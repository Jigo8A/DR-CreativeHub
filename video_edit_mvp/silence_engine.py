from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
DEFAULT_FFMPEG = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
DEFAULT_FFPROBE = Path(r"C:\ffmpeg\bin\ffprobe.exe")
DEFAULT_WHISPER_CACHE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "CreativeHub" / "models"


@dataclass(frozen=True)
class SilenceEvent:
    kind: str
    time: float


@dataclass(frozen=True)
class ActiveRange:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class SpeechWord:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class ClipPlan:
    path: str
    name: str
    original_duration: float
    start: float
    end: float
    kept_duration: float
    removed_duration: float
    detection_method: str = "volume"
    words_detected: int = 0
    words: list[SpeechWord] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessResult:
    output_path: str
    report_path: str
    subtitle_path: str | None
    clips: list[ClipPlan]
    original_duration: float
    final_duration: float
    removed_duration: float


def natural_key(text: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def take_number(path: Path) -> int | None:
    match = re.search(r"(?:^|[^a-z0-9])take[\s_-]*(\d+)(?:[^0-9]|$)", path.stem, re.IGNORECASE)
    return int(match.group(1)) if match else None


def sort_take_paths(paths: Iterable[Path]) -> list[Path]:
    return sorted(
        paths,
        key=lambda path: (
            take_number(path) is None,
            take_number(path) if take_number(path) is not None else natural_key(path.name),
        ),
    )


def parse_silencedetect_output(output: str) -> list[SilenceEvent]:
    events: list[SilenceEvent] = []
    for line in output.splitlines():
        start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start:
            events.append(SilenceEvent("start", float(start.group(1))))
        end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end:
            events.append(SilenceEvent("end", float(end.group(1))))
    return events


def _silence_intervals(duration: float, events: list[SilenceEvent]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    open_start: float | None = None
    for event in sorted(events, key=lambda item: item.time):
        if event.kind == "start":
            open_start = event.time
        elif event.kind == "end" and open_start is not None:
            intervals.append((open_start, min(duration, event.time)))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, duration))
    return intervals


def calculate_active_range(
    duration: float,
    events: list[SilenceEvent],
    start_padding: float = 0.15,
    end_padding: float = 0.10,
    edge_tolerance: float = 0.25,
    minimum_keep: float = 0.25,
) -> ActiveRange:
    intervals = _silence_intervals(duration, events)
    start = 0.0
    end = duration

    if intervals and intervals[0][0] <= edge_tolerance:
        start = max(0.0, intervals[0][1] - start_padding)

    if intervals and intervals[-1][1] >= duration - edge_tolerance:
        end = min(duration, intervals[-1][0] + end_padding)

    if end - start < minimum_keep:
        return ActiveRange(0.0, duration)

    return ActiveRange(round(start, 3), round(end, 3))


def calculate_speech_active_range(
    duration: float,
    words: list[SpeechWord],
    start_padding: float = 0.15,
    end_padding: float = 0.55,
    minimum_keep: float = 0.25,
) -> ActiveRange | None:
    valid_words = [word for word in words if 0 <= word.start < duration and 0 < word.end <= duration + 0.5]
    if not valid_words:
        return None

    first_word = min(valid_words, key=lambda word: word.start)
    last_word = max(valid_words, key=lambda word: word.end)
    start = max(0.0, first_word.start - start_padding)
    end = min(duration, last_word.end + end_padding)

    if end - start < minimum_keep:
        return None
    return ActiveRange(round(start, 3), round(end, 3))


class WhisperSpeechDetector:
    def __init__(
        self,
        model_name: str = "small",
        cache_dir: Path = DEFAULT_WHISPER_CACHE,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 12,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "O modo por fala precisa do pacote faster-whisper. Rode: python -m pip install faster-whisper"
            ) from exc

        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            download_root=str(self.cache_dir),
        )
        return self._model

    def detect_words(self, video_path: Path) -> list[SpeechWord]:
        model = self._load_model()
        segments, _info = model.transcribe(
            str(video_path),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250, "threshold": 0.5},
        )

        words: list[SpeechWord] = []
        for segment in segments:
            for word in segment.words or []:
                text = (word.word or "").strip()
                if text:
                    words.append(SpeechWord(text=text, start=float(word.start), end=float(word.end)))
        return words


def resolve_ffmpeg() -> Path:
    configured = os.environ.get("CREATIVE_HUB_FFMPEG") or os.environ.get("FFMPEG_PATH")
    candidates = [Path(configured)] if configured else []
    candidates.append(DEFAULT_FFMPEG)
    for candidate in candidates:
        if candidate.exists() and "fabrica de videos" not in str(candidate).lower().replace("fabricadevideos", "fabrica de videos"):
            return candidate
    return DEFAULT_FFMPEG


def resolve_ffprobe(ffmpeg_path: Path | None = None) -> Path:
    configured = os.environ.get("CREATIVE_HUB_FFPROBE") or os.environ.get("FFPROBE_PATH")
    candidates = [Path(configured)] if configured else []
    if ffmpeg_path and ffmpeg_path.name.lower() == "ffmpeg.exe":
        candidates.append(ffmpeg_path.with_name("ffprobe.exe"))
    candidates.append(DEFAULT_FFPROBE)
    for candidate in candidates:
        if candidate.exists() and "fabrica de videos" not in str(candidate).lower().replace("fabricadevideos", "fabrica de videos"):
            return candidate
    return DEFAULT_FFPROBE


def list_video_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Pasta nao encontrada: {folder}")
    return sort_take_paths(
        path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def probe_duration(path: Path, ffprobe_path: Path) -> float:
    result = subprocess.run(
        [str(ffprobe_path), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def detect_active_range(
    path: Path,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    threshold_db: int = -30,
    silence_duration: float = 0.15,
    start_padding: float = 0.15,
    end_padding: float = 0.10,
) -> tuple[float, list[SilenceEvent], ActiveRange]:
    duration = probe_duration(path, ffprobe_path)
    result = subprocess.run(
        [
            str(ffmpeg_path),
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={threshold_db}dB:d={silence_duration}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    events = parse_silencedetect_output(result.stderr)
    active = calculate_active_range(duration, events, start_padding, end_padding)
    return duration, events, active


def build_clip_plans(
    folder: Path,
    threshold_db: int = -30,
    silence_duration: float = 0.15,
    start_padding: float = 0.15,
    end_padding: float = 0.55,
    detection_mode: str = "speech",
    ffmpeg_path: Path | None = None,
    ffprobe_path: Path | None = None,
    speech_detector: WhisperSpeechDetector | None = None,
) -> list[ClipPlan]:
    ffmpeg = ffmpeg_path or resolve_ffmpeg()
    ffprobe = ffprobe_path or resolve_ffprobe(ffmpeg)
    detector = speech_detector
    plans: list[ClipPlan] = []
    for video in list_video_files(folder):
        duration = probe_duration(video, ffprobe)
        active: ActiveRange | None = None
        method = "volume"
        words_detected = 0

        if detector is not None:
            words = detector.detect_words(video)
            words_detected = len(words)
            if detection_mode == "speech":
                active = calculate_speech_active_range(duration, words, start_padding, end_padding)
            if active is not None and detection_mode == "speech":
                method = "speech"

        if active is None:
            _duration, _events, active = detect_active_range(
                video, ffmpeg, ffprobe, threshold_db, silence_duration, start_padding, min(end_padding, 0.10)
            )
        plans.append(
            ClipPlan(
                path=str(video),
                name=video.name,
                original_duration=round(duration, 3),
                start=active.start,
                end=active.end,
                kept_duration=round(active.duration, 3),
                removed_duration=round(max(0.0, duration - active.duration), 3),
                detection_method=method,
                words_detected=words_detected,
                words=words,
            )
        )
    if not plans:
        raise ValueError("Nenhum video encontrado nessa pasta.")
    return plans


def _escape_filter_path(value: str) -> str:
    return value.replace("\\", "/").replace(":", "\\:")


def render_from_plan(
    plans: list[ClipPlan],
    output_path: Path,
    ffmpeg_path: Path | None = None,
    width: int = 720,
    height: int = 1280,
    fps: int = 24,
    preset: str = "ultrafast",
    crf: int = 23,
) -> Path:
    if not plans:
        raise ValueError("Plano vazio: nada para renderizar.")

    ffmpeg = ffmpeg_path or resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    filters: list[str] = []
    for index, plan in enumerate(plans):
        inputs.extend(["-i", plan.path])
        filters.append(
            f"[{index}:v]trim=start={plan.start}:end={plan.end},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{index}]"
        )
        filters.append(
            f"[{index}:a]atrim=start={plan.start}:end={plan.end},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates=44100:channel_layouts=stereo[a{index}]"
        )

    concat_inputs = "".join(f"[v{index}][a{index}]" for index in range(len(plans)))
    filters.append(f"{concat_inputs}concat=n={len(plans)}:v=1:a=1[vout][aout]")

    command = [
        str(ffmpeg),
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def process_folder(
    input_folder: Path,
    output_folder: Path,
    threshold_db: int = -30,
    silence_duration: float = 0.15,
    start_padding: float = 0.15,
    end_padding: float = 0.55,
    detection_mode: str = "speech",
    subtitle_mode: str = "none",
    subtitle_x_position: float = 0.5,
    subtitle_y_position: float = 0.66,
    subtitle_font_size: int = 24,
    subtitle_words_per_line: int = 3,
    subtitle_force_caps: bool = True,
) -> ProcessResult:
    from subtitles import SubtitleSettings, burn_subtitles, timeline_words_from_plans, write_ass_file

    ffmpeg = resolve_ffmpeg()
    ffprobe = resolve_ffprobe(ffmpeg)
    needs_words = detection_mode == "speech" or subtitle_mode != "none"
    plans = build_clip_plans(
        input_folder,
        threshold_db=threshold_db,
        silence_duration=silence_duration,
        start_padding=start_padding,
        end_padding=end_padding,
        detection_mode=detection_mode,
        speech_detector=WhisperSpeechDetector() if needs_words else None,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder.mkdir(parents=True, exist_ok=True)
    output_path = output_folder / f"video_edit_mvp_{stamp}.mp4"
    report_path = output_folder / f"video_edit_mvp_{stamp}.json"
    subtitle_path: Path | None = None

    if subtitle_mode != "none":
        temp_dir = Path(__file__).resolve().parent / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_video_path = temp_dir / f"video_edit_mvp_{stamp}_base.mp4"
        render_from_plan(plans, temp_video_path, ffmpeg_path=ffmpeg)
        subtitle_path = output_folder / f"video_edit_mvp_{stamp}.ass"
        subtitle_settings = SubtitleSettings(
            mode=subtitle_mode,
            x_position=subtitle_x_position,
            y_position=subtitle_y_position,
            font_size=subtitle_font_size,
            max_words_per_line=subtitle_words_per_line,
            force_all_caps=subtitle_force_caps,
        )
        write_ass_file(subtitle_path, timeline_words_from_plans(plans), subtitle_settings)
        burn_subtitles(temp_video_path, subtitle_path, output_path, ffmpeg_path=ffmpeg)
        temp_video_path.unlink(missing_ok=True)
    else:
        render_from_plan(plans, output_path, ffmpeg_path=ffmpeg)

    original_duration = round(sum(item.original_duration for item in plans), 3)
    final_duration = round(sum(item.kept_duration for item in plans), 3)
    result = ProcessResult(
        output_path=str(output_path),
        report_path=str(report_path),
        subtitle_path=str(subtitle_path) if subtitle_path else None,
        clips=plans,
        original_duration=original_duration,
        final_duration=final_duration,
        removed_duration=round(original_duration - final_duration, 3),
    )
    report_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
