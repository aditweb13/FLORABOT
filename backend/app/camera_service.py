from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from .config import settings
from .models import Device, DeviceLog, CameraImage, Plant

def get_or_create_device(
    db: Session,
    identifier: str = "esp32-cam-01",
    name: Optional[str] = None,
    ip_address: str = ""
) -> Device:
    """Finds or registers an ESP32-CAM hardware device."""
    dev = db.query(Device).filter(Device.identifier == identifier).first()
    now = datetime.now(timezone.utc)
    if not dev:
        dev = Device(
            identifier=identifier,
            name=name or f"ESP32-CAM ({identifier})",
            type="ESP32-CAM",
            status="online",
            ip_address=ip_address,
            stream_url=settings.camera_stream_url,
            snapshot_url=settings.camera_snapshot_url,
            last_communication=now,
            poll_interval_sec=settings.monitoring_interval_seconds,
            is_active=True
        )
        db.add(dev)
        db.commit()
        db.refresh(dev)
        
        # Log device creation
        log = DeviceLog(
            device_id=dev.id,
            event_type="connected",
            message=f"Device registered with IP {ip_address or 'unknown'}",
            timestamp=now
        )
        db.add(log)
        db.commit()
    else:
        dev.last_communication = now
        dev.status = "online"
        if ip_address:
            dev.ip_address = ip_address
        db.commit()
        db.refresh(dev)

    return dev

def record_device_heartbeat(
    db: Session,
    identifier: str,
    ip_address: str = "",
    status_msg: str = "Heartbeat OK"
) -> Device:
    """Records an incoming heartbeat from an ESP32-CAM node."""
    dev = get_or_create_device(db, identifier=identifier, ip_address=ip_address)
    now = datetime.now(timezone.utc)
    dev.last_communication = now
    dev.status = "online"
    
    log = DeviceLog(
        device_id=dev.id,
        event_type="heartbeat",
        message=status_msg,
        timestamp=now
    )
    db.add(log)
    db.commit()
    db.refresh(dev)
    return dev

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def update_device_statuses(db: Session):
    """
    Evaluates connection health for all devices based on last communication timestamp.
    If elapsed time > timeout, transitions to 'stale' or 'offline'.
    """
    now = datetime.now(timezone.utc)
    devices = db.query(Device).all()
    timeout_sec = settings.device_offline_timeout_seconds
    stale_sec = timeout_sec // 2
    
    for dev in devices:
        last_comm = to_utc(dev.last_communication)
        if not last_comm:
            dev.status = "offline"
            continue
            
        elapsed = (now - last_comm).total_seconds()
        if elapsed > timeout_sec:
            if dev.status != "offline":
                dev.status = "offline"
                db.add(DeviceLog(
                    device_id=dev.id,
                    event_type="disconnected",
                    message=f"Device timed out after {int(elapsed)} seconds without heartbeat.",
                    timestamp=now
                ))
        elif elapsed > stale_sec:
            dev.status = "stale"
        else:
            dev.status = "online"

    db.commit()

def record_received_camera_image(
    db: Session,
    device: Optional[Device],
    plant: Optional[Plant],
    file_path: str,
    file_size: int,
    width: int,
    height: int
) -> CameraImage:
    """Stores metadata for a newly received camera snapshot."""
    now = datetime.now(timezone.utc)
    cam_img = CameraImage(
        device_id=device.id if device else None,
        plant_id=plant.id if plant else None,
        file_path=file_path,
        timestamp=now,
        file_size=file_size,
        width=width,
        height=height,
        processing_status="processing"
    )
    db.add(cam_img)
    if device:
        device.last_image_received = now
        device.last_communication = now
        device.status = "online"
        db.add(DeviceLog(
            device_id=device.id,
            event_type="image_received",
            message=f"Received JPEG frame ({width}x{height}, {file_size} bytes)",
            timestamp=now
        ))
    db.commit()
    db.refresh(cam_img)
    return cam_img
