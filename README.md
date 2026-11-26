# Vaani — Speech to Text

A speech transcription app built with React, FastAPI, SQLite, and Groq Whisper. Audio is sent from the browser to the FastAPI backend and transcribed by Groq.

## What it does

- Captures microphone audio in the browser.
- Shows a rolling live preview while you speak using short REST requests, without a persistent WebSocket.
- Transcribes speech with Groq Whisper and automatic language detection.
- Saves transcripts in a local SQLite database.
- Lists, searches, edits, copies, and deletes saved transcripts.

Audio is not saved as a recording by this app, but audio chunks are sent to Groq for transcription. A Groq API key and an internet connection are required. Use a current desktop Chrome or Edge browser and allow microphone access. Microphone capture on a deployed site requires HTTPS.

## Requirements

- Python 3.12 or newer
- Node.js 18 or newer
- A microphone
- A Groq API key

## Run it locally

Open two terminal windows from the project folder.

If you do not already have a root `.env`, copy `.env.example` to `.env` and set `GROQ_API_KEY`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### 1. Start the API

```powershell
cd backend
python -m venv .venv
```

Activate the environment and start FastAPI:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
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

To launch both services using VS Code tasks, choose **Terminal → Run Task → Vaani: API**, then open a second task terminal and choose **Terminal → Run Task → Vaani: Web**. The API listens on port `8000`, and the frontend on `5173` proxies API requests to it.

- App: <http://localhost:5173>
- API: <http://127.0.0.1:8000/>
- API health: <http://127.0.0.1:8000/api/health>
- API docs: <http://127.0.0.1:8000/docs>

If you prefer separate terminals, run the API and frontend commands above. During Vite development, `/api` requests are proxied to `http://127.0.0.1:8000`; set `VITE_API_PROXY_TARGET` to use another backend address.

## Model and live transcription

The default model is `whisper-large-v3-turbo`; set `GROQ_MODEL=whisper-large-v3` on the backend to use the higher-accuracy model. The frontend submits 20-second PCM chunks to `POST /api/transcribe` while recording and sends the final remainder when recording stops. The API converts PCM to WAV for Groq. Each request stays small enough for Vercel Functions; no WebSocket is used.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Check API status |
| `GET` | `/api/transcriptions` | Read transcription history |
| `POST` | `/api/transcriptions` | Save a transcription |
| `PATCH` | `/api/transcriptions/{id}` | Edit title or transcript text |
| `DELETE` | `/api/transcriptions/{id}` | Delete a transcription |
| `POST` | `/api/transcribe` | Transcribe 16-bit PCM audio |
Live previews use repeated `POST /api/transcribe` requests with PCM audio chunks; no WebSocket endpoint is required.
When the Vite build exists, `/` serves the frontend. On a backend-only local run without a frontend build, `/` retains the API status response.

## Useful settings

- `DATABASE_PATH`: SQLite database file (default: `backend/transcriptions.db`)
- `CORS_ORIGINS`: optional comma-separated frontend origins; local Vite origins are always included
- `VITE_API_PROXY_TARGET`: backend target for the Vite development proxy (default: `http://127.0.0.1:8000`)
- `VITE_API_URL`: optional API base URL override for non-production builds; production always uses same-origin `/api` requests
- `GROQ_API_KEY`: secret Groq API key; set only on the backend
- `GROQ_MODEL`: Groq speech-to-text model (default: `whisper-large-v3-turbo`)

## Deployment notes

Deploy the frontend and FastAPI backend as one Vercel project:

1. Import the repository and set **Root Directory** to the repository root. Use the **FastAPI** framework preset (or **Other** if it is not offered); leave the dashboard Build Command, Output Directory, and Install Command overrides blank. Vercel reads `requirements.txt`, uses the root `main.py` entrypoint, and runs the frontend build from `[tool.vercel.scripts]` in `pyproject.toml`.
2. Add `GROQ_API_KEY` in Vercel **Settings → Environment Variables** for Production and Preview, then redeploy. Optionally add `GROQ_MODEL`. Never create a `VITE_GROQ_API_KEY` variable.
3. Leave `VITE_API_URL` unset so the frontend uses same-origin `/api` requests. `CORS_ORIGINS` is unnecessary for this same-origin setup; add it only if another site must call the API.

The Vercel deployment serves the Vite build at `/` and the FastAPI endpoints under `/api`. Check `/api/health` to verify the API. Local Vite development continues proxying `/api` to FastAPI on port 8000. Vercel uses `/tmp/transcriptions.db`; that storage is ephemeral and does not guarantee transcription history across function instances or deployments. Use a persistent external database if production history must persist.

## Project structure

```text
main.py               # Root Vercel ASGI entrypoint
pyproject.toml        # Vercel build and static-file configuration
requirements.txt      # Root dependency manifest for Vercel
vercel.json           # Single-project Vercel function configuration
backend/
  main.py             # Optional backend-only ASGI entrypoint
  app/
    database.py       # SQLite setup and connections
    main.py           # FastAPI routes and CRUD API
    transcriber.py    # Groq Whisper integration
  requirements.txt
frontend/
  src/
    App.jsx           # Main page, microphone, history, and editing
    main.jsx          # React entry point
    styles.css        # App styles
  package.json
  vite.config.js
.env.example          # Local environment variable template
```

## License

This starter project is provided for learning and hiring-assignment use. Groq and Whisper model usage is subject to their respective terms. Check current Groq pricing and model terms before deployment.
