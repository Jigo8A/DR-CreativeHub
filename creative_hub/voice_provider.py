from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from domain import CopyCard, HubSettings


class VoiceProviderUnavailable(RuntimeError):
    pass


class VoiceProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[HttpRequest], HttpResponse]
ProgressCallback = Callable[[str, int | None], None]
_AUDIO_DOWNLOAD_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


class VoiceProvider(Protocol):
    def generate(
        self,
        card: CopyCard,
        settings: HubSettings,
        progress_callback: ProgressCallback | None = None,
        destination: Path | None = None,
    ) -> Path: ...

    def list_voices(self, settings: HubSettings, provider: str) -> list[dict]: ...


class UnavailableVoiceProvider:
    def generate(
        self,
        card: CopyCard,
        settings: HubSettings,
        progress_callback: ProgressCallback | None = None,
        destination: Path | None = None,
    ) -> Path:
        raise VoiceProviderUnavailable("A API de voz ainda nao foi configurada.")


class OpenSpeakerVoiceProvider:
    base_url = "https://api.ai33.pro"

    def __init__(
        self,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        poll_interval: float = 1.5,
        max_poll_attempts: int = 180,
    ) -> None:
        self.transport = transport or _urllib_transport
        self.sleep = sleep
        self.random_value = random_value
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts

    def generate(
        self,
        card: CopyCard,
        settings: HubSettings,
        progress_callback: ProgressCallback | None = None,
        destination: Path | None = None,
    ) -> Path:
        api_key = settings.voice_api_key.strip()
        voice_id = settings.voice_name.strip()
        text = card.text.strip()
        if not api_key:
            raise VoiceProviderError("Informe a chave da API OpenSpeaker nas configuracoes.")
        if not voice_id:
            raise VoiceProviderError("Informe uma voz OpenSpeaker nas configuracoes.")
        if not _has_voice_prefix(voice_id):
            raise VoiceProviderError("A voz deve usar o prefixo do provedor, por exemplo minimax_ ou elevenlabs_.")
        if not text:
            raise VoiceProviderError("A copy nao possui texto para narrar.")
        if not settings.output_folder.strip():
            raise VoiceProviderError("Selecione uma pasta de saida antes de gerar os audios.")
        try:
            speed = float(settings.voice_speed)
        except (TypeError, ValueError) as exc:
            raise VoiceProviderError("A velocidade da narracao deve estar entre 0.50 e 1.50.") from exc
        if not 0.5 <= speed <= 1.5:
            raise VoiceProviderError("A velocidade da narracao deve estar entre 0.50 e 1.50.")

        if progress_callback:
            progress_callback("Enviando copy para OpenSpeaker...", 5)
        task_id = self._create_task(text, voice_id, speed, api_key)
        if progress_callback:
            progress_callback("Aguardando narracao...", 12)
        audio_url = self._wait_for_task(task_id, api_key, progress_callback)
        if progress_callback:
            progress_callback("Baixando audio...", 94)
        target = destination or self._audio_destination(card, Path(settings.output_folder), audio_url)
        response = self._send(HttpRequest("GET", audio_url, {"User-Agent": _AUDIO_DOWNLOAD_USER_AGENT}))
        if response.status < 200 or response.status >= 300:
            raise VoiceProviderError(_response_error(response, {}, "baixar o audio gerado"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.body)
        if progress_callback:
            progress_callback("Audio pronto.", 100)
        return target

    def list_voices(self, settings: HubSettings, provider: str) -> list[dict]:
        api_key = settings.voice_api_key.strip()
        if not api_key:
            raise VoiceProviderError("Informe a chave da API OpenSpeaker nas configuracoes.")
        response = self._send(
            HttpRequest("GET", f"{self.base_url}/v3/voices?provider={provider}&page=1&page_size=100", {"xi-api-key": api_key})
        )
        data = _json_body(response, "carregar as vozes")
        if response.status < 200 or response.status >= 300 or not data.get("success"):
            raise VoiceProviderError(_response_error(response, data, "carregar as vozes"))
        voices = []
        for item in data.get("data", []):
            if not isinstance(item, Mapping):
                continue
            voice_id = str(item.get("voice_id") or item.get("id") or "").strip()
            if not voice_id:
                continue
            voices.append(
                {
                    "id": voice_id,
                    "name": str(item.get("name") or item.get("voice_name") or voice_id),
                    "provider": str(item.get("provider") or provider),
                    "language": str(item.get("language") or item.get("locale") or ""),
                }
            )
        return voices

    def _create_task(self, text: str, voice_id: str, speed: float, api_key: str) -> str:
        body, content_type = _multipart_form({"text": text, "voice_id": voice_id, "speed": f"{speed:.2f}", "with_transcript": "false"})
        response = self._send(
            HttpRequest(
                "POST",
                f"{self.base_url}/v3/text-to-speech",
                {"xi-api-key": api_key, "Content-Type": content_type},
                body,
            )
        )
        data = _json_body(response, "criar a narracao")
        task_id = str(data.get("task_id", "")).strip()
        if response.status < 200 or response.status >= 300 or not data.get("success") or not task_id:
            raise VoiceProviderError(_response_error(response, data, "criar a narracao"))
        return task_id

    def _wait_for_task(self, task_id: str, api_key: str, progress_callback: ProgressCallback | None) -> str:
        for attempt in range(self.max_poll_attempts):
            response = self._send(HttpRequest("GET", f"{self.base_url}/v1/task/{task_id}", {"xi-api-key": api_key}))
            data = _json_body(response, "consultar a narracao")
            status = str(data.get("status", "")).lower()
            if response.status < 200 or response.status >= 300:
                raise VoiceProviderError(_response_error(response, data, "consultar a narracao"))
            if status == "done":
                audio_url = str((data.get("metadata") or {}).get("audio_url", "")).strip()
                if not audio_url:
                    raise VoiceProviderError("A OpenSpeaker concluiu a tarefa sem informar a URL do audio.")
                return audio_url
            if status in {"failed", "error", "cancelled"}:
                raise VoiceProviderError(_error_message(data, "A OpenSpeaker nao conseguiu gerar esta narracao."))
            if progress_callback:
                progress_callback("Gerando narracao...", _clamp_progress(data.get("progress")))
            if attempt < self.max_poll_attempts - 1 and self.poll_interval:
                self.sleep(self.poll_interval)
        raise VoiceProviderError("A narracao demorou mais que o tempo limite da Creative Hub.")

    def _send(self, request: HttpRequest) -> HttpResponse:
        for attempt in range(4):
            response = self.transport(request)
            if response.status not in {429, 503}:
                return response
            if attempt == 3:
                return response
            retry_after = _retry_after(response.headers)
            delay = retry_after if retry_after is not None else min(8.0, 1.0 * (2**attempt) + self.random_value() * 0.25)
            self.sleep(delay)
        raise AssertionError("Loop de retentativa inesperado.")

    def _audio_destination(self, card: CopyCard, output_folder: Path, audio_url: str) -> Path:
        suffix = Path(urlparse(audio_url).path).suffix.lower()
        suffix = suffix if suffix in {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"} else ".mp3"
        name = _safe_name(card.title or card.id)
        return output_folder / "_creative_hub_audio" / f"{name}_{uuid4().hex[:8]}{suffix}"


def _urllib_transport(request: HttpRequest) -> HttpResponse:
    url_request = Request(request.url, data=request.body, headers=dict(request.headers), method=request.method)
    try:
        with urlopen(url_request, timeout=45) as response:
            return HttpResponse(response.status, dict(response.headers.items()), response.read())
    except HTTPError as error:
        return HttpResponse(error.code, dict(error.headers.items()) if error.headers else {}, error.read())
    except URLError as error:
        raise VoiceProviderError(f"Nao foi possivel conectar com a OpenSpeaker: {error.reason}") from error


def _multipart_form(fields: Mapping[str, str]) -> tuple[bytes, str]:
    boundary = f"----CreativeHub{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _json_body(response: HttpResponse, action: str) -> dict:
    try:
        data = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        preview = response.body.decode("utf-8", errors="replace").strip().replace("\n", " ")[:300]
        detail = f" Corpo: {preview}" if preview else ""
        raise VoiceProviderError(f"A OpenSpeaker retornou HTTP {response.status} com resposta invalida ao {action}.{detail}") from error
    return data if isinstance(data, dict) else {}


def _error_message(data: Mapping, fallback: str) -> str:
    return str(data.get("error_message") or data.get("message") or fallback)


def _response_error(response: HttpResponse, data: Mapping, action: str) -> str:
    code = str(data.get("code") or data.get("error_code") or "").strip()
    message = _error_message(data, f"Falha ao {action}.")
    parts = [f"OpenSpeaker HTTP {response.status}"]
    if code:
        parts.append(f"codigo: {code}")
    details = _rate_limit_details(response.headers)
    suffix = f" [{'; '.join(details)}]" if details else ""
    return f"{' | '.join(parts)}: {message}{suffix}"


def _rate_limit_details(headers: Mapping[str, str]) -> list[str]:
    wanted = {
        "retry-after": "Retry-After",
        "x-ratelimit-remaining": "Remaining",
        "x-ratelimit-limit": "Limit",
        "x-ratelimit-burst": "Burst",
        "x-ratelimit-scope": "Scope",
    }
    values = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    details = []
    for key, label in wanted.items():
        value = values.get(key)
        if not value:
            continue
        details.append(f"{label}: {value}{'s' if key == 'retry-after' else ''}")
    return details


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return None
    return None


def _has_voice_prefix(voice_id: str) -> bool:
    return voice_id.startswith(("elevenlabs_", "minimax_", "clone_", "edge_", "kokoro_", "vbee_", "fishaudio_"))


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return normalized.strip("_")[:60] or "narracao"


def _clamp_progress(value: object) -> int | None:
    try:
        return max(12, min(92, int(float(value))))
    except (TypeError, ValueError):
        return None
