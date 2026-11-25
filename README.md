# FloraBot

FloraBot is a local plant health workspace with a React + TypeScript frontend, FastAPI backend, SQLite storage, Pl@ntNet species identification, Plant.id health assessment, Groq chat and report generation, ESP camera support, and downloadable health reports.

## Quick start on Windows

Requirements: Python 3.11, Node.js 18 or later, npm, and a working network connection for first-time dependency setup.

1. Double-click `start-florabot.bat` (or run it from a terminal).
2. It creates `backend/.env` from the example on first launch, installs dependencies, and starts the API and web app.
3. Open FloraBot at <http://localhost:5173>. The API documentation is at <http://localhost:8000/docs>.
4. Add service credentials to `backend/.env`, then restart the API window to enable provider calls.

## Configure AI services

Edit `backend/.env` (see `backend/.env.example`):

- `PLANTNET_API_KEY`: Pl@ntNet key for plant species identification.
- `PLANT_ID_API_KEY`: Plant.id key for image health and disease assessment.
- `GROQ_API_KEY`: Groq key for the assistant, image assessment, and report explanations.
- `GROQ_MODEL`: Groq model used by assistant and report generation.

Create keys at [my.plantnet.org](https://my.plantnet.org/), [plant.id](https://web.plant.id/), and [console.groq.com](https://console.groq.com/keys). Keep all provider keys in `backend/.env`; the frontend does not need or receive them. Restart the backend after changing keys. PlantNet identifies species, Plant.id assesses image health, and Groq powers chat, image review, and reports. A lightweight local color screen is used only when hosted health assessment is unavailable.

## Connect an ESP camera

The camera settings are prefilled for the configured ESP camera. Its live MJPEG stream is `http://10.105.234.29:81/stream`, and its still image endpoint is `http://10.105.234.29/capture`. The app forwards the MJPEG stream directly. Open **Settings** in FloraBot to change these URLs if the camera address changes:

- Live stream URL: an MJPEG stream such as `http://192.168.1.50:81/stream`.
- Snapshot URL: an optional still-image endpoint such as `http://192.168.1.50/capture`.

Save the settings to the backend environment. The backend forwards the MJPEG stream; the browser does not poll the snapshot URL for live video. Keep the camera and backend on the same local network. For the ESP32 firmware, use SVGA (800×600), JPEG quality 12, two PSRAM frame buffers, and `CAMERA_GRAB_LATEST` when PSRAM is available. If Wi-Fi still cannot keep up, lower the stream to VGA; the app no longer re-encodes or downsamples the incoming frames.

## Data and storage

SQLite database, uploaded/processed images, and generated PDFs are kept under `backend/data/` by default. They persist across app restarts. Configure alternate locations with `DATABASE_URL`, `UPLOAD_DIR`, and `REPORT_DIR` in `backend/.env`.

## Run with Docker

You can also run FloraBot with Docker Compose:

```bash
docker compose up --build
```

- Web UI: <http://localhost:5173>
- API Docs: <http://localhost:8000/docs>

## Run manually

Backend:

```powershell
cd backend
py -3.11 -m venv .venv311
.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Run backend verification tests:

```powershell
python test_phase1.py
```

Frontend in another terminal:

```powershell
npm install
npm run dev
```

Build production frontend:

```powershell
npm run build
```

## Project structure

```text
backend/app/       FastAPI routes, SQLAlchemy models, provider and PDF services
backend/data/      Persistent SQLite database, uploaded images, PDF reports
src/               React pages and reusable UI components
start-florabot.bat Resilient Windows one-click launcher
docker-compose.yml Multi-container Docker configuration
.github/workflows/ Automated GitHub Actions CI workflow
```

## Notes

- Diagnosis responses and recommendations are based on the configured provider response. Provider confidence is shown as image-result confidence, not model accuracy.
- An inconclusive provider result remains inconclusive; the app encourages a clearer retake rather than aggressive treatment.
- The camera’s live stream may be blocked by browser mixed-content rules if FloraBot is served over HTTPS while the ESP camera only serves HTTP.
