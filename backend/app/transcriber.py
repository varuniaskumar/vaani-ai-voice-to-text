"""Lazy loader for the open-source Whisper transcription model."""

import os
from functools import lru_cache

import numpy as np
from faster_whisper import WhisperModel


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    # tiny is small and quick on CPU. Change WHISPER_MODEL to "base" for better accuracy.
    model_name = os.getenv("WHISPER_MODEL", "tiny")
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int) -> dict:
    """Transcribe mono signed 16-bit PCM; resample to Whisper's 16 kHz input."""
    if not pcm_bytes:
        return {"text": "", "language": "unknown", "duration_seconds": 0.0}

    samples = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0
    if sample_rate != 16000:
        old_positions = np.arange(len(samples), dtype=np.float64) / sample_rate
        new_length = round(len(samples) * 16000 / sample_rate)
        new_positions = np.arange(new_length, dtype=np.float64) / 16000
        samples = np.interp(new_positions, old_positions, samples).astype(np.float32)

    segments, info = get_model().transcribe(
        samples,
        language=None,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return {
        "text": text,
        "language": info.language or "unknown",
        "duration_seconds": round(len(pcm_bytes) / 2 / sample_rate, 2),
    }
