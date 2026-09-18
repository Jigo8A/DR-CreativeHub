import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from assembly_transcriber import AssemblyAISpeechDetector
from voice_provider import HttpResponse


class AssemblyAISpeechDetectorTests(unittest.TestCase):
    def test_uses_sync_api_for_short_audio_and_returns_timed_words(self) -> None:
        with TemporaryDirectory() as temporary:
            audio = Path(temporary) / "copy.mp3"
            audio.write_bytes(b"compressed-audio")
            requests = []

            def transport(request):
                requests.append(request)
                return HttpResponse(
                    200,
                    {},
                    json.dumps(
                        {
                            "words": [
                                {"text": "Ola", "start": 120, "end": 490},
                                {"text": "mundo", "start": 510, "end": 940},
                            ],
                            "request_time_ms": 210,
                        }
                    ).encode(),
                )

            def prepare_sync_audio(_source, destination):
                with wave.open(str(destination), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 16000)
                return True

            detector = AssemblyAISpeechDetector(
                "assembly-key",
                transport=transport,
                sync_audio_preparer=prepare_sync_audio,
            )
            words = detector.detect_words(audio)

            self.assertEqual([(word.text, word.start, word.end) for word in words], [("Ola", 0.12, 0.49), ("mundo", 0.51, 0.94)])
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].url, "https://sync.assemblyai.com/transcribe")
            self.assertEqual(requests[0].headers["x-aai-model"], "universal-3-5-pro")
            self.assertIn(b"RIFF", requests[0].body or b"")

    def test_falls_back_to_async_api_when_sync_api_rejects_audio(self) -> None:
        with TemporaryDirectory() as temporary:
            audio = Path(temporary) / "copy.mp3"
            audio.write_bytes(b"compressed-audio")
            requests = []
            responses = iter(
                [
                    HttpResponse(422, {}, b'{"error":"audio_too_long"}'),
                    HttpResponse(200, {}, b'{"upload_url":"https://cdn.example/audio"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"queued"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"completed","words":[{"text":"Ola","start":0,"end":300}]}'),
                ]
            )

            def transport(request):
                requests.append(request)
                return next(responses)

            def prepare_sync_audio(_source, destination):
                with wave.open(str(destination), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 16000)
                return True

            detector = AssemblyAISpeechDetector(
                "assembly-key",
                transport=transport,
                sleep=lambda _: None,
                poll_interval=0,
                sync_audio_preparer=prepare_sync_audio,
            )
            words = detector.detect_words(audio)

            self.assertEqual([(word.text, word.start, word.end) for word in words], [("Ola", 0.0, 0.3)])
            self.assertEqual(requests[0].url, "https://sync.assemblyai.com/transcribe")
            self.assertEqual(requests[1].url, "https://api.assemblyai.com/v2/upload")

    def test_skips_sync_api_when_prepared_audio_exceeds_two_minutes(self) -> None:
        with TemporaryDirectory() as temporary:
            audio = Path(temporary) / "copy.mp3"
            audio.write_bytes(b"compressed-audio")
            requests = []
            responses = iter(
                [
                    HttpResponse(200, {}, b'{"upload_url":"https://cdn.example/audio"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"queued"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"completed","words":[{"text":"Ola","start":0,"end":300}]}'),
                ]
            )

            def prepare_long_wav(_source, destination):
                with wave.open(str(destination), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(1)
                    wav.writeframes(b"\0\0" * 121)
                return True

            def transport(request):
                requests.append(request)
                return next(responses)

            detector = AssemblyAISpeechDetector(
                "assembly-key",
                transport=transport,
                sleep=lambda _: None,
                poll_interval=0,
                sync_audio_preparer=prepare_long_wav,
            )
            detector.detect_words(audio)

            self.assertEqual(requests[0].url, "https://api.assemblyai.com/v2/upload")

    def test_uploads_audio_polls_universal_pro_and_returns_timed_words(self) -> None:
        with TemporaryDirectory() as temporary:
            audio = Path(temporary) / "copy.mp3"
            audio.write_bytes(b"audio-bytes")
            requests = []
            responses = iter(
                [
                    HttpResponse(200, {}, b'{"upload_url":"https://cdn.example/audio"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"queued"}'),
                    HttpResponse(200, {}, b'{"id":"transcript-123","status":"processing"}'),
                    HttpResponse(
                        200,
                        {},
                        json.dumps(
                            {
                                "id": "transcript-123",
                                "status": "completed",
                                "speech_model_used": "universal-3-5-pro",
                                "words": [
                                    {"text": "Ola", "start": 120, "end": 490, "confidence": 0.99},
                                    {"text": "mundo", "start": 510, "end": 940, "confidence": 0.98},
                                ],
                            }
                        ).encode(),
                    ),
                ]
            )

            def transport(request):
                requests.append(request)
                return next(responses)

            detector = AssemblyAISpeechDetector(
                "assembly-key",
                transport=transport,
                sleep=lambda _: None,
                poll_interval=0,
                sync_audio_preparer=lambda _source, _destination: False,
            )
            words = detector.detect_words(audio)

            self.assertEqual([(word.text, word.start, word.end) for word in words], [("Ola", 0.12, 0.49), ("mundo", 0.51, 0.94)])
            self.assertEqual(requests[0].url, "https://api.assemblyai.com/v2/upload")
            self.assertEqual(requests[0].headers["authorization"], "assembly-key")
            self.assertEqual(requests[0].body, b"audio-bytes")
            submitted = json.loads(requests[1].body.decode())
            self.assertEqual(submitted["speech_models"], ["universal-3-5-pro"])
            self.assertEqual(submitted["audio_url"], "https://cdn.example/audio")
            self.assertEqual(requests[2].url, "https://api.assemblyai.com/v2/transcript/transcript-123")

    def test_rejects_a_completed_transcript_without_word_timestamps(self) -> None:
        responses = iter(
            [
                HttpResponse(200, {}, b'{"upload_url":"https://cdn.example/audio"}'),
                HttpResponse(200, {}, b'{"id":"transcript-123","status":"queued"}'),
                HttpResponse(200, {}, b'{"id":"transcript-123","status":"completed","words":[]}'),
            ]
        )
        with TemporaryDirectory() as temporary:
            audio = Path(temporary) / "copy.wav"
            audio.write_bytes(b"audio")
            detector = AssemblyAISpeechDetector(
                "assembly-key",
                transport=lambda _: next(responses),
                sleep=lambda _: None,
                poll_interval=0,
                sync_audio_preparer=lambda _source, _destination: False,
            )

            with self.assertRaisesRegex(RuntimeError, "marcacoes por palavra"):
                detector.detect_words(audio)
