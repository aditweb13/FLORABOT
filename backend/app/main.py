import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import httpx
from fastapi import FastAPI, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import Base, engine, get_db
from .vision_engine import validate_image_bytes, save_validated_image, analyze_plant_image
from .watering_engine import calculate_watering_recommendation
from .knowledge_service import seed_knowledge_base, search_knowledge, retrieve_context_for_analysis
from .agent_service import generate_agent_report_data, generate_chat_reply
from .camera_service import (
    get_or_create_device, record_device_heartbeat, update_device_statuses,
    record_received_camera_image
)
from .pdf_service import build_pdf_report

# Ensure directories & database tables exist
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
Path(settings.report_dir).mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)

# Seed knowledge base
with engine.connect() as conn:
    with Session(bind=conn) as init_db:
        seed_knowledge_base(init_db)
        # Ensure default device exists
        get_or_create_device(init_db, identifier="esp32-cam-01", name="ESP32-CAM Indoor Monitor")

app = FastAPI(title="FloraBOT AI API", version="2.0.0", description="Intelligent Indoor Plant Monitoring & Diagnostic API")

cors_origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
if "*" not in cors_origins and not cors_origins:
    cors_origins = ["*"]

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
    plant: models.Plant,
    image_path: str,
    device: Optional[models.Device] = None,
    cam_img: Optional[models.CameraImage] = None
) -> models.Analysis:
    """Core image processing, computer vision, watering engine, and report pipeline."""
    # 1. Vision & Disease Analysis
    vis_res = analyze_plant_image(image_path, plant_hint=plant.species)

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
        provider_reference=vis_res.get("provider_reference", "")
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
@app.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    update_device_statuses(db)
    active_devices = db.query(models.Device).filter(models.Device.status == "online").count()
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diagnosis_configured": bool(settings.plant_id_api_key),
        "chat_configured": bool(settings.groq_api_key),
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
    device_id: Optional[str] = "esp32-cam-01",
    plant_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    x_device_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receives an incoming camera frame directly from ESP32-CAM via HTTP POST.
    Accepts both multipart form upload or raw binary JPEG payload.
    Automatically timestamps, registers to device, and triggers AI analysis pipeline.
    """
    effective_dev_id = x_device_id or device_id or "esp32-cam-01"
    client_ip = request.client.host if request.client else ""
    device = get_or_create_device(db, identifier=effective_dev_id, ip_address=client_ip)

    # 1. Read bytes from multipart file or raw body
    if image is not None:
        raw_bytes = await image.read()
    else:
        raw_bytes = await request.body()

    if not raw_bytes:
        raise HTTPException(400, "No image payload received in request.")

    # 2. Validate image format & dimensions
    try:
        pil_img, width, height = validate_image_bytes(raw_bytes)
    except ValueError as val_err:
        raise HTTPException(400, f"Image rejected: {str(val_err)}")

    # 3. Store validated image file
    saved_path = save_validated_image(pil_img, settings.upload_dir)

    # 4. Resolve plant to associate
    target_plant = None
    if plant_id:
        target_plant = db.get(models.Plant, plant_id)
    if not target_plant:
        target_plant = db.query(models.Plant).order_by(models.Plant.id.asc()).first()
    
    if not target_plant:
        # Create a default plant container so monitoring history is immediately preserved
        target_plant = models.Plant(
            name="Monitored Plant (ESP32-CAM)",
            species="Unknown Indoor Plant",
            category="Houseplant",
            location="Camera Station",
            notes="Auto-registered for incoming ESP32-CAM stream.",
            pot_size_cm=15
        )
        db.add(target_plant)
        db.commit()
        db.refresh(target_plant)

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

    # 6. Execute full AI analysis & report generation pipeline
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
        "plant_id": target_plant.id,
        "analysis_id": analysis.id,
        "health_status": analysis.health_status,
        "timestamp": cam_img.timestamp
    }

@app.post("/api/devices/{device_id}/heartbeat")
@app.post("/api/camera/heartbeat")
def receive_device_heartbeat(
    device_id: str = "esp32-cam-01",
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Receives periodic heartbeat ping from ESP32-CAM device."""
    client_ip = request.client.host if request and request.client else ""
    dev = record_device_heartbeat(db, identifier=device_id, ip_address=client_ip)
    return {
        "status": "ok",
        "device_id": dev.identifier,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "poll_interval_sec": dev.poll_interval_sec
    }

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
    target_plant = db.get(models.Plant, plant_id) if plant_id else db.query(models.Plant).first()
    if not target_plant:
        target_plant = models.Plant(
            name="Monitored Plant (ESP32-CAM)",
            species="Unknown Indoor Plant",
            category="Houseplant",
            location="Camera Station",
            pot_size_cm=15
        )
        db.add(target_plant)
        db.commit()
        db.refresh(target_plant)

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

    analysis = execute_plant_analysis_pipeline(db, plant=plant, image_path=saved_path)
    return serialize_analysis(analysis)

@app.get("/api/analyses")
def list_analyses(
    plant_id: Optional[int] = None,
    health_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(models.Analysis)
    if plant_id:
        q = q.filter(models.Analysis.plant_id == plant_id)
    if health_filter and health_filter != "all":
        q = q.filter(models.Analysis.health_status.ilike(f"%{health_filter}%"))
    analyses = q.order_by(models.Analysis.timestamp.desc()).limit(limit).all()
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
def list_reports(plant_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.Report)
    if plant_id:
        q = q.filter(models.Report.plant_id == plant_id)
    reports = q.order_by(models.Report.created_at.desc()).all()
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
@app.get("/api/settings")
def get_settings():
    return {
        "camera_stream_url": settings.camera_stream_url,
        "camera_snapshot_url": settings.camera_snapshot_url,
        "device_offline_timeout_seconds": settings.device_offline_timeout_seconds,
        "monitoring_interval_seconds": settings.monitoring_interval_seconds,
        "min_confidence_threshold": settings.min_confidence_threshold,
        "diagnosis_configured": bool(settings.plant_id_api_key),
        "chat_configured": bool(settings.groq_api_key),
        "chat_model": settings.groq_model
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

@app.post("/api/settings/test-ai")
def test_ai_services():
    return {
        "diagnosis_configured": bool(settings.plant_id_api_key),
        "chat_configured": bool(settings.groq_api_key),
        "chat_model": settings.groq_model,
        "local_vision_engine": "Active & Ready"
    }
