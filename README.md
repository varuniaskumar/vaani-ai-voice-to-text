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
- `CORS_ORIGINS`: comma-separated frontend origins; local Vite origins are always included, add the deployed frontend origin on the API host
- `VITE_API_PROXY_TARGET`: backend target for the Vite development proxy (default: `http://127.0.0.1:8000`)
- `VITE_API_URL`: required production frontend API base URL; local development uses the Vite proxy by default

## Deployment notes

For a Vercel frontend deployment, add `VITE_API_URL` in the Vercel project's Environment Variables and set it to the public FastAPI base URL, for example `https://your-api.example.com` (no trailing slash and no `/api` suffix). Set it for each environment you deploy (Production, Preview, and Development as applicable), then redeploy so Vite includes the value in the build.

On the service hosting FastAPI, set `CORS_ORIGINS` to the exact frontend origin, for example `https://your-app.vercel.app`. Include any additional Vercel preview origins as comma-separated values. Do not include URL paths or a trailing slash. The two local origins (`http://localhost:5173` and `http://127.0.0.1:5173`) remain allowed automatically. If FastAPI is also hosted on Vercel, configure `CORS_ORIGINS` in that backend project's settings, not only in the frontend project.

The backend must be publicly reachable over HTTPS for the deployed app. The frontend keeps using the Vite proxy locally; production requests and live WebSocket connections use `VITE_API_URL`. A free cloud host may sleep, have limited memory, or not provide enough CPU/RAM for Whisper. Vercel uses `/tmp/transcriptions.db` by default so a function can initialize SQLite, but `/tmp` is ephemeral and data can be lost between instances or deployments; configure `DATABASE_PATH` only for a writable persistent volume or use an external database when transcription history must persist.

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
