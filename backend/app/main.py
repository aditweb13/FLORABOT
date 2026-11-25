import asyncio
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import List, Optional
import httpx
from fastapi import FastAPI, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import Base, engine, get_db
from .vision_engine import validate_image_bytes, save_validated_image, analyze_plant_image, render_detection_overlay
from .watering_engine import calculate_watering_recommendation
from .knowledge_service import seed_knowledge_base, search_knowledge, retrieve_context_for_analysis
from .agent_service import generate_agent_report_data, generate_chat_reply
from .camera_service import (
    get_or_create_device, record_device_heartbeat, update_device_statuses,
    record_received_camera_image
)
from .pdf_service import build_pdf_report
from .auth import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_api_key, get_current_user, require_role, verify_device_api_key, log_audit_event
)
from .monitoring import ProductionSecurityMiddleware, metrics_registry

# Ensure directories & database tables exist
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
Path(settings.report_dir).mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)
# Forward-compatible SQLite additions for existing databases (create_all does not add columns).
if engine.url.get_backend_name() == "sqlite":
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(analyses)")}
        if "detection_data_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE analyses ADD COLUMN detection_data_json TEXT NOT NULL DEFAULT '[]'")
        if "identification_candidates_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE analyses ADD COLUMN identification_candidates_json TEXT NOT NULL DEFAULT '[]'")
        if "detection_model_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE analyses ADD COLUMN detection_model_json TEXT NOT NULL DEFAULT '{}'")
        if "annotated_image_path" not in cols:
            conn.exec_driver_sql("ALTER TABLE analyses ADD COLUMN annotated_image_path TEXT")
        if "diagnostic_error" not in cols:
            conn.exec_driver_sql("ALTER TABLE analyses ADD COLUMN diagnostic_error TEXT NOT NULL DEFAULT ''")

# Seed knowledge base
with engine.connect() as conn:
    with Session(bind=conn) as init_db:
        seed_knowledge_base(init_db)

app = FastAPI(title="FloraBOT AI API", version="2.0.0", description="Intelligent Indoor Plant Monitoring & Diagnostic API")

cors_origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
if "*" not in cors_origins and not cors_origins:
    cors_origins = ["*"]

app.add_middleware(ProductionSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# -------------------------------------------------------------
# Helpers & Serializers
# -------------------------------------------------------------
def image_url(path: Optional[str]) -> Optional[str]:
    return f"/files/{Path(path).name}" if path else None

def serialize_analysis(a: models.Analysis) -> dict:
    return {
        "id": a.id,
        "image_id": a.image_id,
        "plant_id": a.plant_id,
        "device_id": a.device_id,
        "image": image_url(a.image),
        "timestamp": a.timestamp,
        "plant_identification": a.plant_identification,
        "plant_confidence": a.plant_confidence,
        "disease_detected": a.disease_detected,
        "disease_name": a.disease_name,
        "disease_confidence": a.disease_confidence,
        "severity": a.severity,
        "health_status": a.health_status,
        "confidence": a.confidence,
        "symptoms": a.symptoms,
        "recommendations": a.recommendations,
        "prevention": a.prevention,
        "recovery_plan": a.recovery_plan,
        "stress_status": a.stress_status,
        "stress_observations": a.stress_observations,
        "watering_status": a.watering_status,
        "watering_quantity_ml": a.watering_quantity_ml,
        "watering_reason": a.watering_reason,
        "watering_instructions": a.watering_instructions,
        "provider_engine": a.provider_engine,
        "provider_reference": a.provider_reference,
        "detections": json.loads(a.detection_data_json or "[]"),
        "detection_model": json.loads(a.detection_model_json or "{}"),
        "identification_candidates": json.loads(a.identification_candidates_json or "[]"),
        "original_image": image_url(a.image),
        "annotated_image": image_url(a.annotated_image_path),
        "plant_name": a.plant.name if a.plant else "Unknown Plant"
    }

def serialize_plant(p: models.Plant, detail: bool = False) -> dict:
    latest = max(p.analyses, key=lambda a: a.timestamp) if p.analyses else None
    data = {
        "id": p.id,
        "name": p.name,
        "species": p.species,
        "category": p.category,
        "image": image_url(p.image),
        "registered_at": p.registered_at,
        "location": p.location,
        "notes": p.notes,
        "health_status": p.health_status,
        "pot_size_cm": p.pot_size_cm,
        "soil_type": p.soil_type,
        "watering_frequency_days": p.watering_frequency_days,
        "scan_count": len(p.analyses),
        "last_scan": latest.timestamp if latest else None,
        "latest_analysis": serialize_analysis(latest) if latest else None
    }
    if detail:
        data["analyses"] = [serialize_analysis(a) for a in sorted(p.analyses, key=lambda x: x.timestamp, reverse=True)]
        data["reports"] = [
            {
                "id": r.id,
                "created_at": r.created_at,
                "download_url": f"/api/reports/{r.id}/download",
                "analysis_id": r.analysis_id
            }
            for r in sorted(p.reports, key=lambda x: x.created_at, reverse=True)
        ]
    return data

def execute_plant_analysis_pipeline(
    db: Session,
    plant: Optional[models.Plant],
    image_path: str,
    device: Optional[models.Device] = None,
    cam_img: Optional[models.CameraImage] = None
) -> models.Analysis:
    """Core image processing, computer vision, watering engine, and report pipeline."""
    # 1. Vision & Disease Analysis
    vis_res = analyze_plant_image(image_path, plant_hint=plant.species if plant else None)
    # Attach to a recent observation from the same physical camera only when the
    # identity agrees; otherwise discover a new plant rather than merging by species.
    if plant is None and device:
        prior = db.query(models.CameraImage).filter(
            models.CameraImage.device_id == device.id,
            models.CameraImage.plant_id.isnot(None)
        ).order_by(models.CameraImage.timestamp.desc()).first()
        identified = (vis_res.get("plant_identification") or "").strip().casefold()
        if prior and prior.plant and identified and identified not in {"unknown", "unknown plant"}:
            prior_species = (prior.plant.species or "").strip().casefold()
            if prior_species == identified:
                plant = prior.plant
    if plant is None:
        identified = vis_res.get("plant_identification") or "Unknown Plant"
        plant = models.Plant(
            name=f"Discovered Plant {datetime.now().strftime('%Y%m%d-%H%M%S')}",
            species=identified,
            category="Houseplant",
            health_status="Unscanned",
            image=image_url(image_path),
        )
        db.add(plant)
        db.flush()
        if cam_img:
            cam_img.plant_id = plant.id

    annotated_path = None
    if vis_res.get("detections"):
        try:
            annotated_name = f"{Path(image_path).stem}-annotated.jpg"
            annotated_path = render_detection_overlay(
                image_path,
                vis_res["detections"],
                str(Path(settings.upload_dir) / annotated_name),
            )
        except Exception as exc:
            print(f"Could not create derived annotated image: {type(exc).__name__}: {exc}")

    # 2. Watering Recommendation Engine
    water_res = calculate_watering_recommendation(
        species=vis_res.get("plant_identification") or plant.species,
        health_status=vis_res.get("health_status", "Healthy"),
        stress_status=vis_res.get("stress_status", "None"),
        pot_size_cm=plant.pot_size_cm,
        soil_type=plant.soil_type
    )

    # 3. Create Analysis Record
    analysis = models.Analysis(
        image_id=cam_img.id if cam_img else None,
        plant_id=plant.id,
        device_id=device.id if device else None,
        image=image_path,
        timestamp=datetime.now(timezone.utc),
        plant_identification=vis_res.get("plant_identification", plant.species),
        plant_confidence=vis_res.get("plant_confidence"),
        disease_detected=vis_res.get("disease_detected", "uncertain"),
        disease_name=vis_res.get("disease_name", ""),
        disease_confidence=vis_res.get("disease_confidence"),
        severity=vis_res.get("severity", ""),
        health_status=vis_res.get("health_status", "Inconclusive"),
        confidence=vis_res.get("confidence"),
        symptoms=vis_res.get("symptoms", ""),
        recommendations=vis_res.get("recommendations", ""),
        prevention=vis_res.get("prevention", ""),
        recovery_plan=vis_res.get("recovery_plan", ""),
        stress_status=vis_res.get("stress_status", "None"),
        stress_observations=vis_res.get("stress_observations", ""),
        watering_status=water_res.get("watering_status", "Watering condition uncertain"),
        watering_quantity_ml=water_res.get("watering_quantity_ml"),
        watering_reason=water_res.get("watering_reason", ""),
        watering_instructions=water_res.get("watering_instructions", ""),
        provider_engine=vis_res.get("provider_engine", "FloraBOT Vision Engine"),
        provider_reference=vis_res.get("provider_reference", ""),
        diagnostic_error=vis_res.get("diagnostic_error", ""),
        detection_data_json=json.dumps(vis_res.get("detections", [])),
        detection_model_json=json.dumps(vis_res.get("model_metadata", {})),
        identification_candidates_json=json.dumps(vis_res.get("identification_candidates", [])),
        annotated_image_path=annotated_path
    )
    db.add(analysis)

    # Update plant state
    plant.health_status = analysis.health_status
    if plant.species in ("Unknown", "Unknown Plant", "") and analysis.plant_identification not in ("Unknown", "Unknown Plant", ""):
        plant.species = analysis.plant_identification

    if cam_img:
        cam_img.processing_status = "completed"

    db.commit()
    db.refresh(analysis)

    # 4. Automatic Report Generation
    knowledge = retrieve_context_for_analysis(
        db,
        plant_species=analysis.plant_identification or plant.species,
        disease_name=analysis.disease_name,
        health_status=analysis.health_status
    )
    report_data = generate_agent_report_data(plant, analysis, knowledge)
    pdf_filename = f"flora-report-{plant.id}-{analysis.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    pdf_path = str(Path(settings.report_dir) / pdf_filename)
    
    try:
        build_pdf_report(plant, analysis, report_data, pdf_path)
    except Exception as exc:
        print(f"Error generating PDF report: {exc}")

    report = models.Report(
        plant_id=plant.id,
        analysis_id=analysis.id,
        report_data_json=json.dumps(report_data),
        file_path=pdf_path,
        created_at=datetime.now(timezone.utc)
    )
    db.add(report)
    db.commit()

    return analysis

# -------------------------------------------------------------
# Static File Delivery
# -------------------------------------------------------------
@app.get("/files/{filename}")
def get_file(filename: str):
    safe_name = Path(filename).name
    for root in (settings.upload_dir, settings.report_dir):
        candidate = Path(root) / safe_name
        if candidate.is_file():
            media = "application/pdf" if safe_name.lower().endswith(".pdf") else "image/jpeg"
            return FileResponse(candidate, media_type=media)
    raise HTTPException(404, "Requested file was not found on the server.")

# -------------------------------------------------------------
# System & Status Endpoints
# -------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = ""
    role: Optional[str] = "operator"

class UserLoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user_id: int
    username: str
    role: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    api_key: Optional[str] = None
    created_at: datetime

@app.post("/api/auth/register", response_model=UserResponse)
def register_user(payload: UserRegisterRequest, request: Request, db: Session = Depends(get_db)):
    if len(payload.username.strip()) < 3:
        raise HTTPException(400, "Username must be at least 3 characters.")
    if len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    
    existing = db.query(models.User).filter(
        (models.User.username == payload.username.strip()) | (models.User.email == payload.email.strip().lower())
    ).first()
    if existing:
        raise HTTPException(409, "Username or email is already registered.")
    
    role = payload.role if payload.role in ["admin", "operator", "viewer"] else "operator"
    hashed = hash_password(payload.password)
    new_user = models.User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        hashed_password=hashed,
        full_name=payload.full_name or "",
        role=role,
        is_active=True,
        api_key=generate_api_key()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    client_ip = request.client.host if request.client else "127.0.0.1"
    log_audit_event(db, new_user.username, "USER_REGISTERED", f"user:{new_user.id}", {"role": role}, client_ip)
    
    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        is_active=new_user.is_active,
        api_key=new_user.api_key,
        created_at=new_user.created_at
    )

@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(payload: UserLoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid username or password credentials.")
    if not user.is_active:
        raise HTTPException(403, "Account has been deactivated.")
    
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    token = create_access_token({
        "sub": user.username,
        "user_id": user.id,
        "role": user.role
    })
    
    client_ip = request.client.host if request.client else "127.0.0.1"
    log_audit_event(db, user.username, "USER_LOGGED_IN", f"user:{user.id}", {}, client_ip)
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=settings.jwt_expiration_minutes,
        user_id=user.id,
        username=user.username,
        role=user.role
    )

@app.get("/api/auth/me", response_model=UserResponse)
def get_auth_me(current_user: Optional[models.User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(401, "Not authenticated.")
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        api_key=current_user.api_key,
        created_at=current_user.created_at
    )

@app.post("/api/auth/api-key")
def rotate_api_key(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user:
        raise HTTPException(401, "Authentication required to generate API key.")
    current_user.api_key = generate_api_key()
    db.commit()
    return {"api_key": current_user.api_key}

@app.get("/api/metrics")
def get_prometheus_metrics(db: Session = Depends(get_db)):
    content = metrics_registry.generate_exposition(db)
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")

@app.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    update_device_statuses(db)
    active_devices = db.query(models.Device).filter(models.Device.status == "online").count()
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "online_devices": active_devices
    }

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    update_device_statuses(db)
    plants = db.query(models.Plant).all()
    devices = db.query(models.Device).all()
    recent_analyses = db.query(models.Analysis).order_by(models.Analysis.timestamp.desc()).limit(10).all()
    recent_reports = db.query(models.Report).order_by(models.Report.created_at.desc()).limit(6).all()
    latest_img = db.query(models.CameraImage).order_by(models.CameraImage.timestamp.desc()).first()
    
    healthy_count = sum(1 for p in plants if "healthy" in p.health_status.lower())
    diseased_count = sum(1 for p in plants if "disease" in p.health_status.lower())
    attention_count = sum(1 for p in plants if any(k in p.health_status.lower() for k in ["stress", "wilting", "attention"]))
    unscanned_count = sum(1 for p in plants if p.health_status in ["Unscanned", "Inconclusive"])

    # Online camera status
    cam_online = any(d.status == "online" for d in devices)

    return {
        "total_plants": len(plants),
        "healthy_count": healthy_count,
        "attention_count": attention_count,
        "diseased_count": diseased_count,
        "unscanned_count": unscanned_count,
        "camera_online": cam_online,
        "latest_camera_image": image_url(latest_img.file_path) if latest_img else None,
        "latest_image_time": latest_img.timestamp if latest_img else None,
        "plants": [serialize_plant(p) for p in plants],
        "recent_analyses": [serialize_analysis(a) for a in recent_analyses],
        "recent_reports": [
            {
                "id": r.id,
                "plant_id": r.plant_id,
                "plant_name": r.plant.name if r.plant else "Plant",
                "created_at": r.created_at,
                "download_url": f"/api/reports/{r.id}/download"
            }
            for r in recent_reports
        ],
        "devices": [
            {
                "id": d.id,
                "identifier": d.identifier,
                "name": d.name,
                "status": d.status,
                "ip_address": d.ip_address,
                "last_communication": d.last_communication,
                "last_image_received": d.last_image_received
            }
            for d in devices
        ]
    }

# -------------------------------------------------------------
# ESP32-CAM & Hardware Ingestion Endpoints
# -------------------------------------------------------------
@app.post("/api/devices/{device_id}/images")
@app.post("/api/camera/upload")
async def receive_camera_image(
    request: Request,
    background_tasks: BackgroundTasks,
    device_id: Optional[str] = "esp32-cam-01",
    plant_id: Optional[int] = Form(None),
    query_plant_id: Optional[int] = Query(None, alias="plant_id"),
    image: Optional[UploadFile] = File(None),
    x_device_id: Optional[str] = Header(None),
    x_plant_id: Optional[str] = Header(None),
    async_mode: bool = Query(False),
    x_async: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receives an incoming camera frame directly from ESP32-CAM via HTTP POST.
    Accepts both multipart form upload or raw binary JPEG payload.
    Automatically timestamps, registers to device, and triggers AI analysis pipeline.
    Supports asynchronous fast acknowledgment for hardware devices with short timeouts.
    """
    effective_dev_id = (
        x_device_id if isinstance(x_device_id, str) and x_device_id.strip()
        else (device_id if isinstance(device_id, str) and device_id.strip() else "esp32-cam-01")
    )
    client_ip = request.client.host if request and hasattr(request, "client") and request.client else ""
    device = get_or_create_device(db, identifier=effective_dev_id, ip_address=client_ip)

    # 1. Read bytes from multipart file or raw body safely
    raw_bytes = b""
    if image is not None and hasattr(image, "read"):
        try:
            raw_bytes = await image.read()
        except Exception:
            pass

    if not raw_bytes:
        content_type = request.headers.get("content-type", "").lower()
        if "multipart" in content_type:
            try:
                form = await request.form()
                form_file = form.get("image") or form.get("file")
                if form_file and hasattr(form_file, "read"):
                    raw_bytes = await form_file.read()
                elif isinstance(form_file, (bytes, bytearray)):
                    raw_bytes = bytes(form_file)
                
                # Extract device_id or plant_id from form if passed
                form_dev = form.get("device_id")
                if form_dev and isinstance(form_dev, str) and form_dev.strip():
                    effective_dev_id = form_dev.strip()
                    device = get_or_create_device(db, identifier=effective_dev_id, ip_address=client_ip)
                form_p = form.get("plant_id")
                if form_p and str(form_p).isdigit():
                    plant_id = int(form_p)
            except Exception as exc:
                print(f"Notice: Form read exception (handled): {exc}")

    if not raw_bytes:
        try:
            if hasattr(request, "_body") and isinstance(request._body, (bytes, bytearray)):
                raw_bytes = bytes(request._body)
            elif hasattr(request, "body"):
                body_res = request.body()
                if asyncio.iscoroutine(body_res):
                    raw_bytes = await body_res
                else:
                    raw_bytes = body_res
        except Exception as exc:
            print(f"Notice: Body stream read exception (handled): {exc}")

    if not raw_bytes:
        raise HTTPException(400, "No image payload received in request. Please select an image file to upload.")

    # 2. Validate image format & dimensions
    try:
        pil_img, width, height = validate_image_bytes(raw_bytes)
    except ValueError as val_err:
        raise HTTPException(400, f"Image rejected: {str(val_err)}")

    # 3. Store validated image file
    saved_path = save_validated_image(pil_img, settings.upload_dir)

    # 4. Resolve explicit plant association
    resolved_plant_id = None
    if isinstance(plant_id, int):
        resolved_plant_id = plant_id
    elif isinstance(query_plant_id, int):
        resolved_plant_id = query_plant_id
    elif isinstance(x_plant_id, str) and x_plant_id.strip().isdigit():
        resolved_plant_id = int(x_plant_id.strip())

    if resolved_plant_id is not None:
        target_plant = db.get(models.Plant, resolved_plant_id)
        if not target_plant:
            raise HTTPException(404, f"Target plant with ID {resolved_plant_id} not found.")
    else:
        target_plant = None

    # 5. Record image in DB
    cam_img = record_received_camera_image(
        db,
        device=device,
        plant=target_plant,
        file_path=saved_path,
        file_size=len(raw_bytes),
        width=width,
        height=height
    )

    # Check for asynchronous execution (via query param or X-Async header)
    is_async = (isinstance(async_mode, bool) and async_mode) or (isinstance(x_async, str) and x_async.lower() in ("true", "1", "yes"))
    if is_async:
        cam_img.processing_status = "queued"
        db.commit()

        def _bg_process(img_id: int):
            with Session(bind=engine) as bg_db:
                curr_img = bg_db.get(models.CameraImage, img_id)
                if not curr_img:
                    return
                curr_dev = curr_img.device
                curr_plant = curr_img.plant
                try:
                    curr_img.processing_status = "analyzing"
                    bg_db.commit()
                    execute_plant_analysis_pipeline(
                        bg_db,
                        plant=curr_plant,
                        image_path=curr_img.file_path,
                        device=curr_dev,
                        cam_img=curr_img
                    )
                    curr_img.processing_status = "completed"
                    bg_db.commit()
                except Exception as err:
                    curr_img.processing_status = "failed"
                    curr_img.error_message = str(err)[:290]
                    bg_db.commit()

        background_tasks.add_task(_bg_process, cam_img.id)

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "job_status": "queued",
                "message": "Image received, validated, and queued for asynchronous processing.",
                "image_id": cam_img.id,
                "image_url": image_url(saved_path),
                "device_id": device.identifier,
                "plant_id": target_plant.id if target_plant else None,
                "timestamp": cam_img.timestamp.isoformat() if cam_img.timestamp else None
            }
        )

    # 6. Execute full AI analysis & report generation pipeline synchronously
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        analysis = await run_in_threadpool(execute_plant_analysis_pipeline,
            db,
            plant=target_plant,
            image_path=saved_path,
            device=device,
            cam_img=cam_img
        )
    else:
        analysis = execute_plant_analysis_pipeline(
            db,
            plant=target_plant,
            image_path=saved_path,
            device=device,
            cam_img=cam_img
        )

    return {
        "status": "success",
        "message": "Image received, validated, and analyzed.",
        "image_id": cam_img.id,
        "image_url": image_url(saved_path),
        "device_id": device.identifier,
        "plant_id": analysis.plant_id,
        "analysis_id": analysis.id,
        "health_status": analysis.health_status,
        "timestamp": cam_img.timestamp
    }

@app.post("/api/devices/{device_id}/heartbeat")
@app.post("/api/camera/heartbeat")
async def receive_device_heartbeat(
    device_id: str = "esp32-cam-01",
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Receives periodic heartbeat ping and sensor telemetry from ESP32-CAM device."""
    client_ip = request.client.host if request and request.client else ""
    dev = record_device_heartbeat(db, identifier=device_id, ip_address=client_ip)

    # Ingest sensor telemetry if provided in JSON payload
    try:
        body = await request.json() if request else {}
    except Exception:
        body = {}

    if isinstance(body, dict) and any(k in body for k in ("soil_moisture_pct", "raw_adc", "ambient_temp_c", "humidity_pct")):
        from .watering_engine import calibrate_soil_moisture
        raw_adc = body.get("raw_adc")
        moisture_pct = body.get("soil_moisture_pct")
        substrate = body.get("substrate", "Potting Mix")

        if raw_adc is not None and moisture_pct is None:
            moisture_pct, _ = calibrate_soil_moisture(int(raw_adc), substrate=substrate)

        assigned_plant = dev.analyses[0].plant if dev.analyses else db.query(models.Plant).first()
        plant_id = body.get("plant_id") or (assigned_plant.id if assigned_plant else None)

        telemetry = models.SensorTelemetry(
            device_id=dev.id,
            plant_id=plant_id,
            soil_moisture_pct=float(moisture_pct) if moisture_pct is not None else None,
            raw_adc=int(raw_adc) if raw_adc is not None else None,
            ambient_temp_c=float(body.get("ambient_temp_c")) if body.get("ambient_temp_c") is not None else None,
            humidity_pct=float(body.get("humidity_pct")) if body.get("humidity_pct") is not None else None,
            substrate=substrate,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(telemetry)
        db.commit()

    return {
        "status": "ok",
        "device_id": dev.identifier,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "poll_interval_sec": dev.poll_interval_sec
    }

@app.get("/api/devices/{device_id}/telemetry")
@app.get("/api/plants/{plant_id}/telemetry")
def get_sensor_telemetry(
    device_id: Optional[str] = None,
    plant_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Returns historical sensor time-series telemetry (soil moisture, temperature, humidity)."""
    q = db.query(models.SensorTelemetry)
    if plant_id is not None:
        q = q.filter(models.SensorTelemetry.plant_id == plant_id)
    elif device_id:
        dev = db.query(models.Device).filter(models.Device.identifier == device_id).first()
        if dev:
            q = q.filter(models.SensorTelemetry.device_id == dev.id)

    items = q.order_by(models.SensorTelemetry.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "device_id": t.device_id,
            "plant_id": t.plant_id,
            "soil_moisture_pct": t.soil_moisture_pct,
            "raw_adc": t.raw_adc,
            "ambient_temp_c": t.ambient_temp_c,
            "humidity_pct": t.humidity_pct,
            "substrate": t.substrate,
            "timestamp": t.timestamp
        }
        for t in items
    ]

@app.get("/api/devices")
def list_devices(db: Session = Depends(get_db)):
    update_device_statuses(db)
    devices = db.query(models.Device).all()
    return [
        {
            "id": d.id,
            "identifier": d.identifier,
            "name": d.name,
            "type": d.type,
            "status": d.status,
            "ip_address": d.ip_address,
            "stream_url": d.stream_url or settings.camera_stream_url,
            "snapshot_url": d.snapshot_url or settings.camera_snapshot_url,
            "last_communication": d.last_communication,
            "last_image_received": d.last_image_received,
            "poll_interval_sec": d.poll_interval_sec,
            "is_active": d.is_active,
            "created_at": d.created_at
        }
        for d in devices
    ]

@app.get("/api/devices/{device_id}/logs")
def get_device_logs(device_id: str, limit: int = 50, db: Session = Depends(get_db)):
    dev = db.query(models.Device).filter(models.Device.identifier == device_id).first()
    if not dev:
        try:
            dev = db.get(models.Device, int(device_id))
        except ValueError:
            pass
    if not dev:
        raise HTTPException(404, "Device not found.")
    logs = db.query(models.DeviceLog).filter(models.DeviceLog.device_id == dev.id).order_by(models.DeviceLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "event_type": l.event_type,
            "message": l.message,
            "timestamp": l.timestamp
        }
        for l in logs
    ]

@app.get("/api/camera/stream")
def proxy_camera_stream():
    """Forward the camera's MJPEG stream without polling still images."""
    try:
        client = httpx.Client(timeout=httpx.Timeout(connect=2.0, read=None, write=2.0, pool=2.0), follow_redirects=True)
        upstream = client.send(client.build_request("GET", settings.camera_stream_url), stream=True)
        upstream.raise_for_status()

        def camera_stream():
            try:
                yield from upstream.iter_raw(chunk_size=1024)
            finally:
                upstream.close()
                client.close()

        return StreamingResponse(
            camera_stream(),
            media_type=upstream.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame"),
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    except Exception as exc:
        raise HTTPException(503, f"Live camera stream unavailable: {str(exc)}")


@app.get("/api/camera/snapshot")
def proxy_or_latest_camera_snapshot(
    url: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Proxies live JPEG snapshot from ESP32-CAM if URL is provided and accessible;
    otherwise serves the most recently stored camera frame from the database.
    """
    target_url = url or settings.camera_snapshot_url
    if target_url:
        try:
            with httpx.Client(timeout=6, follow_redirects=True) as client:
                res = client.get(target_url)
                if res.status_code == 200 and res.headers.get("content-type", "").startswith("image/"):
                    return Response(content=res.content, media_type=res.headers["content-type"], headers={"Cache-Control": "no-store"})
        except Exception:
            pass

    # Fall back to latest stored camera image
    latest = db.query(models.CameraImage).order_by(models.CameraImage.timestamp.desc()).first()
    if latest and Path(latest.file_path).is_file():
        return FileResponse(latest.file_path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    raise HTTPException(502, "Camera snapshot is unavailable. Ensure ESP32-CAM is powered and on the same Wi-Fi network.")

@app.get("/api/camera/latest")
def get_latest_camera_frame(db: Session = Depends(get_db)):
    latest = db.query(models.CameraImage).order_by(models.CameraImage.timestamp.desc()).first()
    if not latest:
        return {"has_image": False, "message": "No camera frames received yet."}
    return {
        "has_image": True,
        "id": latest.id,
        "image_url": image_url(latest.file_path),
        "timestamp": latest.timestamp,
        "width": latest.width,
        "height": latest.height,
        "file_size": latest.file_size,
        "plant_id": latest.plant_id,
        "device_id": latest.device_id
    }

@app.post("/api/camera/poll-now")
def trigger_camera_poll(
    plant_id: Optional[int] = None,
    url: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Manually triggers backend to pull a snapshot from ESP32-CAM's HTTP snapshot endpoint,
    validates the frame, stores it, and runs the AI diagnostic pipeline.
    """
    target_url = url or settings.camera_snapshot_url
    if not target_url:
        raise HTTPException(400, "No camera snapshot URL configured. Set CAMERA_SNAPSHOT_URL in Settings.")

    target_plant = db.get(models.Plant, plant_id) if plant_id else None
        
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            res = client.get(target_url)
            res.raise_for_status()
            if not res.headers.get("content-type", "").startswith("image/"):
                raise HTTPException(415, "Target endpoint did not return an image content type.")
            raw_bytes = res.content
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch snapshot from ESP32-CAM at {target_url}: {str(exc)}")

    # Validate image
    pil_img, width, height = validate_image_bytes(raw_bytes)
    saved_path = save_validated_image(pil_img, settings.upload_dir)

    device = get_or_create_device(db, identifier="esp32-cam-01")
    cam_img = record_received_camera_image(
        db, device=device, plant=target_plant,
        file_path=saved_path, file_size=len(raw_bytes), width=width, height=height
    )

    analysis = execute_plant_analysis_pipeline(
        db, plant=target_plant, image_path=saved_path, device=device, cam_img=cam_img
    )

    return {
        "status": "success",
        "image_id": cam_img.id,
        "image_url": image_url(saved_path),
        "analysis_id": analysis.id,
        "health_status": analysis.health_status,
        "watering_status": analysis.watering_status,
        "timestamp": cam_img.timestamp
    }

# -------------------------------------------------------------
# Plant Endpoints
# -------------------------------------------------------------
@app.get("/api/plants")
def list_plants(db: Session = Depends(get_db)):
    plants = db.query(models.Plant).order_by(models.Plant.registered_at.desc()).all()
    return [serialize_plant(p) for p in plants]

@app.post("/api/plants")
async def create_plant(
    name: str = Form(...),
    species: str = Form("Unknown"),
    category: str = Form("Houseplant"),
    location: str = Form(""),
    notes: str = Form(""),
    pot_size_cm: int = Form(15),
    soil_type: str = Form("Potting Mix"),
    watering_frequency_days: int = Form(7),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    saved_img = None
    if image:
        try:
            content = await image.read()
            pil_img, _, _ = validate_image_bytes(content)
            saved_img = save_validated_image(pil_img, settings.upload_dir)
        except ValueError as e:
            raise HTTPException(400, str(e))

    plant = models.Plant(
        name=name.strip(),
        species=species.strip() or "Unknown",
        category=category,
        location=location.strip(),
        notes=notes.strip(),
        pot_size_cm=max(5, min(120, pot_size_cm)),
        soil_type=soil_type.strip() or "Potting Mix",
        watering_frequency_days=watering_frequency_days,
        image=saved_img
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return serialize_plant(plant)

@app.get("/api/plants/{plant_id}")
def get_plant_detail(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(models.Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found.")
    return serialize_plant(plant, detail=True)

@app.patch("/api/plants/{plant_id}")
async def update_plant(
    plant_id: int,
    name: Optional[str] = Form(None),
    species: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    pot_size_cm: Optional[int] = Form(None),
    soil_type: Optional[str] = Form(None),
    watering_frequency_days: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    plant = db.get(models.Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found.")

    if name is not None: plant.name = name.strip()
    if species is not None: plant.species = species.strip()
    if category is not None: plant.category = category
    if location is not None: plant.location = location.strip()
    if notes is not None: plant.notes = notes.strip()
    if pot_size_cm is not None: plant.pot_size_cm = max(5, min(120, pot_size_cm))
    if soil_type is not None: plant.soil_type = soil_type.strip()
    if watering_frequency_days is not None: plant.watering_frequency_days = watering_frequency_days

    if image:
        try:
            content = await image.read()
            pil_img, _, _ = validate_image_bytes(content)
            plant.image = save_validated_image(pil_img, settings.upload_dir)
        except ValueError as e:
            raise HTTPException(400, str(e))

    db.commit()
    db.refresh(plant)
    return serialize_plant(plant, detail=True)

@app.delete("/api/plants/{plant_id}")
def delete_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(models.Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found.")
        
    p_name = plant.name
    image_paths = [x for x in [plant.image, *(a.image for a in plant.analyses)] if x]
    report_paths = [r.file_path for r in plant.reports if r.file_path]

    try:
        # Delete associated conversations
        for convo in db.query(models.Conversation).filter(models.Conversation.plant_id == plant.id).all():
            db.delete(convo)
        db.delete(plant)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Could not delete plant: {str(exc)}")

    # Clean up files safely
    for file_str in image_paths + report_paths:
        try:
            p = Path(file_str).resolve()
            if p.is_file():
                p.unlink()
        except Exception:
            pass

    return {"ok": True, "deleted_id": plant_id, "name": p_name}

# -------------------------------------------------------------
# Analysis Endpoints
# -------------------------------------------------------------
@app.post("/api/plants/{plant_id}/analyze")
async def analyze_uploaded_leaf(
    plant_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Manual leaf photo upload & diagnosis for a specific plant."""
    plant = db.get(models.Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found.")

    try:
        content = await image.read()
        pil_img, w, h = validate_image_bytes(content)
        saved_path = save_validated_image(pil_img, settings.upload_dir)
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))

    analysis = await run_in_threadpool(execute_plant_analysis_pipeline, db, plant=plant, image_path=saved_path)
    return serialize_analysis(analysis)

@app.get("/api/analyses")
def list_analyses(
    response: Response,
    plant_id: Optional[int] = None,
    device_id: Optional[str] = None,
    health_filter: Optional[str] = None,
    disease_detected: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    q = db.query(models.Analysis)
    if plant_id:
        q = q.filter(models.Analysis.plant_id == plant_id)
    if device_id:
        q = q.join(models.Device).filter(models.Device.identifier == device_id)
    if health_filter and health_filter != "all":
        q = q.filter(models.Analysis.health_status.ilike(f"%{health_filter}%"))
    if disease_detected:
        q = q.filter(models.Analysis.disease_detected == disease_detected.lower())

    total_count = q.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)

    analyses = q.order_by(models.Analysis.timestamp.desc()).offset(offset).limit(limit).all()
    return [serialize_analysis(a) for a in analyses]

@app.get("/api/analyses/latest")
def get_latest_analysis(db: Session = Depends(get_db)):
    a = db.query(models.Analysis).order_by(models.Analysis.timestamp.desc()).first()
    if not a:
        raise HTTPException(404, "No analyses recorded yet.")
    return serialize_analysis(a)

@app.get("/api/analyses/{analysis_id}")
def get_analysis_by_id(analysis_id: int, db: Session = Depends(get_db)):
    a = db.get(models.Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Analysis not found.")
    return serialize_analysis(a)

# -------------------------------------------------------------
# Report Endpoints
# -------------------------------------------------------------
@app.get("/api/reports")
def list_reports(
    response: Response,
    plant_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    q = db.query(models.Report)
    if plant_id:
        q = q.filter(models.Report.plant_id == plant_id)

    total_count = q.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)

    reports = q.order_by(models.Report.created_at.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": r.id,
            "plant_id": r.plant_id,
            "plant_name": r.plant.name if r.plant else "Plant",
            "analysis_id": r.analysis_id,
            "created_at": r.created_at,
            "download_url": f"/api/reports/{r.id}/download"
        }
        for r in reports
    ]

@app.get("/api/reports/{report_id}")
def get_report_detail(report_id: int, db: Session = Depends(get_db)):
    r = db.get(models.Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found.")
    try:
        report_data = json.loads(r.report_data_json)
    except Exception:
        report_data = {}
    return {
        "id": r.id,
        "plant_id": r.plant_id,
        "plant_name": r.plant.name if r.plant else "Plant",
        "analysis_id": r.analysis_id,
        "created_at": r.created_at,
        "download_url": f"/api/reports/{r.id}/download",
        "data": report_data
    }

@app.post("/api/plants/{plant_id}/reports")
def create_report_endpoint(
    plant_id: int,
    analysis_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    plant = db.get(models.Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found.")
    analysis = db.get(models.Analysis, analysis_id) if analysis_id else (
        max(plant.analyses, key=lambda a: a.timestamp) if plant.analyses else None
    )
    if not analysis or analysis.plant_id != plant.id:
        raise HTTPException(400, "Run a diagnosis scan before generating a health report.")

    knowledge = retrieve_context_for_analysis(
        db,
        plant_species=analysis.plant_identification or plant.species,
        disease_name=analysis.disease_name,
        health_status=analysis.health_status
    )
    report_data = generate_agent_report_data(plant, analysis, knowledge)
    pdf_filename = f"flora-report-{plant.id}-{analysis.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    pdf_path = str(Path(settings.report_dir) / pdf_filename)
    build_pdf_report(plant, analysis, report_data, pdf_path)

    report = models.Report(
        plant_id=plant.id,
        analysis_id=analysis.id,
        report_data_json=json.dumps(report_data),
        file_path=pdf_path,
        created_at=datetime.now(timezone.utc)
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "download_url": f"/api/reports/{report.id}/download"
    }

@app.get("/api/reports/{report_id}/download")
def download_pdf_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(models.Report, report_id)
    if not r or not Path(r.file_path).is_file():
        raise HTTPException(404, "Report PDF file not found on disk.")
    return FileResponse(
        r.file_path,
        media_type="application/pdf",
        filename=Path(r.file_path).name
    )

# -------------------------------------------------------------
# Chatbot Endpoints
# -------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    plant_id: Optional[int] = None
    report_id: Optional[int] = None

@app.get("/api/conversations")
def list_conversations(db: Session = Depends(get_db)):
    convos = db.query(models.Conversation).order_by(models.Conversation.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "plant_id": c.plant_id,
            "created_at": c.created_at,
            "message_count": len(c.messages)
        }
        for c in convos
    ]

@app.get("/api/conversations/{conversation_id}")
def get_conversation_history(conversation_id: int, db: Session = Depends(get_db)):
    convo = db.get(models.Conversation, conversation_id)
    if not convo:
        raise HTTPException(404, "Conversation not found.")
    return {
        "id": convo.id,
        "title": convo.title,
        "plant_id": convo.plant_id,
        "report_id": convo.report_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at
            }
            for m in sorted(convo.messages, key=lambda x: x.created_at)
        ]
    }

@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    convo = db.get(models.Conversation, conversation_id)
    if convo:
        db.delete(convo)
        db.commit()
    return {"ok": True}

@app.post("/api/chat")
def chat_with_bot(req: ChatRequest, db: Session = Depends(get_db)):
    convo = db.get(models.Conversation, req.conversation_id) if req.conversation_id else None
    if not convo:
        title = "Plant Chat"
        if req.plant_id:
            p = db.get(models.Plant, req.plant_id)
            if p: title = f"{p.name} Consultation"
        convo = models.Conversation(title=title, plant_id=req.plant_id, report_id=req.report_id)
        db.add(convo)
        db.commit()
        db.refresh(convo)

    if req.plant_id:
        convo.plant_id = req.plant_id
    if req.report_id:
        convo.report_id = req.report_id

    # 1. Build context from plant & latest scan
    plant_context = ""
    knowledge_context = ""
    target_plant = db.get(models.Plant, convo.plant_id) if convo.plant_id else None

    if target_plant:
        latest = max(target_plant.analyses, key=lambda a: a.timestamp) if target_plant.analyses else None
        if latest:
            plant_context = (
                f"{target_plant.name} ({target_plant.species}), current health status: {latest.health_status}. "
                f"Condition: {latest.disease_name or 'Healthy'}. Symptoms: {latest.symptoms}. "
                f"Watering: {latest.watering_status} ({latest.watering_quantity_ml or 'check soil'} ml)."
            )
            # Retrieve botanical knowledge matching plant and condition
            k_matches = retrieve_context_for_analysis(
                db,
                plant_species=latest.plant_identification or target_plant.species,
                disease_name=latest.disease_name,
                health_status=latest.health_status
            )
            if k_matches:
                knowledge_context = " | ".join(f"{k.title}: {k.summary}" for k in k_matches[:2])
        else:
            plant_context = f"{target_plant.name} ({target_plant.species}), location: {target_plant.location}. No scans recorded yet."

    # Add references relevant to the question itself, not only the latest diagnosis.
    stop_words = {"what", "when", "where", "which", "with", "from", "that", "this", "your", "does", "have", "about", "could", "would", "should", "please", "tell"}
    terms = [word.strip(".,?!:;()") for word in req.message.lower().split()]
    terms = [word for word in terms if len(word) >= 4 and word not in stop_words][:6]
    found = {}
    for term in terms:
        for entry in search_knowledge(db, query=term, limit=4):
            found[entry.id] = entry
    if found:
        query_context = " | ".join(
            f"{entry.title} ({entry.source_name}): {entry.summary}"
            for entry in list(found.values())[:3]
        )
        knowledge_context = " | ".join(part for part in [knowledge_context, query_context] if part)

    # 2. Record user message
    user_msg = models.ChatMessage(
        conversation_id=convo.id,
        role="user",
        content=req.message.strip()
    )
    db.add(user_msg)
    db.commit()

    # 3. Compile history and invoke agent synthesizer
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(convo.messages, key=lambda x: x.created_at)
    ]
    reply = generate_chat_reply(
        messages=history,
        plant_context=plant_context,
        knowledge_context=knowledge_context
    )

    # 4. Record assistant reply
    assistant_msg = models.ChatMessage(
        conversation_id=convo.id,
        role="assistant",
        content=reply
    )
    db.add(assistant_msg)
    db.commit()

    return {
        "conversation_id": convo.id,
        "reply": reply,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in sorted(convo.messages, key=lambda x: x.created_at)
        ]
    }

# -------------------------------------------------------------
# Knowledge Base Endpoints
# -------------------------------------------------------------
@app.get("/api/knowledge")
def search_knowledge_endpoint(
    query: str = "",
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    entries = search_knowledge(db, query=query, category=category)
    return [
        {
            "id": e.id,
            "title": e.title,
            "category": e.category,
            "plant_species": e.plant_species,
            "disease_name": e.disease_name,
            "summary": e.summary,
            "details_markdown": e.details_markdown,
            "care_data": json.loads(e.care_data_json) if e.care_data_json else {},
            "treatment_plan": e.treatment_plan,
            "prevention_tips": e.prevention_tips,
            "source_name": e.source_name,
            "source_url": e.source_url
        }
        for e in entries
    ]

@app.get("/api/knowledge/{entry_id}")
def get_knowledge_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.get(models.KnowledgeEntry, entry_id)
    if not e:
        raise HTTPException(404, "Knowledge entry not found.")
    return {
        "id": e.id,
        "title": e.title,
        "category": e.category,
        "plant_species": e.plant_species,
        "disease_name": e.disease_name,
        "summary": e.summary,
        "details_markdown": e.details_markdown,
        "care_data": json.loads(e.care_data_json) if e.care_data_json else {},
        "treatment_plan": e.treatment_plan,
        "prevention_tips": e.prevention_tips,
        "source_name": e.source_name,
        "source_url": e.source_url
    }

# -------------------------------------------------------------
# Settings Endpoints
# -------------------------------------------------------------
class CameraSettings(BaseModel):
    stream_url: str
    snapshot_url: str

def normalize_camera_url(url: str, *, stream: bool) -> str:
    """Turn the ESP32 web UI root URL into the firmware's media endpoint."""
    parsed = urlsplit(url.strip())
    if parsed.path not in ("", "/"):
        return urlunsplit(parsed)

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port
    if stream:
        authority = f"{host}:{port if port and port != 80 else 81}"
        path = "/stream"
    else:
        authority = f"{host}:{port}" if port else host
        path = "/capture"
    return urlunsplit((parsed.scheme, authority, path, "", ""))

@app.get("/api/settings")
def get_settings():
    return {
        "camera_stream_url": settings.camera_stream_url,
        "camera_snapshot_url": settings.camera_snapshot_url,
        "device_offline_timeout_seconds": settings.device_offline_timeout_seconds,
        "monitoring_interval_seconds": settings.monitoring_interval_seconds,
        "min_confidence_threshold": settings.min_confidence_threshold,
    }

@app.post("/api/settings/camera")
def update_camera_settings(payload: CameraSettings, db: Session = Depends(get_db)):
    stream_url = normalize_camera_url(payload.stream_url, stream=True)
    snapshot_url = normalize_camera_url(payload.snapshot_url, stream=False)
    if not stream_url or not snapshot_url:
        raise HTTPException(400, "Both camera URLs are required.")

    settings.camera_stream_url = stream_url
    settings.camera_snapshot_url = snapshot_url

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        replacements = {
            "CAMERA_STREAM_URL": stream_url,
            "CAMERA_SNAPSHOT_URL": snapshot_url,
        }
        for key, value in replacements.items():
            prefix = f"{key}="
            matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
            if matches:
                lines[matches[0]] = f"{prefix}{value}"
            else:
                lines.append(f"{prefix}{value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    devices = db.query(models.Device).all()
    for device in devices:
        device.stream_url = stream_url
        device.snapshot_url = snapshot_url
    db.commit()

    return {
        "camera_stream_url": stream_url,
        "camera_snapshot_url": snapshot_url,
        "status": "saved",
    }

@app.post("/api/settings/test-camera")
def test_camera_connection(url: str = Query(...)):
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(url)
            return {
                "connected": r.status_code < 400,
                "status_code": r.status_code,
                "message": f"Endpoint responded with HTTP {r.status_code}."
            }
    except Exception as exc:
        return {
            "connected": False,
            "message": f"Camera did not respond: {str(exc)}"
        }
