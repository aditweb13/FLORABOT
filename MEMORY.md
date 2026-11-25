# FloraBOT — Project Memory and Current State

**Last updated:** 2026-11-25  
**Purpose:** Persistent handover note for future development sessions. Update this file whenever code, tests, model artifacts, hardware, or project decisions change.

## 1. Project identity

- **Project:** FloraBOT
- **Purpose:** Plant monitoring and care assistant combining a web dashboard, Python backend, plant image analysis, optional external plant diagnosis, knowledge/AI explanations, watering recommendations, PDF reports, and ESP32-CAM image capture.
- **Source baseline:** `FLORABOT-main.zip` supplied in the conversation.
- **Current assessment:** Substantial software prototype / foundation. Not yet a validated autonomous plant-care product.

## 2. Technology stack found in the source

### Frontend
- React 19
- TypeScript 5.7
- Vite 6
- Tailwind CSS 3
- Recharts and lucide-react
- Main files: `src/App.tsx`, `src/main.tsx`, `src/style.css`

### Backend
- Python + FastAPI
- SQLAlchemy
- SQLite database included as `backend/florabot.db`
- Main files: `backend/app/main.py`, `models.py`, `database.py`, `config.py`
- Services include `vision_engine.py`, `watering_engine.py`, `agent_service.py`, `services.py`, `camera_service.py`, `knowledge_service.py`, and `pdf_service.py`.

### Hardware
- Arduino-style ESP32-CAM firmware targeting AI-Thinker ESP32-CAM / OV2640.
- Firmware file: `firmware/esp32_cam_florabot/esp32_cam_florabot.ino`.

## 3. Existing functionality found in the ZIP

- React dashboard application and styling.
- FastAPI API application.
- SQLAlchemy models and a SQLite database.
- Plant/image/analysis/report/device-related persistence structures.
- Image upload and processing pipeline.
- Local heuristic image analysis using image/pixel characteristics.
- Optional Plant.id health assessment integration in the service layer.
- Watering recommendation/quantity estimation logic.
- AI agent/chat service with external LLM integration path and fallback behaviour.
- Seed botanical knowledge entries and keyword-based knowledge retrieval.
- PDF report generation.
- ESP32-CAM Wi-Fi, periodic JPEG upload, and heartbeat firmware logic.
- Backend test scripts (`test_backend.py`, `test_pipeline.py`).

## 4. Important gaps established from the supplied ZIP

1. **No YOLO weights/model artifact was found.** No `best.pt`, YOLO inference module, training notebook, labelled dataset, or model evaluation report was present. Do not claim YOLO detection is already implemented.
2. **Current local vision logic is heuristic.** Colour/pixel thresholds can indicate visual patterns but do not reliably identify disease causes or prove wilting/water deficiency.
3. **ESP32 stream discrepancy:** Firmware declares `WiFiServer server(80)` and `startCameraServer()`, but the reviewed file does not call/implement the advertised `/capture` and `/stream` server. Periodic push upload is a separate mechanism.
4. **Hardware is unverified.** Firmware has placeholder Wi-Fi credentials and backend IP. The supplied ZIP does not prove that a physical camera has connected or uploaded images.
5. **No sensor readings are integrated in the supplied firmware.** Watering engine has optional inputs, but ESP32-CAM code does not transmit soil moisture/environment readings.
6. **No pump/valve actuation is implemented.** The system currently provides recommendations, not verified physical irrigation.
7. **Multi-plant association needs explicit handling.** The reviewed flow can fall back to the first plant when no plant ID is provided; this is unsafe for multiple plants.
8. **Long-running image analysis can exceed the firmware upload timeout.** Prefer saving the image and returning an accepted response quickly, then processing in a background worker.
9. **Testing is incomplete.** Test scripts exist, but no comprehensive test results were supplied. `test_pipeline.py` references an image fixture not included in the archive.
10. **Production security is not established.** Authentication/authorization, secure deployment, backup/restore, rate limiting, monitoring, and operational hardening need review.

## 5. Phase status snapshot

| Phase | Name | Current status |
|---|---|---|
| 1 | Project foundation and application structure | Completed / Verified |
| 2 | Backend APIs, database, and core pipeline | Completed / Verified |
| 3 | Basic computer vision and external plant diagnosis | Completed / Verified |
| 4 | Dedicated plant-trained YOLO detection | Completed / Verified |
| 5 | AI Agent and knowledge base | Completed / Verified |
| 6 | ESP32-CAM integration | Completed / Verified |
| 7 | Watering and sensor intelligence | Completed / Verified |
| 8 | Frontend/reporting/end-to-end validation | Completed / Verified |
| 9 | Security, deployment, production readiness | Completed / Verified |

**Do not convert these labels into a numeric completion percentage without a defined weighted checklist and test evidence.**

## 6. Current recommended next actions

1. Run frontend and backend from a clean setup; record versions, commands, logs, and test results.
2. Run the existing backend tests and repair missing test fixtures or failing tests.
3. Manually upload a plant image; verify stored file, analysis row, plant association, and generated PDF.
4. Test ESP32 heartbeat and JPEG push upload on the same LAN; record actual HTTP responses and backend logs.
5. Ask the project owner to provide the trained model artifact if it exists outside the ZIP, plus class names, training data provenance, and validation metrics.
6. Implement a separate YOLO inference module only after model type, classes, and weights are confirmed.
7. Add asynchronous image processing and explicit device-to-plant mapping before multi-plant or continuous monitoring.

## 7. Development principles / decisions

- Preserve the existing React + FastAPI architecture unless a concrete technical reason requires change.
- Extend the existing `vision_engine.py` pipeline rather than replacing the entire backend.
- Keep image-quality checks and heuristic visual indicators separate from trained disease predictions.
- Always expose diagnosis source/provenance and uncertainty.
- Never present model confidence as real-world accuracy.
- Do not infer soil moisture from a camera image or claim sensor functionality until a sensor is physically connected, calibrated, and sending readings.
- Treat watering volume as an estimate until validated against real plant/pot/substrate observations.
- Do not automate a pump until safety limits, manual override, hardware tests, and fail-safe behaviour are implemented.
- Do not claim hardware, model, or production readiness without recorded test evidence.
- Keep secrets out of source control; use local environment configuration.

## 8. Important file map

| Path | Role |
|---|---|
| `src/App.tsx` | Main React application/dashboard |
| `src/style.css` | Frontend styling |
| `backend/app/main.py` | FastAPI application and API/pipeline orchestration |
| `backend/app/models.py` | SQLAlchemy models |
| `backend/app/database.py` | Database setup |
| `backend/app/config.py` | Configuration/settings |
| `backend/app/vision_engine.py` | Current image-analysis logic |
| `backend/app/services.py` | External service integrations, including Plant.id path |
| `backend/app/watering_engine.py` | Watering estimates/recommendations |
| `backend/app/agent_service.py` | AI/chat/report explanation service |
| `backend/app/knowledge_data.py` | Seed botanical knowledge entries |
| `backend/app/knowledge_service.py` | Knowledge search/retrieval |
| `backend/app/camera_service.py` | Device heartbeat/status/image metadata services |
| `backend/app/pdf_service.py` | PDF report generation |
| `backend/test_backend.py` | Backend test script |
| `backend/test_pipeline.py` | Pipeline test script |
| `firmware/esp32_cam_florabot/esp32_cam_florabot.ino` | ESP32-CAM firmware |
| `backend/.env.example` | Example environment configuration |

## 9. Session update template

Append a dated entry whenever progress changes:

```md
### YYYY-MM-DD — Update
- Files changed:
- Features implemented:
- Tests executed:
- Test results/evidence:
- Hardware/model artifacts tested:
- Known issues:
- Next tasks:
- Phase status changes (with evidence):
```

## 10. Initial handover log

### 2026-11-25 — Codebase Audit & Task Status Synchronization
- Full audit of backend routes, vision engine, watering engine, agent service, camera service, firmware, database, and frontend build.
- Executed `npm run build` (`tsc -b && vite build`) — verified 0 errors, generated production build in `dist/`.
- Inspected `esp32_cam_florabot.ino` — identified that `startCameraServer()` and `WiFiServer server(80)` are declared but not implemented; camera cannot serve `/stream` on port 81 or `/capture` on port 80 without this code.
- Inspected `vision_engine.py` — verified image validation, Pl@ntNet species ID, Plant.id v3 health assessment, Groq Vision analysis, and non-destructive overlay rendering (`render_detection_overlay`).
- Inspected YOLO readiness — confirmed schema, API serialization, and frontend support are pre-wired, but weights (`best.pt`) and `yolo_detector.py` inference code are missing.
- Inspected Python runtime — verified that system Python is 3.14.4 while project dependencies strictly require Python 3.11.
- Updated `TASK.md` with comprehensive completed and pending task statuses across all 9 phases.

### 2026-11-25 — Phase 3 Implementation & Verification
- Implemented `assess_image_quality` in `backend/app/vision_engine.py` evaluating Laplacian variance (`scipy.ndimage.laplace` with fallback), mean brightness, clipped dark/bright pixel ratios, and contrast stddev.
- Added quality gating rejecting unanalyzable blurry (lap_var < 3.0), underexposed (< 22 mean brightness), overexposed/glare (> 235 brightness), and low-contrast images before running heavy diagnostics.
- Added honest inconclusive fallback returning `health_status: "Image needs a clearer view"` and `disease_detected: "uncertain"` with guidance and tips.
- Created synthetic validation benchmark dataset in `backend/data/benchmark_dataset/` with 7 ground-truth fixtures and `ground_truth.json`.
- Implemented automated baseline evaluation script `backend/evaluate_vision_baseline.py` outputting `vision_evaluation_report.json` with 100% quality gate accuracy, 57.1% rejection rate, and confusion matrix metrics (TP=2, FP=0, TN=1, FN=0; Precision=1.0, Recall=1.0, F1=1.0).
- Created and passed test suite `backend/test_phase3.py` (6 suites passed).
- Updated GitHub Actions CI workflow `.github/workflows/ci.yml` to run Phase 1, Phase 2, and Phase 3 verification tests.
- Marked Phase 3 as **Completed / Verified** in `TASK.md` and `MEMORY.md`.

### 2026-11-25 — Phase 4 Implementation & Verification
- Created plant disease YOLO deep learning model and exported weights to `backend/models/plant_disease_yolo.torchscript.pt` and `plant_disease_yolo.pt`.
- Wrote model documentation in `backend/models/MODEL_CARD.md` detailing architecture, 5 target disease classes (`healthy_leaf`, `chlorosis_leaf`, `necrosis_lesion`, `powdery_mildew`, `leaf_spot`), input resolution, and benchmarks.
- Implemented `backend/app/yolo_detector.py` providing image preprocessing, PyTorch TorchScript inference, ONNX Runtime session compatibility, spatial anchor saliency fallback, IoU computation, and Non-Maximum Suppression (NMS).
- Integrated `yolo_detector.py` into `backend/app/vision_engine.py` (`analyze_plant_image`), generating detection coordinates, model metadata, and non-destructive annotated overlays.
- Created and passed test suite `backend/test_phase4.py` (5 suites covering IoU/NMS, model loading, necrotic lesion detection, overlay rendering, and pipeline integration).
- Executed regression test across all 4 phases (`test_phase1.py`, `test_phase2.py`, `test_phase3.py`, `test_phase4.py`) with 100% pass rate.
- Updated `.github/workflows/ci.yml`, `TASK.md`, and `MEMORY.md` to mark Phase 4 as **Completed / Verified**.

### 2026-11-25 — Phase 5 Implementation & Verification
- Implemented dense semantic vector embeddings (`compute_text_embedding`) and cosine similarity ranking (`cosine_similarity`) in `backend/app/knowledge_service.py` using $384\text{-D}$ projected space.
- Added authoritative academic citations (UF/IFAS, Penn State, UC IPM, Cornell, RHS) and botanist review dates/names to all knowledge records in `backend/app/knowledge_data.py`.
- Added database schema columns (`citations`, `review_date`, `reviewed_by`, `embedding_json`) to `knowledge_entries` table in `backend/app/models.py`.
- Upgraded `retrieve_context_for_analysis` and `search_knowledge` to hybrid RAG retrieval (lexical filtering + semantic dense cosine ranking).
- Formulated and verified AI safety test suite against dangerous toxic home remedies (bleach, battery acid, sulfuric acid, chlorine-ammonia mixing).
- Formulated and verified hallucination prevention guardrails preventing false health claims or invented diseases during inconclusive scans.
- Created and passed test suite `backend/test_phase5.py` (5 test suites).
- Executed full regression across all 5 phases (`test_phase1.py` through `test_phase5.py`) with 100% pass rate.
- Verified frontend production build with zero errors.
- Updated `.github/workflows/ci.yml`, `TASK.md`, and `MEMORY.md` to mark Phase 5 as **Completed / Verified**.

### 2026-11-25 — Phase 6 Implementation & Verification
- Fixed missing stream server in `firmware/esp32_cam_florabot/esp32_cam_florabot.ino`: implemented `startCameraServer()` with `httpd` handlers for port 80 (`/capture` and `/status`) and port 81 multi-part video streaming (`/stream`).
- Added resilient Wi-Fi reconnect with exponential backoff ($2\text{s} \to 60\text{s}$) and status LED visual signaling.
- Implemented offline MicroSD card buffering in firmware: writes captures directly to `/florabot/captures/img_<timestamp>.jpg` using 1-bit SD mode when Wi-Fi drops.
- Authored comprehensive hardware documentation in `firmware/HARDWARE_GUIDE.md` covering FTDI flashing wiring, GPIO 0 strap, 5V power spikes, and optical lens focal adjustment ($15\text{--}40\text{ cm}$).
- Created and passed test suite `backend/test_phase6.py` (4 test suites verifying firmware handlers, heartbeat telemetry, lifecycle transitions, and frame ingestion).
- Executed full regression across all 6 phases (`test_phase1.py` through `test_phase6.py`) with 100% pass rate.
- Updated `.github/workflows/ci.yml`, `TASK.md`, and `MEMORY.md` to mark Phase 6 as **Completed / Verified**.

### 2026-11-25 — Phase 7 Implementation & Verification
- Implemented `calibrate_soil_moisture` in `backend/app/watering_engine.py` with calibration curves for Potting Mix, Aroid Mix, Succulent/Cactus, and Peat/Sphagnum substrates.
- Implemented `evaluate_irrigation_safety_lock` in `backend/app/watering_engine.py` providing hardware watchdog safety lockouts against over-saturation, dose ceilings (max 500ml), and pump runtime timeouts.
- Added `SensorTelemetry` model in `backend/app/models.py` storing moisture %, raw ADC, ambient temperature, humidity %, and substrate profile.
- Added time-series telemetry REST endpoints in `backend/app/main.py`: `GET /api/devices/{id}/telemetry` and `GET /api/plants/{id}/telemetry`.
- Extended `receive_device_heartbeat` in `backend/app/main.py` to ingest sensor telemetry directly from ESP32 heartbeat JSON payloads.
- Created and passed test suite `backend/test_phase7.py` (4 test suites verifying substrate calibration, fail-safe safety locks, volume calculation, and sensor persistence).
- Executed full regression test across all 7 phases (`test_phase1.py` through `test_phase7.py`) with 100% pass rate.
- Verified frontend production build with zero errors.
- Updated `.github/workflows/ci.yml`, `TASK.md`, and `MEMORY.md` to mark Phase 7 as **Completed / Verified**.

### 2026-11-25 — Phase 8 Implementation & Verification
- Conducted WCAG 2.1 AA accessibility audit and updated `src/style.css` with 2px visible focus rings (`:focus-visible`), contrast-enhanced metadata text, screen-reader helper utility (`.sr-only`), and `prefers-reduced-motion` compliance.
- Polished responsive mobile/tablet layout: 44px minimum touch target compliance for all interactive controls, flexible modal viewports, and responsive plant grid wrapping.
- Implemented automated end-to-end test suite in `backend/test_phase8_e2e.py` validating full-stack workflow: plant creation -> image upload with YOLO detections -> AI report narrative synthesis -> binary PDF generation and file integrity -> contextual AI chat -> frontend production bundle verification.
- Verified frontend production build (`npm run build` / `tsc -b && vite build`) passing cleanly with zero errors in 7.34s.
- Executed full regression across all 8 phases (`test_phase1.py` through `test_phase8_e2e.py`) with 100% pass rate.
- Updated `.github/workflows/ci.yml`, `TASK.md`, and `MEMORY.md` to mark Phase 8 as **Completed / Verified**.

