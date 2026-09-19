from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from voice_provider import HttpRequest, HttpResponse, Transport


ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
ASSEMBLYAI_SYNC_URL = "https://sync.assemblyai.com/v1/transcribe"
UNIVERSAL_35_PRO = "universal-3-5-pro"
SYNC_AUDIO_LIMIT_SECONDS = 120


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float


class SyncTranscriptionUnavailable(RuntimeError):
    """Signals that the short-audio endpoint should fall back to async."""


class AssemblyAISpeechDetector:
    def __init__(
        self,
        api_key: str,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 300,
        sync_audio_preparer: Callable[[Path, Path], bool] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.transport = transport or _urllib_transport
        self.sleep = sleep
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts
        self.sync_audio_preparer = sync_audio_preparer or _prepare_sync_wav

    def detect_words(self, audio_path: Path) -> list[TimedWord]:
        if not self.api_key:
            raise RuntimeError("Informe a chave da API AssemblyAI nas configuracoes de transcricao.")
        path = Path(audio_path)
        if not path.is_file():
            raise RuntimeError("O audio para transcricao nao foi encontrado.")
        try:
            return self._detect_words_sync(path)
        except SyncTranscriptionUnavailable:
            pass
        upload_url = self._upload(path)
        transcript_id = self._create_transcript(upload_url)
        return self._wait_for_words(transcript_id)

    def _detect_words_sync(self, audio_path: Path) -> list[TimedWord]:
        with TemporaryDirectory(prefix="creative-hub-sync-") as temporary:
            prepared_path = Path(temporary) / "audio.wav"
            if not self.sync_audio_preparer(audio_path, prepared_path):
                raise SyncTranscriptionUnavailable("Nao foi possivel preparar o audio para a Sync API.")
            if not prepared_path.is_file() or not prepared_path.stat().st_size:
                raise SyncTranscriptionUnavailable("O audio preparado para a Sync API esta vazio.")
            if _wav_duration_seconds(prepared_path) > SYNC_AUDIO_LIMIT_SECONDS:
                raise SyncTranscriptionUnavailable("O audio excede o limite da Sync API.")
            response = self.transport(_sync_request(prepared_path, self.api_key))
        data = _json_body(response, "transcrever o audio rapidamente")
        if not 200 <= response.status < 300:
            raise SyncTranscriptionUnavailable(_error_message(data, f"A Sync API retornou HTTP {response.status}."))
        raw_words = data.get("words")
        words = _timed_words(raw_words)
        if not words:
            raise SyncTranscriptionUnavailable("A Sync API concluiu sem marcacoes por palavra.")
        if not isinstance(raw_words, list) or len(words) != len(raw_words):
            raise SyncTranscriptionUnavailable("A Sync API concluiu com marcacoes por palavra incompletas.")
        return words

    def _upload(self, audio_path: Path) -> str:
        content_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"
        response = self.transport(
            HttpRequest(
                "POST",
                f"{ASSEMBLYAI_BASE_URL}/upload",
                {"authorization": self.api_key, "content-type": content_type},
                audio_path.read_bytes(),
            )
        )
        data = _json_body(response, "enviar o audio")
        upload_url = str(data.get("upload_url") or "").strip()
        if not 200 <= response.status < 300 or not upload_url:
            raise RuntimeError(_error_message(data, f"A AssemblyAI nao recebeu o audio (HTTP {response.status})."))
        return upload_url

    def _create_transcript(self, upload_url: str) -> str:
        body = json.dumps(
            {
                "audio_url": upload_url,
                "speech_models": [UNIVERSAL_35_PRO],
                "language_detection": True,
            }
        ).encode("utf-8")
        response = self.transport(
            HttpRequest(
                "POST",
                f"{ASSEMBLYAI_BASE_URL}/transcript",
                {"authorization": self.api_key, "content-type": "application/json"},
                body,
            )
        )
        data = _json_body(response, "iniciar a transcricao")
        transcript_id = str(data.get("id") or "").strip()
        if not 200 <= response.status < 300 or not transcript_id:
            raise RuntimeError(_error_message(data, f"A AssemblyAI nao iniciou a transcricao (HTTP {response.status})."))
        return transcript_id

    def _wait_for_words(self, transcript_id: str) -> list[TimedWord]:
        for attempt in range(self.max_poll_attempts):
            response = self.transport(
                HttpRequest("GET", f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}", {"authorization": self.api_key})
            )
            data = _json_body(response, "consultar a transcricao")
            if not 200 <= response.status < 300:
                raise RuntimeError(_error_message(data, f"A AssemblyAI retornou HTTP {response.status} ao consultar a transcricao."))
            status = str(data.get("status") or "").lower()
            if status == "completed":
                words = _timed_words(data.get("words"))
                if not words:
                    raise RuntimeError("A AssemblyAI concluiu a transcricao sem marcacoes por palavra.")
                return words
            if status in {"error", "failed"}:
                raise RuntimeError(_error_message(data, "A AssemblyAI nao conseguiu transcrever este audio."))
            if attempt < self.max_poll_attempts - 1 and self.poll_interval:
                self.sleep(self.poll_interval)
        raise RuntimeError("A transcricao da AssemblyAI demorou mais que o tempo limite da Creative Hub.")


def _timed_words(value: object) -> list[TimedWord]:
    if not isinstance(value, list):
        return []
    words: list[TimedWord] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        try:
            start = float(item["start"]) / 1000
            end = float(item["end"]) / 1000
        except (KeyError, TypeError, ValueError):
            continue
        if text and end > start >= 0:
            words.append(TimedWord(text=text, start=round(start, 3), end=round(end, 3)))
    return words


def _json_body(response: HttpResponse, action: str) -> dict:
    try:
        data = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"A AssemblyAI retornou uma resposta invalida ao {action}.") from error
    return data if isinstance(data, dict) else {}


def _error_message(data: dict, fallback: str) -> str:
    return str(data.get("error") or data.get("message") or fallback)


def _prepare_sync_wav(source: Path, destination: Path) -> bool:
    if source.suffix.lower() == ".wav":
        shutil.copyfile(source, destination)
        return True
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and destination.is_file() and destination.stat().st_size > 44


def _sync_request(audio_path: Path, api_key: str) -> HttpRequest:
    boundary = f"----CreativeHub{uuid4().hex}"
    payload = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="config"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            b'{"timestamps": true}\r\n',
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="audio"; filename="audio.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            audio_path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    return HttpRequest(
        "POST",
        ASSEMBLYAI_SYNC_URL,
        {
            "authorization": api_key,
            "content-type": f"multipart/form-data; boundary={boundary}",
            "x-aai-model": UNIVERSAL_35_PRO,
        },
        payload,
    )


def _wav_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as wav:
            rate = wav.getframerate()
            return wav.getnframes() / rate if rate else float("inf")
    except (OSError, wave.Error):
        return float("inf")


def _urllib_transport(request: HttpRequest) -> HttpResponse:
    url_request = Request(request.url, data=request.body, headers=dict(request.headers), method=request.method)
    try:
        with urlopen(url_request, timeout=90) as response:
            return HttpResponse(response.status, dict(response.headers.items()), response.read())
    except HTTPError as error:
        return HttpResponse(error.code, dict(error.headers.items()) if error.headers else {}, error.read())
    except URLError as error:
        raise RuntimeError(f"Nao foi possivel conectar com a AssemblyAI: {error.reason}") from error
