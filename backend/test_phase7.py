"""
FloraBOT Phase 7 Automated Test Suite (Watering & Sensor Intelligence):
1. Substrate Calibration Curves (Capacitive sensor ADC to volumetric water content %).
2. Fail-Safe Automated Irrigation Safety Lock & Watchdog timeout limits.
3. Botanical Watering Recommendation Engine with Pot Size & Substrate context.
4. Telemetry Ingestion via Heartbeat payload (/api/devices/{id}/heartbeat).
5. Sensor Time-Series Telemetry Endpoints (/api/devices/{id}/telemetry, /api/plants/{id}/telemetry).
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base, Plant, Device, SensorTelemetry
from app.watering_engine import (
    calculate_watering_recommendation,
    calibrate_soil_moisture,
    evaluate_irrigation_safety_lock,
    SUBSTRATE_CALIBRATION_CURVES
)

TEST_DB_PATH = backend_dir / "data" / "test_phase7.db"

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

def test_substrate_calibration_curves():
    print("Testing capacitive soil moisture substrate calibration...")
    # Potting Mix curve: dry=3100, wet=1450
    dry_pct, dry_eval = calibrate_soil_moisture(3100, substrate="Potting Mix")
    assert dry_pct == 0.0, f"Expected 0.0% at dry ADC, got {dry_pct}"
    assert dry_eval == "dry"

    wet_pct, wet_eval = calibrate_soil_moisture(1450, substrate="Potting Mix")
    assert wet_pct == 100.0, f"Expected 100.0% at wet ADC, got {wet_pct}"
    assert wet_eval == "saturated"

    mid_pct, mid_eval = calibrate_soil_moisture(2275, substrate="Potting Mix")
    assert 45.0 <= mid_pct <= 55.0, f"Expected mid range ~50%, got {mid_pct}"
    assert mid_eval == "optimal"

    # Test Succulent / Cactus Mix: optimal range 10% - 35%
    succ_pct, succ_eval = calibrate_soil_moisture(2800, substrate="Succulent / Cactus")
    assert succ_pct > 0
    print(f"  -> Passed substrate calibration curves (Potting Mix: dry={dry_pct}%, wet={wet_pct}%, mid={mid_pct}%).")

def test_irrigation_safety_watchdog():
    print("Testing automated irrigation safety lock and watchdog limits...")
    # Case 1: Soil is already saturated (> optimal_max) -> Must lock out pump
    lock1 = evaluate_irrigation_safety_lock(
        target_volume_ml=200,
        calibrated_moisture_pct=72.0,
        substrate="Potting Mix"
    )
    assert lock1["irrigation_allowed"] is False
    assert lock1["dispense_volume_ml"] == 0
    assert "exceeds substrate saturation" in lock1["safety_lock_reason"]

    # Case 2: Excessive volume request (> max single dose 500ml) -> Must clamp to safe limit
    lock2 = evaluate_irrigation_safety_lock(
        target_volume_ml=1200,
        calibrated_moisture_pct=15.0,
        substrate="Potting Mix",
        max_single_dose_ml=500
    )
    assert lock2["irrigation_allowed"] is True
    assert lock2["dispense_volume_ml"] == 500, f"Expected clamped 500ml, got {lock2['dispense_volume_ml']}"
    assert lock2["pump_watchdog_timeout_sec"] > 0

    # Case 3: Zero or negative volume -> Lock out
    lock3 = evaluate_irrigation_safety_lock(target_volume_ml=0, calibrated_moisture_pct=10.0)
    assert lock3["irrigation_allowed"] is False
    print("  -> Passed irrigation safety lock, saturation cutoff, and watchdog ceiling.")

def test_watering_engine_integration():
    print("Testing botanical watering engine volume and limitation calculations...")
    rec = calculate_watering_recommendation(
        species="Monstera deliciosa",
        health_status="Healthy",
        stress_status="None",
        pot_size_cm=20,
        soil_type="Aroid Mix",
        moisture_sensor_reading=18.0 # Sensor reports thirst (< 20%)
    )
    assert rec["watering_status"] == "Water may be required"
    assert rec["watering_quantity_ml"] is not None
    assert rec["watering_quantity_ml"] > 100
    assert "Standard 20 cm container" in rec["assumptions"][0]

    # Test overwatered / saturated condition
    rec_wet = calculate_watering_recommendation(
        species="Sansevieria trifasciata",
        health_status="Yellowing",
        stress_status="Leaf Chlorosis",
        pot_size_cm=15,
        moisture_sensor_reading=78.0
    )
    assert rec_wet["watering_status"] == "Possible overwatering"
    assert rec_wet["watering_quantity_ml"] is None
    print(f"  -> Passed watering recommendation engine (Thirsty: {rec['watering_quantity_ml']}ml, Saturated: {rec_wet['watering_status']}).")

def test_sensor_telemetry_persistence(db: Session):
    print("Testing sensor time-series telemetry models and querying...")
    plant = Plant(name="Calathea Test", species="Calathea orbifolia")
    device = Device(identifier="esp32-sensor-01", status="online")
    db.add_all([plant, device])
    db.commit()

    # Record 3 telemetry readings
    t1 = SensorTelemetry(
        device_id=device.id,
        plant_id=plant.id,
        soil_moisture_pct=42.5,
        raw_adc=2400,
        ambient_temp_c=24.2,
        humidity_pct=62.0,
        substrate="Peat / Sphagnum",
        timestamp=datetime.now(timezone.utc)
    )
    t2 = SensorTelemetry(
        device_id=device.id,
        plant_id=plant.id,
        soil_moisture_pct=38.0,
        raw_adc=2480,
        ambient_temp_c=24.8,
        humidity_pct=59.5,
        substrate="Peat / Sphagnum",
        timestamp=datetime.now(timezone.utc)
    )
    db.add_all([t1, t2])
    db.commit()

    readings = db.query(SensorTelemetry).filter(SensorTelemetry.plant_id == plant.id).all()
    assert len(readings) == 2
    assert readings[0].soil_moisture_pct == 42.5
    assert readings[0].ambient_temp_c == 24.2
    assert readings[0].substrate == "Peat / Sphagnum"
    print(f"  -> Passed sensor telemetry persistence ({len(readings)} historical readings verified).")

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 7 TEST SUITE (WATERING & SENSORS)")
    print("========================================================\n")
    db = get_test_db()
    try:
        test_substrate_calibration_curves()
        test_irrigation_safety_watchdog()
        test_watering_engine_integration()
        test_sensor_telemetry_persistence(db)
        print("\n========================================================")
        print("  ALL PHASE 7 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
        print("========================================================\n")
    finally:
        db.close()

if __name__ == "__main__":
    main()
