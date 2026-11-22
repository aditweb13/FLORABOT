# FloraBot

FloraBot is a local plant health workspace with a React + TypeScript frontend, FastAPI backend, SQLite storage, Plant.id Health Assessment integration, Groq chat, ESP camera support, and downloadable ReportLab health reports.

## Quick start on Windows

Requirements: Python 3.10 or later, Node.js 18 or later, and npm.

1. Double-click `start-florabot.bat` (or run it from a terminal).
2. It creates `backend/.env` from the example on first launch, installs dependencies, and starts the API and web app.
3. Open FloraBot at <http://localhost:5173>. The API documentation is at <http://localhost:8000/docs>.
4. Add service credentials to `backend/.env`, then restart the API window to enable provider calls.

## Configure AI services

Edit `backend/.env` (see `backend/.env.example`):

- `PLANT_ID_API_KEY`: Plant.id / Kindwise key. The app calls the Plant Health Assessment endpoint for identification and health or disease suggestions.
- `PLANT_ID_API_URL`: Optional endpoint override. Defaults to `https://plant.id/api/v3/health_assessment`.
- `GROQ_API_KEY`: Groq API key for the plant care chat assistant.
- `GROQ_MODEL`: Groq chat model; defaults to `openai/gpt-oss-120b`.

API keys remain on the backend and are not sent to the browser. If a key is missing, the corresponding feature reports that it is not configured instead of returning mock results.

## Connect an ESP camera

The camera settings are prefilled for the configured ESP camera. Its live MJPEG stream is `http://10.105.234.29:81/stream`, and its still image endpoint is `http://10.105.234.29/capture`. Open **Settings** in FloraBot to change these URLs if the camera address changes:

- Live stream URL: an MJPEG stream such as `http://192.168.1.50:81/stream`.
- Snapshot URL: an optional still-image endpoint such as `http://192.168.1.50/capture`.

Save the settings and test the camera endpoint. These URLs are stored in the current browser. The camera and the browser must be able to reach each other on the same network. If the camera has no snapshot endpoint, Capture lets you choose an image file instead. Some ESP firmware needs permissive CORS headers to allow browser snapshot capture.

## Data and storage

SQLite database, uploaded/processed images, and generated PDFs are kept under `backend/data/` by default. They persist across app restarts. Configure alternate locations with `DATABASE_URL`, `UPLOAD_DIR`, and `REPORT_DIR` in `backend/.env`.

## Run manually

Backend:

```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Frontend in another terminal:

```powershell
npm install
npm run dev
```

## Project structure

```text
backend/app/       FastAPI routes, SQLAlchemy models, provider and PDF services
backend/data/      Persistent SQLite database, uploaded images, PDF reports
src/               React pages and reusable UI components
start-florabot.bat Windows one-click launcher
```

## Notes

- Diagnosis responses and recommendations are based on the configured provider response. Provider confidence is shown as image-result confidence, not model accuracy.
- An inconclusive provider result remains inconclusive; the app encourages a clearer retake rather than aggressive treatment.
- The camera’s live stream may be blocked by browser mixed-content rules if FloraBot is served over HTTPS while the ESP camera only serves HTTP.
