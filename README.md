# Vaani — Speech to Text

A small speech transcription app built with React, FastAPI, SQLite, and the open-source Whisper model. It is designed to run on your computer without a paid transcription API.

## What it does

- Captures microphone audio in the browser.
- Shows a rolling live preview while you speak. The preview can change as the model gets more audio.
- Runs a final transcription using `faster-whisper`, with automatic language detection (including Hindi and English).
- Saves transcripts in a local SQLite database.
- Lists, searches, edits, copies, and deletes saved transcripts.

The first run downloads the selected Whisper model from Hugging Face. After that, inference runs locally. The browser sends audio to the FastAPI server on your machine; audio is not saved as a recording. Use a current desktop Chrome or Edge browser and allow microphone access. Microphone capture on a deployed site requires HTTPS.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer
- A microphone

## Run it locally

Open two terminal windows from the project folder.

### 1. Start the API

```powershell
cd backend
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install dependencies and start the API:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API docs are at <http://127.0.0.1:8000/docs>. The SQLite database `backend/transcriptions.db` is created automatically.

### 2. Start the React app

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local address Vite prints (normally <http://localhost:5173>), allow microphone access, and start speaking.

### Run both services from VS Code (Windows)

Node.js LTS is included as a project-local runtime under `tools/node-v24.22.3-win-x64`, and `.vscode/settings.json` adds it to new VS Code terminals. Open a **new** integrated terminal after opening this folder to use `node` and `npm` commands.

To launch both services using VS Code tasks, choose **Terminal → Run Task → Vaani: API**, then open a second task terminal and choose **Terminal → Run Task → Vaani: Web**. The API listens on port `8000`, and the frontend on `5173` proxies API and WebSocket requests to it.

- App: <http://localhost:5173>
- API: <http://127.0.0.1:8000/>
- API health: <http://127.0.0.1:8000/api/health>
- API docs: <http://127.0.0.1:8000/docs>

If you prefer separate terminals, run the API and frontend commands above. During Vite development, `/api` requests are proxied to `http://127.0.0.1:8000`; set `VITE_API_PROXY_TARGET` to use another backend address. Set `VITE_API_URL` when the frontend should call an API directly, such as in a production deployment.

## Model size and language

The default model is `tiny`, which uses less memory and is quickest on a CPU. Set `WHISPER_MODEL=base` or `WHISPER_MODEL=small` before starting FastAPI for a larger, generally more accurate model. The selected model is downloaded once and cached by faster-whisper. Model quality and speed depend on your hardware. Whisper automatically detects the spoken language; the language picker in the UI is only a display preference at this stage.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | API status and docs link |
| `GET` | `/api/health` | Check API status |
| `GET` | `/api/transcriptions` | Read transcription history |
| `POST` | `/api/transcriptions` | Save a transcription |
| `PATCH` | `/api/transcriptions/{id}` | Edit title or transcript text |
| `DELETE` | `/api/transcriptions/{id}` | Delete a transcription |
| `POST` | `/api/transcribe` | Transcribe 16-bit PCM audio |
| `WS` | `/api/live` | Receive rolling live preview from 16 kHz PCM audio |

## Useful settings

- `WHISPER_MODEL`: `tiny`, `base`, or `small` (default: `tiny`)
- `DATABASE_PATH`: SQLite database file (default: `backend/transcriptions.db`)
- `CORS_ORIGINS`: comma-separated allowed frontend origins (default: `http://127.0.0.1:5173,http://localhost:5173`)
- `VITE_API_PROXY_TARGET`: backend target for the Vite development proxy (default: `http://127.0.0.1:8000`)
- `VITE_API_URL`: optional direct API base URL for the frontend; local development uses the Vite proxy by default

## Deployment notes

This project is intentionally easiest and cheapest to run locally. A free cloud host may sleep, have limited memory, or not provide enough CPU/RAM for Whisper. For deployment, host the FastAPI API and SQLite file on a persistent machine/volume, set `CORS_ORIGINS` and `VITE_API_URL`, and serve the frontend over HTTPS. Vercel uses `/tmp/transcriptions.db` by default so the function can initialize SQLite, but `/tmp` is ephemeral and data can be lost between instances or deployments; configure `DATABASE_PATH` only for a writable persistent volume or use an external database when transcription history must persist.

## Project structure

```text
backend/
  app/
    database.py       # SQLite setup and connections
    main.py           # FastAPI routes and CRUD API
    transcriber.py    # Local faster-whisper model
  requirements.txt
frontend/
  src/
    App.jsx           # Main page, microphone, history, and editing
    main.jsx          # React entry point
    styles.css        # App styles
  package.json
  vite.config.js
```

## License

This starter project is provided for learning and hiring-assignment use. Whisper/faster-whisper retain their respective upstream licenses. Check each model's terms before using a downloaded model commercially.
