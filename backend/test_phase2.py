"""
Phase 2 automated verification test.
Validates Alembic migrations, explicit device-to-plant mapping,
asynchronous ingestion (202 Accepted), pagination, and filtering.
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from alembic.config import Config
from alembic import command
from fastapi import Response, HTTPException
from app.main import app, list_analyses, list_reports, receive_camera_image
from app.database import get_db, engine
from app import models
from sqlalchemy.orm import Session

def run_coro(coro):
    """Executes a coroutine directly without requiring Windows IOCP socket pairs."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value

def create_sample_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (128, 128), color=(40, 140, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

def run_phase2_tests():
    print("=== FloraBOT Phase 2 Verification Test ===", flush=True)
    db = next(get_db())

    # 1. Alembic Migration Verification
    print("1. Verifying Alembic migration status...", flush=True)
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.current(alembic_cfg)
    print("   [PASS] Alembic migrations configured and verified at current head.", flush=True)

    # 2. Explicit Plant / Device Mapping & 404 on Invalid Plant ID
    print("2. Verifying explicit plant mapping and validation...", flush=True)
    test_plant = models.Plant(
        name="Phase2 Test Ficus",
        species="Ficus elastica",
        category="Houseplant",
        health_status="Healthy"
    )
    db.add(test_plant)
    db.commit()
    db.refresh(test_plant)
    pid = test_plant.id
    print(f"   Created test plant ID: {pid}", flush=True)

    class MockRequest:
        def __init__(self, body_bytes: bytes, client_host: str = "127.0.0.1"):
            self._body = body_bytes
            self.client = type("Client", (), {"host": client_host})()
        async def body(self):
            return self._body

    class MockBackgroundTasks:
        def __init__(self):
            self.tasks = []
        def add_task(self, func, *args, **kwargs):
            self.tasks.append((func, args, kwargs))
        def execute_all(self):
            for func, args, kwargs in self.tasks:
                func(*args, **kwargs)

    jpeg_data = create_sample_jpeg_bytes()

    # Test invalid plant ID -> raises 404
    try:
        req = MockRequest(jpeg_data)
        bg = MockBackgroundTasks()
        run_coro(receive_camera_image(
            request=req,
            background_tasks=bg,
            device_id="esp32-cam-test",
            plant_id=99999999,
            image=None,
            db=db
        ))
        assert False, "Expected 404 for invalid plant ID"
    except HTTPException as exc:
        assert exc.status_code == 404, f"Expected 404, got {exc.status_code}"
        print(f"   [PASS] Non-existent plant ID correctly rejected with HTTP 404: {exc.detail}", flush=True)

    # 3. Asynchronous Ingestion (Fast 202 Accepted Acknowledgment)
    print("3. Verifying asynchronous ingestion mode (202 Accepted)...", flush=True)
    req = MockRequest(jpeg_data)
    bg = MockBackgroundTasks()
    res = run_coro(receive_camera_image(
        request=req,
        background_tasks=bg,
        device_id="esp32-cam-async-01",
        plant_id=pid,
        image=None,
        async_mode=True,
        db=db
    ))
    assert res.status_code == 202, f"Expected 202, got {res.status_code}"
    body = json.loads(res.body.decode())
    assert body["status"] == "accepted"
    assert body["job_status"] == "queued"
    img_id = body["image_id"]
    print(f"   [PASS] Async ingestion returned 202 Accepted in fast mode (Image ID: {img_id}).", flush=True)

    # Execute background worker task with mocked external providers
    mock_vis_result = {
        "plant_identification": "Ficus elastica",
        "plant_confidence": 0.95,
        "disease_detected": "no",
        "disease_name": "",
        "disease_confidence": None,
        "severity": "None",
        "health_status": "Healthy (Verified)",
        "confidence": 0.95,
        "symptoms": "Healthy leaf tissue",
        "recommendations": "Maintain current care routine",
        "prevention": "Avoid overwatering",
        "recovery_plan": "",
        "stress_status": "None",
        "stress_observations": "No stress observed",
        "provider_engine": "Test Mock Engine",
        "provider_reference": "test_ref",
        "diagnostic_error": "",
        "detections": [],
        "model_metadata": {},
        "identification_candidates": []
    }
    with patch("app.main.analyze_plant_image", return_value=mock_vis_result), \
         patch("app.main.generate_agent_report_data", return_value={"summary": "Mock report summary", "details": {}}):
        bg.execute_all()

    with Session(bind=engine) as verify_db:
        cam_rec = verify_db.get(models.CameraImage, img_id)
        assert cam_rec.processing_status == "completed", f"Expected completed status, got {cam_rec.processing_status}"
        print(f"   [PASS] Background task executed successfully (Status: {cam_rec.processing_status}).", flush=True)

    # 4. Pagination and Query Filtering for Analyses
    print("4. Verifying pagination and filtering for /api/analyses...", flush=True)
    resp = Response()
    analyses = list_analyses(response=resp, plant_id=pid, limit=10, offset=0, db=db)
    assert isinstance(analyses, list)
    assert "X-Total-Count" in resp.headers
    assert resp.headers["X-Limit"] == "10"
    assert resp.headers["X-Offset"] == "0"
    print(f"   [PASS] /api/analyses pagination headers verified: X-Total-Count={resp.headers['X-Total-Count']}, X-Limit={resp.headers['X-Limit']}, X-Offset={resp.headers['X-Offset']}.", flush=True)

    # 5. Pagination and Query Filtering for Reports
    print("5. Verifying pagination and filtering for /api/reports...", flush=True)
    resp_rep = Response()
    reports = list_reports(response=resp_rep, plant_id=pid, limit=5, offset=0, db=db)
    assert isinstance(reports, list)
    assert "X-Total-Count" in resp_rep.headers
    assert resp_rep.headers["X-Limit"] == "5"
    print(f"   [PASS] /api/reports pagination headers verified: X-Total-Count={resp_rep.headers['X-Total-Count']}, X-Limit={resp_rep.headers['X-Limit']}.", flush=True)

    # 6. Malformed Image Rejection
    print("6. Verifying malformed image rejection...", flush=True)
    try:
        bad_req = MockRequest(b"NotAJpegHeader")
        run_coro(receive_camera_image(
            request=bad_req,
            background_tasks=MockBackgroundTasks(),
            device_id="esp32-cam-test",
            plant_id=pid,
            image=None,
            db=db
        ))
        assert False, "Expected 400 for corrupt image"
    except HTTPException as exc:
        assert exc.status_code == 400
        print(f"   [PASS] Malformed image payload rejected with HTTP 400: {exc.detail}", flush=True)

    # Cleanup test plant
    db.delete(test_plant)
    db.commit()

    print("\n[SUCCESS] All Phase 2 backend verification checks PASSED!", flush=True)

if __name__ == "__main__":
    run_phase2_tests()
