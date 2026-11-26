import atexit
import base64
import os
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from groq import Groq

_test_storage = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_test_storage.name) / "test.db")
os.environ["CORS_ORIGINS"] = "https://vaani-test.vercel.app/"
os.environ["GROQ_API_KEY"] = "test-api-key"
os.environ["GROQ_MODEL"] = "whisper-large-v3-turbo"
atexit.register(_test_storage.cleanup)

from fastapi.testclient import TestClient

from app.database import database_session
from app.main import app
from app.transcriber import transcribe_pcm


class TranscriptionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        with database_session() as connection:
            connection.execute("DELETE FROM transcriptions")

    def test_health_and_cors_include_local_and_configured_deployment_origins(self):
        self.assertEqual(self.client.get("/api/health").json()["provider"], "groq")

        for origin in (
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://vaani-test.vercel.app",
        ):
            response = self.client.options(
                "/api/health",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers.get("access-control-allow-origin"), origin
            )

    def test_root_serves_built_frontend_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            index_file = Path(directory) / "index.html"
            index_file.write_text("<html>frontend</html>", encoding="utf-8")
            with patch("app.main.FRONTEND_DIST", Path(directory)):
                response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "<html>frontend</html>")

    def test_transcription_history_create_update_delete(self):
        created = self.client.post(
            "/api/transcriptions",
            json={
                "text": "spoken words",
                "language": "en",
                "duration_seconds": 2.5,
            },
        )
        self.assertEqual(created.status_code, 201)
        item = created.json()
        self.assertEqual(item["title"], "spoken words")
        self.assertEqual(item["text"], "spoken words")

        updated = self.client.patch(
            f"/api/transcriptions/{item['id']}",
            json={"title": "Updated title", "text": "Edited words"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Updated title")
        self.assertEqual(updated.json()["text"], "Edited words")

        self.assertEqual(
            self.client.get("/api/transcriptions").json()[0]["id"], item["id"]
        )
        self.assertEqual(
            self.client.delete(f"/api/transcriptions/{item['id']}").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"/api/transcriptions/{item['id']}").status_code, 404
        )

    def test_audio_endpoint_converts_pcm_to_wav_and_returns_frontend_shape(self):
        pcm_bytes = b"\x00\x00" * 16000
        mock_transcriptions = SimpleNamespace(
            create=Mock(return_value=SimpleNamespace(
                text="  hello world  ", language="en"
            ))
        )
        mock_client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=mock_transcriptions)
        )

        with patch(
            "app.transcriber._get_groq_client", return_value=mock_client
        ) as get_client:
            response = self.client.post(
                "/api/transcribe",
                json={
                    "audio_base64": base64.b64encode(pcm_bytes).decode("ascii"),
                    "sample_rate": 16000,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {"text": "hello world", "language": "en", "duration_seconds": 1.0},
        )
        get_client.assert_called_once_with("test-api-key")

        request = mock_transcriptions.create.call_args.kwargs
        self.assertEqual(request["model"], "whisper-large-v3-turbo")
        self.assertEqual(request["response_format"], "verbose_json")
        filename, wav_bytes, mime_type = request["file"]
        self.assertEqual((filename, mime_type), ("recording.wav", "audio/wav"))
        with wave.open(BytesIO(wav_bytes), "rb") as audio_file:
            self.assertEqual(audio_file.getframerate(), 16000)
            self.assertEqual(audio_file.getnchannels(), 1)
            self.assertEqual(audio_file.getsampwidth(), 2)
            self.assertEqual(audio_file.getnframes(), 16000)

    def test_audio_endpoint_rejects_bad_base64_and_incomplete_pcm_samples(self):
        invalid_base64 = self.client.post(
            "/api/transcribe",
            json={"audio_base64": "not-base64", "sample_rate": 16000},
        )
        self.assertEqual(invalid_base64.status_code, 400)

        odd_length_pcm = self.client.post(
            "/api/transcribe",
            json={
                "audio_base64": base64.b64encode(b"\x01").decode("ascii"),
                "sample_rate": 16000,
            },
        )
        self.assertEqual(odd_length_pcm.status_code, 400)

    def test_audio_endpoint_reports_missing_groq_credentials(self):
        pcm_bytes = base64.b64encode(b"\x00\x00" * 8000).decode("ascii")
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            response = self.client.post(
                "/api/transcribe",
                json={"audio_base64": pcm_bytes, "sample_rate": 16000},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])

    def test_groq_sdk_uploads_wav_as_multipart_without_network_access(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "text": "Groq result",
                    "language": "en",
                    "duration": 1.0,
                    "task": "transcribe",
                },
                request=request,
            )

        http_client = httpx.Client(transport=httpx.MockTransport(respond))
        groq_client = Groq(
            api_key="test-api-key",
            base_url="https://api.groq.test/openai/v1",
            http_client=http_client,
        )
        try:
            with patch("app.transcriber._get_groq_client", return_value=groq_client):
                result = transcribe_pcm(b"\x00\x00" * 16000, 16000)
        finally:
            groq_client.close()

        self.assertEqual(result["text"], "Groq result")
        self.assertEqual(result["language"], "en")
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.headers["authorization"], "Bearer test-api-key")
        self.assertIn(b"recording.wav", request.content)
        self.assertIn(b"audio/wav", request.content)
        self.assertIn(b"whisper-large-v3-turbo", request.content)


if __name__ == "__main__":
    unittest.main()
