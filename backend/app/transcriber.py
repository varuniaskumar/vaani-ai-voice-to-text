"""Groq Whisper transcription for browser-captured PCM audio."""

import os
import wave
from functools import lru_cache
from io import BytesIO

from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    RateLimitError,
)


class TranscriptionServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@lru_cache(maxsize=1)
def _get_groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key, timeout=60, max_retries=1)


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int) -> dict:
    if not pcm_bytes:
        return {"text": "", "language": "unknown", "duration_seconds": 0.0}

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise TranscriptionServiceError(
            503, "Groq is not configured. Set GROQ_API_KEY on the backend."
        )

    wav_buffer = BytesIO()
    with wave.open(wav_buffer, "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(pcm_bytes)

    try:
        result = _get_groq_client(api_key).audio.transcriptions.create(
            file=("recording.wav", wav_buffer.getvalue(), "audio/wav"),
            model=os.getenv("GROQ_MODEL", "whisper-large-v3-turbo"),
            response_format="verbose_json",
        )
    except AuthenticationError as error:
        raise TranscriptionServiceError(
            503, "Groq rejected the configured API key. Check GROQ_API_KEY."
        ) from error
    except RateLimitError as error:
        raise TranscriptionServiceError(
            429, "Groq rate limit reached. Please try again shortly."
        ) from error
    except APIConnectionError as error:
        raise TranscriptionServiceError(
            502, "Could not connect to the Groq transcription service."
        ) from error
    except APIStatusError as error:
        raise TranscriptionServiceError(
            502, f"Groq transcription failed with status {error.status_code}."
        ) from error

    return {
        "text": result.text.strip(),
        "language": getattr(result, "language", None) or "unknown",
        "duration_seconds": round(len(pcm_bytes) / (2 * sample_rate), 2),
    }
