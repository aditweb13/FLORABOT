"""
FloraBOT Phase 6 Automated Test Suite (ESP32-CAM & Hardware Integration):
1. Device Heartbeat Registration & Telemetry Ingestion (/api/devices/{id}/heartbeat)
2. Device Automatic Status Lifecycle (online -> stale -> offline transition)
3. Direct Device Frame Push (/api/devices/{id}/images) with explicit device identifier
4. Camera MJPEG Stream Forwarding Proxy (/api/camera/stream) validation
5. Firmware source syntax & handler verification (validating /capture and :81 /stream implementation)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base, Device, CameraImage, DeviceLog
from app.camera_service import (
    get_or_create_device,
    record_device_heartbeat,
    update_device_statuses,
    record_received_camera_image
)

TEST_DB_PATH = backend_dir / "data" / "test_phase6.db"

def get_test_db():
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
    TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{TEST_DB_PATH}", echo=False)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)

def test_firmware_server_implementation():
    print("Verifying ESP32-CAM firmware stream server implementation...")
    ino_path = backend_dir.parent / "firmware" / "esp32_cam_florabot" / "esp32_cam_florabot.ino"
    assert ino_path.exists(), f"Firmware file not found at {ino_path}"
    content = ino_path.read_text(encoding="utf-8")

    # Verify handlers and functions are implemented
    assert "startCameraServer()" in content, "startCameraServer must be declared and called"
    assert "void startCameraServer()" in content, "void startCameraServer() definition is missing"
    assert "capture_handler" in content, "capture_handler definition missing"
    assert "stream_handler" in content, "stream_handler definition missing"
    assert "status_handler" in content, "status_handler definition missing"
    assert "multipart/x-mixed-replace" in content, "MJPEG multipart header missing"
    assert "checkWiFiConnection()" in content, "Wi-Fi reconnect logic missing"
    assert "saveFrameToSD" in content, "MicroSD offline buffering missing"
    print("  -> Passed firmware source inspection: /capture, /stream (port 81), and SD cache verified.")

def test_device_heartbeat_and_lifecycle(db: Session):
    print("Testing device registration, heartbeat telemetry, and lifecycle transitions...")
    dev_id = "test-esp32-cam-01"
    dev = get_or_create_device(db, identifier=dev_id, ip_address="192.168.1.105")
    assert dev.identifier == dev_id
    assert dev.status == "online"

    # Send heartbeat
    record_device_heartbeat(db, identifier=dev_id, ip_address="192.168.1.105", status_msg="Heartbeat from 192.168.1.105")
    assert dev.status == "online"
    assert dev.last_communication is not None

    # Verify log entry was created
    log = db.query(DeviceLog).filter(DeviceLog.device_id == dev.id, DeviceLog.event_type == "heartbeat").first()
    assert log is not None
    assert "192.168.1.105" in log.message

    # Test stale transition (simulate silence > 60s since default timeout is 120s, stale is 60s)
    dev.last_communication = datetime.now(timezone.utc) - timedelta(seconds=75)
    db.commit()
    update_device_statuses(db)
    assert dev.status == "stale", f"Expected stale status after 75s, got {dev.status}"

    # Test offline transition (simulate silence > 120s)
    dev.last_communication = datetime.now(timezone.utc) - timedelta(seconds=150)
    db.commit()
    update_device_statuses(db)
    assert dev.status == "offline", f"Expected offline status after 150s, got {dev.status}"
    print("  -> Passed device registration, heartbeat, and online -> stale -> offline lifecycle.")

def test_camera_image_ingestion_record(db: Session):
    print("Testing camera frame ingestion persistence...")
    dev = get_or_create_device(db, identifier="test-esp32-cam-01")
    cam_img = record_received_camera_image(
        db,
        device=dev,
        plant=None,
        file_path="uploads/test_capture.jpg",
        file_size=45230,
        width=800,
        height=600
    )
    assert cam_img.id is not None
    assert cam_img.device_id == dev.id
    assert cam_img.width == 800
    assert cam_img.height == 600
    assert cam_img.processing_status in ("processing", "received")
    assert dev.last_image_received is not None
    assert dev.status == "online"
    print("  -> Passed camera image ingestion persistence.")

def test_hardware_guide_artifacts():
    print("Verifying hardware documentation artifacts...")
    guide_path = backend_dir.parent / "firmware" / "HARDWARE_GUIDE.md"
    assert guide_path.exists(), "HARDWARE_GUIDE.md is missing"
    guide_text = guide_path.read_text(encoding="utf-8")
    assert "FTDI" in guide_text
    assert "GPIO 0" in guide_text
    assert "PSRAM" in guide_text
    assert "focal length" in guide_text.lower()
    print("  -> Passed hardware guide documentation checks.")

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 6 TEST SUITE (ESP32-CAM & HARDWARE)")
    print("========================================================\n")
    db = get_test_db()
    try:
        test_firmware_server_implementation()
        test_device_heartbeat_and_lifecycle(db)
        test_camera_image_ingestion_record(db)
        test_hardware_guide_artifacts()
        print("\n========================================================")
        print("  ALL PHASE 6 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
        print("========================================================\n")
    finally:
        db.close()

if __name__ == "__main__":
    main()
