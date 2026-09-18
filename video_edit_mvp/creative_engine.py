from __future__ import annotations

import json
import math
import random
import re
import subprocess
from threading import Event, Lock
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from silence_engine import (
    VIDEO_EXTENSIONS,
    SpeechWord,
    WhisperSpeechDetector,
    natural_key,
    probe_duration,
    resolve_ffmpeg,
    resolve_ffprobe,
    sort_take_paths,
)
from subtitles import HeadlineSettings, SubtitleSettings, burn_subtitles, write_ass_file


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
HISTORY_FILE = ".creative_take_history.json"
_BACKGROUND_MUSIC_LOUDNESS_CACHE: dict[tuple[str, int, int], float] = {}
_BACKGROUND_MUSIC_LOUDNESS_LOCK = Lock()
_BACKGROUND_MUSIC_LOUDNESS_IN_FLIGHT: dict[tuple[str, int, int], Event] = {}


@dataclass(frozen=True)
class KeywordTrigger:
    word: str
    start: float
    end: float
    variant: str


@dataclass(frozen=True)
class TranscriptionPreview:
    audio_path: str
    text: str
    words_count: int
    words: list[dict[str, float | str]]


@dataclass(frozen=True)
class VisualSegment:
    source_path: str
    source_start: float
    output_duration: float
    playback_speed: float = 1.0


@dataclass(frozen=True)
class AudioSegment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class AudioEditSettings:
    trim_edges: bool = False
    cut_internal_silence: bool = False
    silence_threshold_db: int = -35
    min_silence_duration: float = 0.4
    keep_silence: float = 0.18

    @property
    def enabled(self) -> bool:
        return self.trim_edges or self.cut_internal_silence


@dataclass(frozen=True)
class PreparedCreativeAudio:
    source_path: Path
    effective_audio_path: Path
    audio_duration: float
    words: list[SpeechWord]
    timings: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CreativeRenderJob:
    audio_path: Path
    output_path: Path
    subtitle_path: Path | None
    words: list[SpeechWord]
    visual_plan: list[VisualSegment]
    audio_duration: float
    subtitle_settings: SubtitleSettings
    headline_settings: HeadlineSettings | None = None
    broll_path: Path | None = None
    broll_start: float | None = None
    broll_duration: float = 0.0
    broll_speed: float = 1.0
    background_music_path: Path | None = None
    background_music_offset_db: float = -18.0
    timings: dict[str, float] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class CreativeBatchItem:
    audio_path: str
    output_path: str | None
    subtitle_path: str | None
    status: str
    duration: float
    words_detected: int
    trigger_word: str | None
    trigger_time: float | None
    visual_segments: list[VisualSegment] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class CreativeBatchResult:
    kind: str
    report_path: str
    history_path: str
    items: list[CreativeBatchItem]
    total: int
    completed: int
    failed: int
    test_only: bool


DurationLookup = Callable[[Path], float]
RenderJobFunc = Callable[[CreativeRenderJob], Path]
ProgressCallback = Callable[[int, int, str], None]
WordLoader = Callable[[Path], list[SpeechWord]]
OutputPathsForAudio = Callable[[Path], tuple[Path, Path]]
SegmentValidator = Callable[[VisualSegment], bool]


def list_audio_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Pasta de audios nao encontrada: {folder}")
    files = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS]
    return sorted(files, key=lambda path: natural_key(path.name))


def list_bank_videos(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Pasta de takes nao encontrada: {folder}")
    videos = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        raise ValueError("Nenhum video encontrado no banco de takes.")
    return sort_take_paths(videos)


def split_keyword_variants(raw_value: str | Iterable[str]) -> list[str]:
    if isinstance(raw_value, str):
        parts = raw_value.replace("\n", ",").split(",")
    else:
        parts = list(raw_value)
    return [part.strip() for part in parts if part and part.strip()]


def find_keyword_trigger(words: list[SpeechWord], variants: Iterable[str]) -> KeywordTrigger | None:
    lookup = {_normalize_keyword(variant): variant for variant in variants if variant.strip()}
    if not lookup:
        return None
    for word in sorted(words, key=lambda item: item.start):
        normalized = _normalize_keyword(word.text)
        if normalized in lookup:
            return KeywordTrigger(word=word.text, start=word.start, end=word.end, variant=lookup[normalized])
    return None


def transcribe_audio_preview(audio_folder: Path, speech_detector: WhisperSpeechDetector | None = None) -> TranscriptionPreview:
    audios = list_audio_files(audio_folder)
    if not audios:
        raise ValueError("Nenhum audio encontrado nessa pasta.")
    detector = speech_detector or WhisperSpeechDetector()
    audio_path = audios[0]
    words = detector.detect_words(audio_path)
    return TranscriptionPreview(
        audio_path=str(audio_path),
        text=" ".join(word.text for word in words),
        words_count=len(words),
        words=[{"text": word.text, "start": word.start, "end": word.end} for word in words],
    )


def build_visual_plan(
    takes: list[Path],
    target_duration: float,
    segment_duration: float,
    duration_lookup: DurationLookup,
    rng: random.Random | None = None,
    used_ranges: set[str] | None = None,
    background_speed: float = 1.0,
    segment_validator: SegmentValidator | None = None,
) -> list[VisualSegment]:
    if target_duration <= 0:
        raise ValueError("Audio sem duracao valida.")
    if segment_duration <= 0:
        raise ValueError("Duracao dos cortes precisa ser maior que zero.")
    if not takes:
        raise ValueError("Nenhum take disponivel para montar o criativo.")

    randomizer = rng or random.Random()
    used = used_ranges if used_ranges is not None else set()
    count = max(1, math.ceil(target_duration / segment_duration))
    plan: list[VisualSegment] = []

    for index in range(count):
        remaining = target_duration - sum(item.output_duration for item in plan)
        output_duration = round(min(segment_duration, remaining), 3)
        candidates = takes
        if index == count - 1 and len(takes) > 1 and plan:
            different = [take for take in takes if str(take) != plan[0].source_path]
            if different:
                candidates = different
        try:
            segment = _choose_segment(
                candidates,
                output_duration,
                duration_lookup,
                randomizer,
                used,
                background_speed,
                segment_validator,
            )
        except ValueError:
            if candidates is takes:
                raise
            segment = _choose_segment(
                takes,
                output_duration,
                duration_lookup,
                randomizer,
                used,
                background_speed,
                segment_validator,
            )
        plan.append(segment)

    return plan


def calculate_audio_keep_segments(
    duration: float,
    silences: list[tuple[float, float]],
    settings: AudioEditSettings,
) -> list[AudioSegment]:
    if duration <= 0:
        return []

    active_start = 0.0
    active_end = duration
    sorted_silences = sorted((max(0.0, start), min(duration, end)) for start, end in silences if end > start)
    edge_tolerance = 0.08

    if settings.trim_edges and sorted_silences:
        first_start, first_end = sorted_silences[0]
        if first_start <= edge_tolerance:
            active_start = min(duration, first_end)
        last_start, last_end = sorted_silences[-1]
        if last_end >= duration - edge_tolerance:
            active_end = max(active_start, last_start)

    if active_end <= active_start:
        return [AudioSegment(0.0, duration)]

    if not settings.cut_internal_silence:
        return [AudioSegment(round(active_start, 3), round(active_end, 3))]

    segments: list[AudioSegment] = []
    cursor = active_start
    keep_each_side = max(0.0, settings.keep_silence) / 2

    for silence_start, silence_end in sorted_silences:
        start = max(silence_start, active_start)
        end = min(silence_end, active_end)
        silence_duration = end - start
        if start <= active_start + edge_tolerance or end >= active_end - edge_tolerance:
            continue
        if silence_duration < settings.min_silence_duration or silence_duration <= settings.keep_silence:
            continue

        left_end = min(end, start + keep_each_side)
        right_start = max(left_end, end - keep_each_side)
        if left_end > cursor:
            segments.append(AudioSegment(round(cursor, 3), round(left_end, 3)))
        cursor = right_start

    if active_end > cursor:
        segments.append(AudioSegment(round(cursor, 3), round(active_end, 3)))

    return [segment for segment in segments if segment.duration > 0.01]


def process_creative_batch(
    audio_folder: Path,
    takes_folder: Path,
    output_folder: Path,
    broll_path: Path | None,
    keyword_variants: list[str],
    segment_duration: float,
    subtitle_settings: SubtitleSettings,
    headline_settings: HeadlineSettings | None = None,
    speech_detector: WhisperSpeechDetector | None = None,
    duration_lookup: DurationLookup | None = None,
    render_job_func: RenderJobFunc | None = None,
    rng: random.Random | None = None,
    progress_callback: ProgressCallback | None = None,
    limit: int | None = None,
    audio_edit_settings: AudioEditSettings | None = None,
    background_speed: float = 1.0,
    speed_broll: bool = False,
    word_loader: WordLoader | None = None,
    output_paths_for_audio: OutputPathsForAudio | None = None,
    background_music_path: Path | None = None,
    background_music_offset_db: float = -18.0,
    prepared_audios: dict[str, PreparedCreativeAudio] | None = None,
) -> CreativeBatchResult:
    ffmpeg = resolve_ffmpeg()
    ffprobe = resolve_ffprobe(ffmpeg)
    get_duration = duration_lookup or (lambda path: probe_duration(path, ffprobe))
    renderer = render_job_func or render_creative_job
    detector = speech_detector or WhisperSpeechDetector()
    randomizer = rng or random.Random()
    output_folder.mkdir(parents=True, exist_ok=True)

    audios = list_audio_files(audio_folder)
    if limit is not None:
        audios = audios[:limit]
    if not audios:
        raise ValueError("Nenhum audio encontrado nessa pasta.")

    takes = list_bank_videos(takes_folder)
    broll = _resolve_broll_path(broll_path)
    history_path = output_folder / HISTORY_FILE
    used_ranges = _load_history(history_path)
    batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    items: list[CreativeBatchItem] = []
    for index, audio in enumerate(audios, start=1):
        prepared = (prepared_audios or {}).get(str(audio.resolve()))
        timings: dict[str, float] = dict(prepared.timings) if prepared else {}
        item_started = time.perf_counter()
        try:
            if prepared:
                effective_audio = prepared.effective_audio_path
                audio_duration = prepared.audio_duration
                words = prepared.words
                timings["prepared_transcription"] = 1.0
            else:
                prepared = prepare_creative_audio(
                    audio=audio,
                    output_folder=output_folder,
                    batch_stamp=batch_stamp,
                    audio_edit_settings=audio_edit_settings,
                    speech_detector=detector,
                    duration_lookup=get_duration,
                    word_loader=word_loader,
                    ffmpeg=ffmpeg,
                )
                effective_audio = prepared.effective_audio_path
                audio_duration = prepared.audio_duration
                words = prepared.words
                timings.update(prepared.timings)

            stage_started = time.perf_counter()
            trigger = find_keyword_trigger(words, keyword_variants)
            plan = build_visual_plan(
                takes=takes,
                target_duration=audio_duration,
                segment_duration=segment_duration,
                duration_lookup=get_duration,
                rng=randomizer,
                used_ranges=used_ranges,
                background_speed=background_speed,
                segment_validator=(
                    (lambda segment: _segment_can_be_decoded(segment, ffmpeg)) if render_job_func is None else None
                ),
            )
            timings["visual_plan"] = _elapsed(stage_started)
            if output_paths_for_audio:
                output_path, subtitle_path = output_paths_for_audio(audio)
            else:
                output_path = output_folder / f"{audio.stem}_creative_{batch_stamp}.mp4"
                subtitle_path = output_folder / f"{audio.stem}_creative_{batch_stamp}.ass"
            needs_ass = subtitle_settings.mode != "none" or _headline_is_enabled(headline_settings)
            job = CreativeRenderJob(
                audio_path=effective_audio,
                output_path=output_path,
                subtitle_path=subtitle_path if needs_ass else None,
                words=words,
                visual_plan=plan,
                audio_duration=audio_duration,
                subtitle_settings=subtitle_settings,
                headline_settings=headline_settings,
                broll_path=broll if trigger else None,
                broll_start=trigger.start if trigger else None,
                broll_duration=round(get_duration(broll), 3) if broll and trigger else 0.0,
                broll_speed=background_speed if speed_broll else 1.0,
                background_music_path=background_music_path,
                background_music_offset_db=background_music_offset_db,
                timings=timings,
            )
            stage_started = time.perf_counter()
            renderer(job)
            timings["render"] = _elapsed(stage_started)
            timings["total"] = _elapsed(item_started)
            item = CreativeBatchItem(
                audio_path=str(audio),
                output_path=str(output_path),
                subtitle_path=str(job.subtitle_path) if job.subtitle_path else None,
                status="completed",
                duration=audio_duration,
                words_detected=len(words),
                trigger_word=trigger.word if trigger else None,
                trigger_time=trigger.start if trigger else None,
                visual_segments=plan,
                timings=timings,
            )
        except Exception as exc:
            timings["total"] = _elapsed(item_started)
            item = CreativeBatchItem(
                audio_path=str(audio),
                output_path=None,
                subtitle_path=None,
                status="failed",
                duration=0.0,
                words_detected=0,
                trigger_word=None,
                trigger_time=None,
                timings=timings,
                error=str(exc),
            )
        items.append(item)
        if progress_callback:
            progress_callback(index, len(audios), audio.name)

    _save_history(history_path, used_ranges)
    completed = sum(1 for item in items if item.status == "completed")
    result = CreativeBatchResult(
        kind="creative_batch",
        report_path=str(output_folder / f"criativos_lote_{batch_stamp}.json"),
        history_path=str(history_path),
        items=items,
        total=len(items),
        completed=completed,
        failed=len(items) - completed,
        test_only=limit == 1,
    )
    Path(result.report_path).write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def prepare_creative_audio(
    *,
    audio: Path,
    output_folder: Path,
    batch_stamp: str,
    audio_edit_settings: AudioEditSettings | None,
    speech_detector: WhisperSpeechDetector,
    duration_lookup: DurationLookup | None = None,
    word_loader: WordLoader | None = None,
    ffmpeg: Path | None = None,
) -> PreparedCreativeAudio:
    ffmpeg_path = ffmpeg or resolve_ffmpeg()
    ffprobe = resolve_ffprobe(ffmpeg_path)
    get_duration = duration_lookup or (lambda path: probe_duration(path, ffprobe))
    timings: dict[str, float] = {}

    stage_started = time.perf_counter()
    effective_audio = _prepare_audio_for_creative(
        audio=audio,
        output_folder=output_folder,
        batch_stamp=batch_stamp,
        settings=audio_edit_settings,
        duration_lookup=get_duration,
        ffmpeg=ffmpeg_path,
    )
    timings["audio_prepare"] = _elapsed(stage_started)

    stage_started = time.perf_counter()
    audio_duration = round(get_duration(effective_audio), 3)
    timings["audio_probe"] = _elapsed(stage_started)

    stage_started = time.perf_counter()
    words = word_loader(effective_audio) if word_loader else speech_detector.detect_words(effective_audio)
    timings["transcription"] = _elapsed(stage_started)
    return PreparedCreativeAudio(
        source_path=audio,
        effective_audio_path=effective_audio,
        audio_duration=audio_duration,
        words=words,
        timings=timings,
    )


def render_creative_job(job: CreativeRenderJob) -> Path:
    ffmpeg = resolve_ffmpeg()
    temp_path = job.output_path.with_name(f"{job.output_path.stem}_base.mp4")
    render_started = time.perf_counter()
    stage_started = time.perf_counter()
    _render_base_video(job, temp_path, ffmpeg)
    job.timings["render_base"] = _elapsed(stage_started)
    if job.subtitle_path:
        stage_started = time.perf_counter()
        write_ass_file(job.subtitle_path, job.words, job.subtitle_settings, headline=job.headline_settings)
        burn_subtitles(
            temp_path,
            job.subtitle_path,
            job.output_path,
            ffmpeg_path=ffmpeg,
            headline_overlay_path=job.headline_settings.emoji_overlay_path if job.headline_settings else None,
            headline_duration=job.headline_settings.duration if job.headline_settings else 0.0,
        )
        job.timings["subtitle_and_headline"] = _elapsed(stage_started)
        temp_path.unlink(missing_ok=True)
    else:
        temp_path.replace(job.output_path)
    job.timings["render_total"] = _elapsed(render_started)
    return job.output_path


def _render_base_video(job: CreativeRenderJob, output_path: Path, ffmpeg: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    for index, segment in enumerate(job.visual_plan):
        playback_speed = max(0.1, segment.playback_speed)
        source_duration = round(segment.output_duration * playback_speed, 3)
        inputs.extend(["-i", segment.source_path])
        filters.append(
            f"[{index}:v]trim=start={segment.source_start}:duration={source_duration},"
            f"setpts=(PTS-STARTPTS)/{playback_speed},"
            "scale=720:1280:force_original_aspect_ratio=increase,"
            "crop=720:1280,setsar=1,fps=24,format=yuv420p"
            f"[v{index}]"
        )

    audio_index = len(job.visual_plan)
    inputs.extend(["-i", str(job.audio_path)])
    concat_inputs = "".join(f"[v{index}]" for index in range(len(job.visual_plan)))
    filters.append(f"{concat_inputs}concat=n={len(job.visual_plan)}:v=1:a=0[vbase]")
    final_video = "[vbase]"

    if job.broll_path and job.broll_start is not None:
        broll_index = audio_index + 1
        inputs.extend(["-i", str(job.broll_path)])
        broll_speed = max(0.1, job.broll_speed)
        broll_output_duration = max(0.1, min(job.broll_duration / broll_speed, job.audio_duration - job.broll_start))
        broll_source_duration = round(broll_output_duration * broll_speed, 3)
        filters.append(
            f"[{broll_index}:v]trim=duration={broll_source_duration},"
            f"setpts=(PTS-STARTPTS)/{broll_speed}+{job.broll_start}/TB,"
            "scale=720:1280:force_original_aspect_ratio=increase,"
            "crop=720:1280,setsar=1,fps=24,format=yuv420p[broll]"
        )
        filters.append(
            f"{final_video}[broll]overlay=0:0:enable='between(t,{job.broll_start},{job.broll_start + broll_output_duration})'[vout]"
        )
        final_video = "[vout]"

    final_audio = f"{audio_index}:a"
    if job.background_music_path:
        music_index = len(job.visual_plan) + 1 + (1 if job.broll_path and job.broll_start is not None else 0)
        inputs.extend(["-stream_loop", "-1", "-i", str(job.background_music_path)])
        stage_started = time.perf_counter()
        voice_lufs = measure_integrated_loudness(job.audio_path, ffmpeg)
        music_lufs, music_loudness_cache_hit = measure_cached_background_music_loudness(job.background_music_path, ffmpeg)
        gain_db = background_music_gain_db(voice_lufs, music_lufs, job.background_music_offset_db)
        job.timings["music_loudness"] = _elapsed(stage_started)
        job.timings["music_loudness_cached"] = 1.0 if music_loudness_cache_hit else 0.0
        filters.extend([
            f"[{audio_index}:a]aresample=async=1[voice]",
            f"[{music_index}:a]atrim=duration={job.audio_duration},asetpts=PTS-STARTPTS,volume={gain_db:.2f}dB[music]",
            "[voice][music]amix=inputs=2:duration=first:normalize=0[aout]",
        ])
        final_audio = "[aout]"

    command = [
        str(ffmpeg),
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        final_video,
        "-map",
        final_audio,
        "-t",
        str(job.audio_duration),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    stage_started = time.perf_counter()
    subprocess.run(command, check=True)
    job.timings["base_ffmpeg"] = _elapsed(stage_started)


def background_music_gain_db(voice_lufs: float, music_lufs: float, offset_db: float) -> float:
    return float(voice_lufs) + float(offset_db) - float(music_lufs)


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 4)


def measure_integrated_loudness(source: Path, ffmpeg: Path) -> float:
    command = [str(ffmpeg), "-v", "info", "-i", str(source), "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    match = re.search(r'\{\s*"input_i".*?\}', result.stderr, re.DOTALL)
    if not match:
        raise RuntimeError("Nao foi possivel medir o volume da musica.")
    value = json.loads(match.group(0)).get("input_i")
    return float(value)


def measure_cached_background_music_loudness(source: Path, ffmpeg: Path) -> tuple[float, bool]:
    """Reuse a music's LUFS value until its path, size, or modification time changes."""
    path = Path(source)
    try:
        stat = path.stat()
        resolved = str(path.resolve())
    except OSError:
        return measure_integrated_loudness(path, ffmpeg), False

    key = (resolved, stat.st_size, stat.st_mtime_ns)
    with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
        cached = _BACKGROUND_MUSIC_LOUDNESS_CACHE.get(key)
        pending = _BACKGROUND_MUSIC_LOUDNESS_IN_FLIGHT.get(key)
    if cached is not None:
        return cached, True
    if pending is not None:
        pending.wait()
        with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
            cached = _BACKGROUND_MUSIC_LOUDNESS_CACHE.get(key)
        if cached is not None:
            return cached, True

    with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
        pending = _BACKGROUND_MUSIC_LOUDNESS_IN_FLIGHT.get(key)
        if pending is None:
            pending = Event()
            _BACKGROUND_MUSIC_LOUDNESS_IN_FLIGHT[key] = pending
            should_measure = True
        else:
            should_measure = False
    if not should_measure:
        pending.wait()
        with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
            cached = _BACKGROUND_MUSIC_LOUDNESS_CACHE.get(key)
        if cached is not None:
            return cached, True
        return measure_cached_background_music_loudness(path, ffmpeg)

    try:
        measured = measure_integrated_loudness(path, ffmpeg)
        with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
            for stale_key in [item for item in _BACKGROUND_MUSIC_LOUDNESS_CACHE if item[0] == resolved and item != key]:
                del _BACKGROUND_MUSIC_LOUDNESS_CACHE[stale_key]
            _BACKGROUND_MUSIC_LOUDNESS_CACHE[key] = measured
        return measured, False
    finally:
        with _BACKGROUND_MUSIC_LOUDNESS_LOCK:
            completed = _BACKGROUND_MUSIC_LOUDNESS_IN_FLIGHT.pop(key, None)
        if completed is not None:
            completed.set()


def _choose_segment(
    candidates: list[Path],
    output_duration: float,
    duration_lookup: DurationLookup,
    rng: random.Random,
    used_ranges: set[str],
    playback_speed: float,
    segment_validator: SegmentValidator | None = None,
) -> VisualSegment:
    speed = max(0.1, playback_speed)
    for _attempt in range(40):
        source = rng.choice(candidates)
        source_span = output_duration * speed
        source_duration = duration_lookup(source)
        if source_duration + 0.01 < source_span:
            continue
        max_start = max(0.0, source_duration - source_span)
        start = round(rng.uniform(0.0, max_start), 2) if max_start else 0.0
        key = _history_key(source, start, source_span)
        if key in used_ranges:
            continue
        segment = VisualSegment(str(source), start, output_duration, speed)
        if segment_validator and not segment_validator(segment):
            continue
        used_ranges.add(key)
        return segment

    for source in candidates:
        source_span = output_duration * speed
        source_duration = duration_lookup(source)
        if source_duration + 0.01 < source_span:
            continue
        segment = VisualSegment(str(source), 0.0, output_duration, speed)
        if segment_validator and not segment_validator(segment):
            continue
        used_ranges.add(_history_key(source, 0.0, source_span))
        return segment

    raise ValueError("Nenhum trecho de video valido foi encontrado no banco de takes.")


def _segment_can_be_decoded(segment: VisualSegment, ffmpeg: Path) -> bool:
    source_duration = max(0.01, segment.output_duration * max(0.1, segment.playback_speed))
    command = [
        str(ffmpeg),
        "-v",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        "-ss",
        str(segment.source_start),
        "-i",
        segment.source_path,
        "-map",
        "0:v:0",
        "-t",
        str(source_duration),
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    timestamps = re.findall(r"out_time_us=(\d+)", result.stdout)
    if not timestamps:
        return False
    decoded_duration = int(timestamps[-1]) / 1_000_000
    return decoded_duration + 0.08 >= source_duration


def _prepare_audio_for_creative(
    audio: Path,
    output_folder: Path,
    batch_stamp: str,
    settings: AudioEditSettings | None,
    duration_lookup: DurationLookup,
    ffmpeg: Path,
) -> Path:
    if not settings or not settings.enabled:
        return audio

    duration = duration_lookup(audio)
    silences = detect_audio_silences(
        audio,
        duration=duration,
        ffmpeg=ffmpeg,
        threshold_db=settings.silence_threshold_db,
        min_silence_duration=settings.min_silence_duration,
    )
    segments = calculate_audio_keep_segments(duration, silences, settings)
    if not _audio_segments_changed(duration, segments):
        return audio

    temp_folder = output_folder / "_audio_temp"
    temp_folder.mkdir(parents=True, exist_ok=True)
    output_audio = temp_folder / f"{audio.stem}_editado_{batch_stamp}.m4a"
    _render_audio_segments(audio, output_audio, segments, ffmpeg)
    return output_audio


def detect_audio_silences(
    audio: Path,
    duration: float,
    ffmpeg: Path,
    threshold_db: int,
    min_silence_duration: float,
) -> list[tuple[float, float]]:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-i",
        str(audio),
        "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_silence_duration}",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", completed.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", completed.stderr)]
    silences: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration
        if end > start:
            silences.append((round(start, 3), round(min(duration, end), 3)))
    return silences


def _audio_segments_changed(duration: float, segments: list[AudioSegment]) -> bool:
    if len(segments) != 1:
        return bool(segments)
    segment = segments[0]
    return abs(segment.start) > 0.02 or abs(segment.end - duration) > 0.02


def _render_audio_segments(source: Path, output_audio: Path, segments: list[AudioSegment], ffmpeg: Path) -> None:
    filters = []
    concat_inputs = []
    for index, segment in enumerate(segments):
        filters.append(
            f"[0:a]atrim=start={segment.start}:end={segment.end},asetpts=PTS-STARTPTS[a{index}]"
        )
        concat_inputs.append(f"[a{index}]")
    filters.append(f"{''.join(concat_inputs)}concat=n={len(segments)}:v=0:a=1[aout]")
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[aout]",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(output_audio),
    ]
    subprocess.run(command, check=True)


def _resolve_broll_path(value: Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(value)
    if path.is_file():
        return path
    if path.is_dir():
        videos = list_bank_videos(path)
        return videos[0] if videos else None
    return None


def _headline_is_enabled(settings: HeadlineSettings | None) -> bool:
    return bool(settings and settings.enabled and settings.text.strip())


def _load_history(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        return {str(item) for item in data}
    return set()


def _save_history(path: Path, values: set[str]) -> None:
    path.write_text(json.dumps(sorted(values), ensure_ascii=False, indent=2), encoding="utf-8")


def _history_key(path: Path, start: float, duration: float) -> str:
    return f"{Path(path)}|{start:.2f}|{duration:.2f}"


def _normalize_keyword(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "".join(char for char in ascii_text.lower() if char.isalnum())
