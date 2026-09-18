from __future__ import annotations

import json
import mimetypes
import os
import threading
import traceback
import webbrowser
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from caption_batch import caption_folder
from creative_engine import AudioEditSettings, process_creative_batch, split_keyword_variants, transcribe_audio_preview
from modern_folder_picker import pick_folder
from silence_engine import WhisperSpeechDetector, build_clip_plans, process_folder
from subtitles import SubtitleSettings


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
DEFAULT_INPUT = Path(r"C:\Users\PCGamerInfor\Documents\Appyon\2. KellyNash\13.09\video01")
PORT = 8091

job_lock = threading.Lock()
job_state = {
    "running": False,
    "status": "Pronto",
    "progress": 0,
    "result": None,
    "error": None,
}


def _json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _clean_path(value: str | Path | None, fallback: Path) -> Path:
    if value is None or str(value).strip() == "":
        return fallback
    cleaned = str(value).strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return Path(cleaned)


def _clean_optional_path(value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return _clean_path(value, Path())


def _select_windows_folder(
    initial_path: str | Path | None = None,
    askdirectory_func=None,
) -> Path | None:
    initial_dir = _initial_picker_dir(initial_path)
    if askdirectory_func is None:
        selected = pick_folder(initial_dir)
    else:
        selected = askdirectory_func(title="Selecionar pasta", initialdir=str(initial_dir), mustexist=False)
    if not selected:
        return None
    return _clean_path(selected, Path.home())


def _initial_picker_dir(value: str | Path | None) -> Path:
    if value is None or str(value).strip() == "":
        return Path.home()
    path = _clean_path(value, Path.home())
    if path.is_file():
        return path.parent
    if path.exists() and path.is_dir():
        return path
    parent = path.parent
    return parent if parent.exists() else Path.home()


def _bool_value(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sim", "yes", "on"}
    return bool(value)


def _video_url(path: str | Path) -> str:
    return f"/api/video?path={quote(str(path), safe='')}"


def _request_path(raw_path: str) -> str:
    path = urlparse(raw_path).path.rstrip("/")
    return path or "/"


def _settings(payload: dict) -> dict:
    return {
        "input_folder": _clean_path(payload.get("input_folder"), DEFAULT_INPUT),
        "output_folder": _clean_path(payload.get("output_folder"), OUTPUT_DIR),
        "threshold_db": int(payload.get("threshold_db", -30)),
        "silence_duration": float(payload.get("silence_duration", 0.15)),
        "start_padding": float(payload.get("start_padding", 0.15)),
        "end_padding": float(payload.get("end_padding", 0.55)),
        "detection_mode": payload.get("detection_mode", "speech"),
        "subtitle_mode": payload.get("subtitle_mode", "none"),
        "subtitle_x_position": float(payload.get("subtitle_x_position", 0.5)),
        "subtitle_y_position": float(payload.get("subtitle_y_position", 0.66)),
        "subtitle_font_size": int(payload.get("subtitle_font_size", 24)),
        "subtitle_words_per_line": int(payload.get("subtitle_words_per_line", 3)),
        "subtitle_force_caps": bool(payload.get("subtitle_force_caps", True)),
    }


def _subtitle_settings(settings: dict) -> SubtitleSettings:
    return SubtitleSettings(
        mode=settings.get("subtitle_mode", "normal"),
        x_position=float(settings.get("subtitle_x_position", 0.5)),
        y_position=float(settings.get("subtitle_y_position", 0.66)),
        font_size=int(settings.get("subtitle_font_size", 24)),
        max_words_per_line=int(settings.get("subtitle_words_per_line", 3)),
        force_all_caps=bool(settings.get("subtitle_force_caps", True)),
    )


def _creative_settings(payload: dict) -> dict:
    return {
        "audio_folder": _clean_path(payload.get("creative_audio_folder"), DEFAULT_INPUT),
        "takes_folder": _clean_path(payload.get("input_folder"), DEFAULT_INPUT),
        "output_folder": _clean_path(payload.get("output_folder"), OUTPUT_DIR),
        "broll_path": _clean_optional_path(payload.get("creative_broll_path")),
        "keyword_variants": split_keyword_variants(payload.get("creative_keywords", "")),
        "segment_duration": float(payload.get("creative_segment_duration", 3.0)),
        "audio_edit_settings": AudioEditSettings(
            trim_edges=_bool_value(payload.get("creative_trim_audio_edges"), False),
            cut_internal_silence=_bool_value(payload.get("creative_cut_internal_silence"), False),
            silence_threshold_db=int(payload.get("creative_silence_threshold_db", -35)),
            min_silence_duration=float(payload.get("creative_min_silence_duration", 0.4)),
            keep_silence=float(payload.get("creative_keep_silence", 0.18)),
        ),
        "background_speed": max(0.1, float(payload.get("creative_background_speed", 1.0))),
        "speed_broll": _bool_value(payload.get("creative_speed_broll"), False),
    }


def _summary_from_plans(plans) -> dict:
    original = round(sum(item.original_duration for item in plans), 3)
    final = round(sum(item.kept_duration for item in plans), 3)
    return {
        "clips": [asdict(item) for item in plans],
        "original_duration": original,
        "final_duration": final,
        "removed_duration": round(original - final, 3),
    }


def _analysis_settings(settings: dict) -> dict:
    analysis = {
        "folder": settings["input_folder"],
        "threshold_db": settings["threshold_db"],
        "silence_duration": settings["silence_duration"],
        "start_padding": settings["start_padding"],
        "end_padding": settings["end_padding"],
        "detection_mode": settings["detection_mode"],
    }
    if settings["detection_mode"] == "speech":
        analysis["speech_detector"] = WhisperSpeechDetector()
    return analysis


def _run_job(settings: dict) -> None:
    with job_lock:
        job_state.update(
            {
                "running": True,
                "status": "Analisando silêncios dos takes...",
                "progress": 15,
                "result": None,
                "error": None,
            }
        )

    try:
        result = process_folder(**settings)
        payload = asdict(result)
        payload["kind"] = "merge"
        payload["video_url"] = _video_url(result.output_path)
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Vídeo finalizado",
                    "progress": 100,
                    "result": payload,
                    "error": None,
                }
            )
    except Exception as exc:
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Erro no processamento",
                    "progress": 0,
                    "result": None,
                    "error": f"{exc}\n{traceback.format_exc()}",
                }
            )


def _run_caption_batch_job(settings: dict) -> None:
    def update_progress(done: int, total: int, name: str) -> None:
        progress = 5 + round((done / max(1, total)) * 90)
        with job_lock:
            job_state.update(
                {
                    "status": f"Legendando {done}/{total}: {name}",
                    "progress": min(progress, 95),
                }
            )

    with job_lock:
        job_state.update(
            {
                "running": True,
                "status": "Preparando lote de legendas...",
                "progress": 5,
                "result": None,
                "error": None,
            }
        )

    try:
        result = caption_folder(
            input_folder=settings["input_folder"],
            output_folder=settings["output_folder"],
            subtitle_settings=_subtitle_settings(settings),
            speech_detector=WhisperSpeechDetector(),
            progress_callback=update_progress,
        )
        payload = asdict(result)
        for item in payload["items"]:
            if item["output_path"]:
                item["video_url"] = _video_url(item["output_path"])
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Lote de legendas finalizado",
                    "progress": 100,
                    "result": payload,
                    "error": None,
                }
            )
    except Exception as exc:
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Erro no lote de legendas",
                    "progress": 0,
                    "result": None,
                    "error": f"{exc}\n{traceback.format_exc()}",
                }
            )


def _run_creative_job(payload: dict, test_only: bool) -> None:
    settings = _settings(payload)
    creative_settings = _creative_settings(payload)

    def update_progress(done: int, total: int, name: str) -> None:
        progress = 5 + round((done / max(1, total)) * 90)
        with job_lock:
            job_state.update(
                {
                    "status": f"Renderizando criativo {done}/{total}: {name}",
                    "progress": min(progress, 95),
                }
            )

    with job_lock:
        job_state.update(
            {
                "running": True,
                "status": "Preparando criativos...",
                "progress": 5,
                "result": None,
                "error": None,
            }
        )

    try:
        result = process_creative_batch(
            audio_folder=creative_settings["audio_folder"],
            takes_folder=creative_settings["takes_folder"],
            output_folder=creative_settings["output_folder"],
            broll_path=creative_settings["broll_path"],
            keyword_variants=creative_settings["keyword_variants"],
            segment_duration=creative_settings["segment_duration"],
            subtitle_settings=_subtitle_settings(settings),
            speech_detector=WhisperSpeechDetector(),
            progress_callback=update_progress,
            limit=1 if test_only else None,
            audio_edit_settings=creative_settings["audio_edit_settings"],
            background_speed=creative_settings["background_speed"],
            speed_broll=creative_settings["speed_broll"],
        )
        payload_result = asdict(result)
        for item in payload_result["items"]:
            if item["output_path"]:
                item["video_url"] = _video_url(item["output_path"])
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Criativos finalizados" if not test_only else "Teste finalizado",
                    "progress": 100,
                    "result": payload_result,
                    "error": None,
                }
            )
    except Exception as exc:
        with job_lock:
            job_state.update(
                {
                    "running": False,
                    "status": "Erro nos criativos",
                    "progress": 0,
                    "result": None,
                    "error": f"{exc}\n{traceback.format_exc()}",
                }
            )


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(_request_path(self.path))
        if path == "/api/defaults":
            _json_response(
                self,
                {
                    "input_folder": str(DEFAULT_INPUT),
                    "output_folder": str(OUTPUT_DIR),
                    "threshold_db": -30,
                    "silence_duration": 0.15,
                    "start_padding": 0.15,
                    "end_padding": 0.55,
                    "detection_mode": "speech",
                    "subtitle_mode": "none",
                    "subtitle_x_position": 0.5,
                    "subtitle_y_position": 0.66,
                    "subtitle_font_size": 24,
                    "subtitle_words_per_line": 3,
                    "subtitle_force_caps": True,
                    "creative_audio_folder": "",
                    "creative_broll_path": "",
                    "creative_keywords": "",
                    "creative_segment_duration": 3.0,
                    "creative_trim_audio_edges": True,
                    "creative_cut_internal_silence": False,
                    "creative_silence_threshold_db": -35,
                    "creative_min_silence_duration": 0.4,
                    "creative_keep_silence": 0.18,
                    "creative_background_speed": 1.0,
                    "creative_speed_broll": False,
                },
            )
            return
        if path == "/api/job":
            with job_lock:
                _json_response(self, dict(job_state))
            return
        if path.startswith("/output/"):
            self._serve_output(path.removeprefix("/output/"))
            return
        if path == "/api/video":
            query = parse_qs(parsed.query)
            requested = Path(query.get("path", [""])[0])
            self._send_file(requested)
            return
        self._serve_web(path)

    def do_POST(self) -> None:
        try:
            path = _request_path(self.path)
            payload = _read_json(self)
            if path == "/api/select-folder":
                selected = _select_windows_folder(payload.get("current_path", ""))
                _json_response(self, {"ok": True, "path": str(selected) if selected else "", "cancelled": selected is None})
                return
            settings = _settings(payload)
            if path == "/api/analyze":
                plans = build_clip_plans(**_analysis_settings(settings))
                _json_response(self, _summary_from_plans(plans))
                return
            if path == "/api/process":
                with job_lock:
                    if job_state["running"]:
                        _json_response(self, {"ok": False, "error": "Já tem um processamento rodando."}, 409)
                        return
                    job_state.update({"running": True, "status": "Entrando na fila...", "progress": 5})
                thread = threading.Thread(target=_run_job, args=(settings,), daemon=True)
                thread.start()
                _json_response(self, {"ok": True})
                return
            if path == "/api/caption-batch":
                with job_lock:
                    if job_state["running"]:
                        _json_response(self, {"ok": False, "error": "Já tem um processamento rodando."}, 409)
                        return
                    job_state.update({"running": True, "status": "Entrando na fila...", "progress": 5})
                thread = threading.Thread(target=_run_caption_batch_job, args=(settings,), daemon=True)
                thread.start()
                _json_response(self, {"ok": True})
                return
            if path == "/api/creative-transcribe":
                preview = transcribe_audio_preview(
                    _creative_settings(payload)["audio_folder"],
                    WhisperSpeechDetector(),
                )
                _json_response(self, asdict(preview))
                return
            if path in {"/api/creative-test", "/api/creative-batch"}:
                with job_lock:
                    if job_state["running"]:
                        _json_response(self, {"ok": False, "error": "Já tem um processamento rodando."}, 409)
                        return
                    job_state.update({"running": True, "status": "Entrando na fila...", "progress": 5})
                thread = threading.Thread(
                    target=_run_creative_job,
                    args=(payload, path == "/api/creative-test"),
                    daemon=True,
                )
                thread.start()
                _json_response(self, {"ok": True})
                return
            if path == "/api/open-output":
                settings["output_folder"].mkdir(parents=True, exist_ok=True)
                os.startfile(str(settings["output_folder"]))
                _json_response(self, {"ok": True})
                return
            if path == "/api/open-video":
                video_path = Path(payload.get("video_path", ""))
                if not video_path.exists() or not video_path.is_file():
                    _json_response(self, {"error": "Vídeo não encontrado."}, 404)
                    return
                os.startfile(str(video_path))
                _json_response(self, {"ok": True})
                return
            _json_response(self, {"error": "Rota não encontrada."}, 404)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, 500)

    def _serve_web(self, path: str) -> None:
        if path in {"", "/"}:
            target = WEB_DIR / "index.html"
        else:
            target = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR not in target.parents and target != WEB_DIR / "index.html":
            self.send_error(403)
            return
        self._send_file(target)

    def _serve_output(self, name: str) -> None:
        target = (OUTPUT_DIR / Path(name).name).resolve()
        if OUTPUT_DIR not in target.parents:
            self.send_error(403)
            return
        self._send_file(target)

    def _send_file(self, target: Path) -> None:
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Video Edit MVP rodando em {url}", flush=True)
    threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
