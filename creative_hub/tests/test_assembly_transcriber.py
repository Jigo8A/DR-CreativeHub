import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from assembly_transcriber import AssemblyAISpeechDetector
from voice_provider import HttpResponse


class AssemblyAISpeechDetectorTests(unittest.TestCase):
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

            detector = AssemblyAISpeechDetector("assembly-key", transport=transport, sleep=lambda _: None, poll_interval=0)
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
            detector = AssemblyAISpeechDetector("assembly-key", transport=lambda _: next(responses), sleep=lambda _: None, poll_interval=0)

            with self.assertRaisesRegex(RuntimeError, "marcacoes por palavra"):
                detector.detect_words(audio)
