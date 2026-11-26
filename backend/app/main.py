from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .database import database_session, initialize_database, row_to_dict
from .transcriber import transcribe_pcm


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Speech to Text API", version="1.0.0", lifespan=lifespan)
local_origins = ["http://127.0.0.1:5173", "http://localhost:5173"]
configured_origins = os.getenv("CORS_ORIGINS", "").split(",")
origins = list(
    dict.fromkeys(
        origin.strip().rstrip("/")
        for origin in [*local_origins, *configured_origins]
        if origin.strip()
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranscriptionCreate(BaseModel):
    text: str = Field(min_length=1)
    language: str = "unknown"
    duration_seconds: float = Field(default=0, ge=0)
    title: str | None = None


class TranscriptionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, min_length=1)


class AudioRequest(BaseModel):
    # PCM is base64 encoded by the browser so the same endpoint works with JSON.
    audio_base64: str
    sample_rate: int = Field(default=16000, ge=8000, le=48000)


@app.get("/")
def root():
    return {"name": "Speech to Text API", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/transcriptions")
def list_transcriptions():
    with database_session() as connection:
        rows = connection.execute(
            "SELECT * FROM transcriptions ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


@app.post("/api/transcriptions", status_code=201)
def create_transcription(payload: TranscriptionCreate):
    title = (payload.title or payload.text[:48].strip() or "Untitled transcription")
    with database_session() as connection:
        cursor = connection.execute(
            "INSERT INTO transcriptions (title, text, language, duration_seconds) VALUES (?, ?, ?, ?)",
            (title, payload.text.strip(), payload.language, payload.duration_seconds),
        )
        row = connection.execute("SELECT * FROM transcriptions WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.patch("/api/transcriptions/{transcription_id}")
def update_transcription(transcription_id: int, payload: TranscriptionUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide a title or text to update")
    with database_session() as connection:
        existing = connection.execute("SELECT id FROM transcriptions WHERE id = ?", (transcription_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Transcription not found")
        assignments = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [transcription_id]
        connection.execute(
            f"UPDATE transcriptions SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            values,
        )
        row = connection.execute("SELECT * FROM transcriptions WHERE id = ?", (transcription_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/transcriptions/{transcription_id}", status_code=204)
def delete_transcription(transcription_id: int):
    with database_session() as connection:
        cursor = connection.execute("DELETE FROM transcriptions WHERE id = ?", (transcription_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transcription not found")


@app.post("/api/transcribe")
def transcribe_audio(payload: AudioRequest):
    import base64
    try:
        pcm_bytes = base64.b64decode(payload.audio_base64, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid base64 audio")
    if len(pcm_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio is too large (maximum 50 MB)")
    if len(pcm_bytes) % 2:
        raise HTTPException(status_code=400, detail="Audio must contain complete 16-bit samples")
    try:
        return transcribe_pcm(pcm_bytes, payload.sample_rate)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Transcription failed: {error}") from error


@app.websocket("/api/live")
async def live_preview(websocket: WebSocket):
    """Accept raw 16 kHz PCM and return rolling 4-second transcript previews."""
    await websocket.accept()
    pcm = bytearray()
    last_transcribed = 0
    window_bytes = 4 * 16000 * 2
    hop_bytes = 2 * 16000 * 2
    try:
        while True:
            message = await websocket.receive()
            if message.get("bytes") is None:
                continue
            pcm.extend(message["bytes"])
            if len(pcm) >= window_bytes and len(pcm) - last_transcribed >= hop_bytes:
                start = max(0, len(pcm) - window_bytes)
                preview = await run_in_threadpool(transcribe_pcm, bytes(pcm[start:]), 16000)
                await websocket.send_json({"type": "preview", **preview})
                last_transcribed = len(pcm)
    except WebSocketDisconnect:
        pass
    except Exception as error:
        try:
            await websocket.send_json({"type": "error", "message": str(error)})
            await websocket.close(code=1011)
        except Exception:
            pass
