# FloraBOT — Complete Project Plan and Phase Definition

**Version:** 1.0  
**Last updated:** 2026-11-25  
**Baseline:** Supplied `FLORABOT-main.zip` source review.

## 1. Project overview

FloraBOT is intended to be a plant-monitoring and care-support system. The current source combines a React dashboard, FastAPI backend, SQLite/SQLAlchemy persistence, image analysis, optional Plant.id integration, watering recommendations, an AI/chat service, a botanical knowledge base, PDF reports, and ESP32-CAM firmware for periodic image capture and upload.

The intended product flow is:

1. A user registers/selects a plant and its growing context.
2. An ESP32-CAM or user upload provides a plant image.
3. The backend validates and stores the image.
4. Image analysis identifies visible conditions and, once integrated, runs a plant-trained detection model.
5. The system combines model results with plant profile and verified sensor readings (if sensors are installed).
6. The knowledge/recommendation layer creates cautious care guidance.
7. The dashboard presents results, history, device status, and reports.
8. A PDF report records the assessment and recommendations.

**Scope boundary:** The supplied source does not yet establish reliable autonomous watering. The current watering engine produces recommendations/estimates; the supplied ESP32-CAM firmware does not contain sensor acquisition or pump/valve control.

## 2. Project objectives

- Provide a usable web interface for plant profiles and monitoring.
- Receive and store images from manual uploads and ESP32-CAM devices.
- Provide transparent plant-health assessment with uncertainty and provenance.
- Integrate a trained plant-specific model when weights and evaluation evidence are available.
- Generate species-aware care guidance using curated botanical references.
- Provide watering estimates and later incorporate calibrated sensor measurements.
- Maintain plant/device/image/analysis/report history.
- Generate useful PDF reports.
- Validate reliability, safety, and deployment readiness before public release.

## 3. Architecture

```text
ESP32-CAM / Manual Upload
          |
          v
FastAPI Image Ingestion API
          |
          +----> Image Storage + Database Metadata
          |
          v
Background Analysis Worker (recommended)
          |
          +----> Image Quality Checks
          +----> Local Visual Heuristics
          +----> Plant-trained YOLO (to be integrated)
          +----> Optional Plant.id service
          |
          v
Analysis Result + Plant/Device Context
          |
          +----> Knowledge Retrieval
          +----> Watering Recommendation Engine
          +----> AI Explanation / Report Service
          |
          v
Database + PDF Report
          |
          v
React Dashboard / Monitoring History
```

### Main technologies in the supplied project

- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts, lucide-react.
- Backend: Python, FastAPI, SQLAlchemy.
- Database: SQLite in the supplied project snapshot.
- Vision: local image heuristics and optional Plant.id API integration.
- AI services: external LLM integration path and fallback in the agent service.
- Hardware: ESP32-CAM / OV2640 firmware.
- Reports: PDF generation using ReportLab.

## 4. Phase roadmap

## Phase 1 — Foundation and environment setup

**Goal:** Establish a reproducible working development environment and understand the existing application.

**Source baseline:** React/TypeScript/Vite frontend, FastAPI backend, configuration, dependencies, README, and startup helper are present.

**Work:**
- Install and pin compatible dependencies.
- Configure environment variables safely.
- Start backend and frontend independently.
- Confirm frontend/backend connectivity.
- Check build/type errors and startup logs.
- Document developer setup and LAN configuration.

**Deliverables:** Reproducible setup guide, successful frontend build, backend startup evidence.

**Acceptance:** Fresh environment can start both applications and the frontend can call the backend.

**Current status:** Implemented in source; runtime verification pending.

## Phase 2 — Backend, API, database, and ingestion pipeline

**Goal:** Make the data path reliable from image ingestion through persisted analysis and report.

**Source baseline:** FastAPI application, SQLAlchemy models, SQLite database, camera service, image/report services, and pipeline orchestration are present.

**Work:**
- Verify all API routes and validation.
- Verify image storage and metadata.
- Verify plant/device/image/analysis/report relationships.
- Use explicit plant assignment for every image.
- Add database migrations and backup/restore.
- Move long-running model/API processing into a background worker with job status and retry policy.
- Add request and upload limits.

**Deliverables:** API tests, data-flow test, migration/backup process, asynchronous processing design.

**Acceptance:** Image upload receives a quick acknowledgement, processing status is tracked, and results are stored against the correct plant/device.

**Current status:** Implemented in source; verification and hardening pending.

## Phase 3 — Image quality and baseline plant-health assessment

**Goal:** Keep useful baseline image checks while clearly limiting what heuristics can claim.

**Source baseline:** `vision_engine.py` contains image/pixel-based heuristics; `services.py` contains an optional Plant.id health assessment integration path.

**Work:**
- Add blur, exposure, framing, and resolution checks.
- Separate visual symptoms from disease diagnosis.
- Make result provenance explicit.
- Handle API timeout, quota, authentication, and invalid response cases.
- Build a labelled test set and measure performance.
- Return inconclusive results when evidence is insufficient.

**Deliverables:** Image quality module, baseline evaluation report, robust external-service handling.

**Acceptance:** The system does not overstate what colour/pixel heuristics can identify; test performance and failure states are documented.

**Current status:** Partially implemented.

## Phase 4 — Plant-trained YOLO detection

**Goal:** Add a reproducible model-based detection capability for defined plant disease/condition classes.

**Source baseline:** No YOLO weights, inference module, training notebook, dataset, or evaluation report was found in the supplied ZIP.

**Prerequisites:** Model weights, model architecture/task, class names, dataset provenance, licence, and held-out evaluation data must be supplied/confirmed.

**Work:**
- Define classes and annotation rules.
- Audit dataset quality and avoid leakage between train/validation/test splits.
- Train or obtain the model and preserve training configuration.
- Implement model loading/inference as a separate service/module.
- Return class, confidence, bounding boxes/masks, model version, and inference metadata.
- Generate annotated images.
- Evaluate class-wise precision/recall/F1 and mAP as appropriate.
- Benchmark inference latency on target hardware/server.
- Add uncertainty and no-detection handling.

**Deliverables:** Versioned model artifact, inference module, annotated result, evaluation report, model card.

**Acceptance:** Reproducible inference and documented held-out evaluation; UI/API displays detections without presenting confidence as accuracy.

**Current status:** Not found in supplied ZIP; pending model artifact and integration.

## Phase 5 — Knowledge base and AI assistant

**Goal:** Provide explanations and care guidance grounded in verified plant data and trusted references.

**Source baseline:** Agent/chat service, external LLM path with fallback, seed knowledge entries, keyword search/retrieval, and pipeline integration are present.

**Work:**
- Audit botanical entries and attach source URLs, authors/organizations, and review dates.
- Improve retrieval relevance and evidence inclusion.
- Ground answers in plant profile, analysis, and actual sensor readings only.
- Distinguish model findings from generated explanations.
- Add uncertainty, safety, and escalation language.
- Test unsupported questions, conflicting evidence, and unavailable LLM/API behaviour.

**Deliverables:** Curated knowledge library, grounded agent prompts/context, test suite for answer quality.

**Acceptance:** Recommendations can be traced to evidence and the assistant clearly states when data is missing or uncertain.

**Current status:** Partially implemented.

## Phase 6 — ESP32-CAM device integration

**Goal:** Reliably connect the physical camera to the backend and map images to the correct plant.

**Source baseline:** Firmware includes AI-Thinker camera setup, Wi-Fi, periodic JPEG push upload, and heartbeat requests. Backend has device registration/heartbeat/status/image metadata services.

**Work:**
- Configure Wi-Fi and backend host for the deployment network.
- Flash and test the physical board.
- Verify heartbeat, image upload, JPEG dimensions, and stored metadata.
- Implement `/capture` and `/stream` server if required; the supplied firmware advertises these but does not demonstrate their implementation/call.
- Add retries, reconnect handling, and upload acknowledgement.
- Add explicit plant-device assignment/provisioning.
- Keep ingestion response fast and analysis asynchronous.
- Verify online/stale/offline status transitions.

**Deliverables:** Tested firmware, device setup guide, integration test evidence, device-to-plant mapping.

**Acceptance:** Real hardware reliably uploads images and heartbeat; the correct plant receives each image.

**Current status:** Firmware implemented; physical verification and stream functionality pending.

## Phase 7 — Watering and sensor intelligence

**Goal:** Progress from estimated advice to evidence-based recommendations, with optional sensor integration.

**Source baseline:** Watering engine uses plant/pot/soil/health context and optional sensor inputs to estimate watering. Supplied ESP32-CAM firmware does not read sensors and no pump/valve actuation is present.

**Work:**
- Document assumptions behind current water estimates.
- Avoid equating visible wilting with dry soil.
- Select and integrate suitable soil-moisture/environment sensors if required.
- Calibrate sensors for substrate and installation.
- Add timestamped sensor payloads and history.
- Validate stale, missing, and implausible readings.
- Validate recommendation rules against real plant outcomes.
- Treat pump control as a separate future scope with manual override and fail-safe controls.

**Deliverables:** Validated recommendation rules, sensor integration (if in scope), calibration guide, safety requirements.

**Acceptance:** Measured readings are distinguished from estimates; recommendations have test evidence. No automatic watering until actuation is independently safety-tested.

**Current status:** Partially implemented; sensor and actuator integration not found.

## Phase 8 — Frontend, reports, and end-to-end validation

**Goal:** Deliver a consistent user experience from plant setup to analysis history and reporting.

**Source baseline:** React dashboard and styling exist; PDF report generation exists.

**Work:**
- Verify all screens use real API data.
- Add clear loading, error, empty, stale-device, and inconclusive states.
- Display annotated detections, model provenance, confidence, and timestamps.
- Show device status and last successful image.
- Verify history and reports across multiple plants.
- Check PDF output against stored analysis.
- Add frontend and end-to-end automated tests.
- Test responsive layouts and accessibility.

**Deliverables:** Validated dashboard flows, test reports, consistent PDF output.

**Acceptance:** User can create/select a plant, receive an image, inspect a traceable assessment, view history, and download the matching report.

**Current status:** UI and PDF code present; end-to-end validation pending.

## Phase 9 — Security, deployment, and release

**Goal:** Prepare the system for reliable use outside local development.

**Source baseline:** Production security and deployment readiness are not demonstrated by the supplied archive.

**Work:**
- Add authentication and authorization.
- Secure secrets and rotate credentials if exposed.
- Configure HTTPS/reverse proxy and restrict network access.
- Enforce upload limits, content validation, safe storage, and rate limiting.
- Select production database and migration strategy.
- Add backup/restore, logging, metrics, monitoring, and alerting.
- Add deployment automation, rollback, and release checklist.
- Conduct security, load, and recovery tests.

**Deliverables:** Deployment guide, secure configuration, monitoring/backup plan, release evidence.

**Acceptance:** Reproducible secured deployment with tested backup and recovery.

**Current status:** Pending.

## 5. Cross-phase requirements

### Data and traceability
- Every image, analysis, report, and sensor reading must have timestamps and correct plant/device association.
- Store model name/version and diagnosis source with every model-backed analysis.
- Store units and calibration metadata for sensor readings.
- Keep raw image and annotated image references distinct.

### Reliability
- Image ingestion should not wait for slow external inference.
- Retry transient network failures with bounded backoff.
- Avoid duplicate processing when devices retry uploads; use an idempotency identifier where appropriate.
- Preserve error states and processing history.

### AI quality
- Maintain a held-out evaluation set.
- Report class-wise metrics, not only a single aggregate score.
- Evaluate across lighting, background, camera distance, leaf orientation, species, and disease stage.
- Return `inconclusive` where evidence is insufficient.
- Never represent confidence as measured accuracy.

### Safety and claims
- Do not claim soil moisture is measured unless a calibrated sensor supplies the reading.
- Do not claim watering is automated unless pump/valve hardware and control logic are implemented and tested.
- Do not diagnose a disease solely from leaf colour thresholds.
- Do not recommend treatment without considering uncertainty, plant species, and reference quality.

## 6. Recommended milestone sequence

1. **Milestone A — Baseline works:** clean startup, build, API, database, and manual image-to-report flow.
2. **Milestone B — Hardware data path works:** physical ESP32 heartbeat and image upload with correct plant mapping.
3. **Milestone C — Validated vision:** image quality checks, model artifact, inference, annotated images, and evaluation.
4. **Milestone D — Grounded plant intelligence:** curated knowledge, safe agent responses, and validated watering guidance.
5. **Milestone E — Complete user workflow:** dashboard, history, reports, and end-to-end tests.
6. **Milestone F — Release-ready:** authentication, deployment, monitoring, backups, security and recovery validation.

## 7. Current project position

Based on the supplied source snapshot only:
- The foundation and much of the application/backend structure are present.
- Basic image-analysis and external Plant.id integration paths are present.
- AI agent/knowledge and watering recommendation components are present but require validation and improvement.
- A dedicated YOLO pipeline is not present in the archive.
- ESP32-CAM firmware is present, but physical operation is unverified and advertised stream endpoints are not implemented in the reviewed firmware.
- Sensor-based watering and pump actuation are not demonstrated.
- Full end-to-end testing and production deployment are pending.

**Recommended immediate action:** Run the existing project and establish a tested baseline before making architectural changes. Then confirm whether a trained YOLO model exists outside the ZIP. Do not start model integration by guessing the model classes or artifact format.

## 8. Project change log

- **2026-11-25:** Initial roadmap created from the supplied project ZIP review. Statuses reflect code presence only where noted; no runtime, model, or physical hardware verification was performed during the review.
