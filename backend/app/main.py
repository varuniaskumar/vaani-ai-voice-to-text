"""FastAPI application for Vaani speech transcription."""

import base64
import binascii
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
load_dotenv(PROJECT_ROOT / ".env")

from .database import database_session, initialize_database, row_to_dict
from .transcriber import TranscriptionServiceError, transcribe_pcm

MAX_PCM_BYTES = 3 * 1024 * 1024
LOCAL_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
configured_origins = os.getenv("CORS_ORIGINS", "").split(",")
allowed_origins = list(
    dict.fromkeys(
        origin.strip().rstrip("/")
        for origin in [*LOCAL_ORIGINS, *configured_origins]
        if origin.strip()
    )
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Speech to Text API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranscriptionCreate(BaseModel):
    text: str = Field(min_length=1)
    language: str = "unknown"
    duration_seconds: float = Field(default=0, ge=0)
    title: str | None = Field(default=None, max_length=120)


class TranscriptionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, min_length=1)


class AudioRequest(BaseModel):
    audio_base64: str = Field(max_length=4_194_304)
    sample_rate: int = Field(default=16000, ge=8000, le=48000)


@app.get("/")
def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"name": "Speech to Text API", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "provider": "groq",
        "configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
    }


@app.get("/api/transcriptions")
def list_transcriptions():
    with database_session() as connection:
        rows = connection.execute(
            "SELECT * FROM transcriptions ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


@app.post("/api/transcriptions", status_code=201)
def create_transcription(payload: TranscriptionCreate):
    title = payload.title or payload.text[:48].strip() or "Untitled transcription"
    with database_session() as connection:
        cursor = connection.execute(
            "INSERT INTO transcriptions (title, text, language, duration_seconds) "
            "VALUES (?, ?, ?, ?)",
            (title, payload.text.strip(), payload.language, payload.duration_seconds),
        )
        row = connection.execute(
            "SELECT * FROM transcriptions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return row_to_dict(row)


@app.patch("/api/transcriptions/{transcription_id}")
def update_transcription(transcription_id: int, payload: TranscriptionUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide a title or text to update")
    with database_session() as connection:
        existing = connection.execute(
            "SELECT id FROM transcriptions WHERE id = ?", (transcription_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Transcription not found")
        assignments = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [transcription_id]
        connection.execute(
            f"UPDATE transcriptions SET {assignments}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            values,
        )
        row = connection.execute(
            "SELECT * FROM transcriptions WHERE id = ?", (transcription_id,)
        ).fetchone()
    return row_to_dict(row)


@app.delete("/api/transcriptions/{transcription_id}", status_code=204)
def delete_transcription(transcription_id: int):
    with database_session() as connection:
        cursor = connection.execute(
            "DELETE FROM transcriptions WHERE id = ?", (transcription_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transcription not found")


@app.post("/api/transcribe")
def transcribe_audio(payload: AudioRequest):
    try:
        pcm_bytes = base64.b64decode(payload.audio_base64, validate=True)
    except (binascii.Error, ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail="Invalid base64 audio") from error

    if len(pcm_bytes) > MAX_PCM_BYTES:
        raise HTTPException(status_code=413, detail="Audio chunk exceeds the 3 MB limit")
    if len(pcm_bytes) % 2:
        raise HTTPException(
            status_code=400, detail="Audio must contain complete 16-bit samples"
        )

    try:
        return transcribe_pcm(pcm_bytes, payload.sample_rate)
    except TranscriptionServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
