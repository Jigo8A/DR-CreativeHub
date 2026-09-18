import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain import CopyCard, default_state
from voice_provider import HttpResponse, OpenSpeakerVoiceProvider, VoiceProviderError


class OpenSpeakerVoiceProviderTests(unittest.TestCase):
    def test_rate_limit_error_preserves_api_code_and_retry_information(self) -> None:
        response = HttpResponse(
            429,
            {"Retry-After": "7", "X-RateLimit-Remaining": "0", "X-RateLimit-Scope": "create"},
            json.dumps({"message": "Limite temporario atingido", "code": "rate_limit"}).encode(),
        )
        settings = default_state().settings
        settings.voice_api_key = "api-key"
        settings.voice_name = "minimax_male-qn-qingse"
        settings.output_folder = "."

        with self.assertRaisesRegex(
            VoiceProviderError,
            r"HTTP 429.*rate_limit.*Limite temporario atingido.*Retry-After: 7s.*Remaining: 0.*Scope: create",
        ):
            OpenSpeakerVoiceProvider(transport=lambda _: response, sleep=lambda _: None).generate(
                CopyCard(id="copy-1", text="Texto"), settings
            )

    def test_list_voices_normalizes_the_open_speaker_response(self) -> None:
        response = HttpResponse(
            200,
            {},
            json.dumps(
                {
                    "success": True,
                    "data": [
                        {"voice_id": "clone_maria", "name": "Maria", "provider": "clone", "language": "Portuguese", "gender": "Female"}
                    ],
                    "pagination": {"page": 1, "page_size": 100, "total": 1},
                }
            ).encode(),
        )
        settings = default_state().settings
        settings.voice_api_key = "api-key"

        voices = OpenSpeakerVoiceProvider(transport=lambda _: response).list_voices(settings, "clone")

        self.assertEqual(voices, [{"id": "clone_maria", "name": "Maria", "provider": "clone", "language": "Portuguese"}])

    def test_generate_creates_task_polls_and_saves_audio(self) -> None:
        calls = []
        responses = iter(
            [
                HttpResponse(200, {}, json.dumps({"success": True, "task_id": "task-1"}).encode()),
                HttpResponse(200, {}, json.dumps({"status": "doing", "progress": 50}).encode()),
                HttpResponse(200, {}, json.dumps({"status": "done", "metadata": {"audio_url": "https://cdn.example/audio.mp3"}}).encode()),
                HttpResponse(200, {}, b"generated-audio"),
            ]
        )

        def fake_transport(request):
            calls.append(request)
            return next(responses)

        with TemporaryDirectory() as temporary:
            settings = default_state().settings
            settings.voice_api_key = "api-key"
            settings.voice_name = "minimax_male-qn-qingse"
            settings.output_folder = temporary
            output = OpenSpeakerVoiceProvider(transport=fake_transport, sleep=lambda _: None).generate(
                CopyCard(id="copy-1", title="Oferta", text="Texto para narrar"), settings
            )

            self.assertEqual(output.read_bytes(), b"generated-audio")
            self.assertEqual(calls[0].url, "https://api.ai33.pro/v3/text-to-speech")
            self.assertEqual(calls[0].headers["xi-api-key"], "api-key")
            self.assertIn(b'name="voice_id"', calls[0].body)
            self.assertIn(b"minimax_male-qn-qingse", calls[0].body)
            self.assertEqual(calls[1].url, "https://api.ai33.pro/v1/task/task-1")
            self.assertIn("Mozilla/5.0", calls[3].headers["User-Agent"])

    def test_generate_sends_the_configured_narration_speed(self) -> None:
        calls = []
        responses = iter(
            [
                HttpResponse(200, {}, json.dumps({"success": True, "task_id": "task-1"}).encode()),
                HttpResponse(200, {}, json.dumps({"status": "done", "metadata": {"audio_url": "https://cdn.example/audio.mp3"}}).encode()),
                HttpResponse(200, {}, b"generated-audio"),
            ]
        )

        with TemporaryDirectory() as temporary:
            settings = default_state().settings
            settings.voice_api_key = "api-key"
            settings.voice_name = "minimax_male-qn-qingse"
            settings.voice_speed = 1.12
            settings.output_folder = temporary
            OpenSpeakerVoiceProvider(transport=lambda request: (calls.append(request), next(responses))[1], sleep=lambda _: None).generate(
                CopyCard(id="copy-1", title="Oferta", text="Texto para narrar"), settings
            )

        self.assertIn(b'name="speed"', calls[0].body)
        self.assertIn(b"1.12", calls[0].body)

    def test_generate_uses_the_requested_organized_destination(self) -> None:
        responses = iter(
            [
                HttpResponse(200, {}, json.dumps({"success": True, "task_id": "task-1"}).encode()),
                HttpResponse(200, {}, json.dumps({"status": "done", "metadata": {"audio_url": "https://cdn.example/audio.mp3"}}).encode()),
                HttpResponse(200, {}, b"audio"),
            ]
        )
        with TemporaryDirectory() as temporary:
            settings = default_state().settings
            settings.voice_api_key = "api-key"
            settings.voice_name = "minimax_male-qn-qingse"
            settings.output_folder = temporary
            destination = Path(temporary) / "audios" / "Video 22_abcd1234.mp3"

            result = OpenSpeakerVoiceProvider(transport=lambda _: next(responses), sleep=lambda _: None).generate(
                CopyCard(id="copy-1", title="Video 22", text="Texto para narrar"), settings, destination=destination
            )

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"audio")

    def test_generate_retries_rate_limit_before_polling_again(self) -> None:
        responses = iter(
            [
                HttpResponse(200, {}, json.dumps({"success": True, "task_id": "task-1"}).encode()),
                HttpResponse(429, {"Retry-After": "2"}, b"{}"),
                HttpResponse(200, {}, json.dumps({"status": "done", "metadata": {"audio_url": "https://cdn.example/audio.mp3"}}).encode()),
                HttpResponse(200, {}, b"audio"),
            ]
        )
        delays = []
        with TemporaryDirectory() as temporary:
            settings = default_state().settings
            settings.voice_api_key = "api-key"
            settings.voice_name = "edge_pt-BR-FranciscaNeural"
            settings.output_folder = temporary
            OpenSpeakerVoiceProvider(transport=lambda _: next(responses), sleep=delays.append).generate(
                CopyCard(id="copy-1", text="Texto"), settings
            )

        self.assertEqual(delays, [2.0])
