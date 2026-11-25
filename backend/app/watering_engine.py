import math
from typing import Any, Dict, Optional, Tuple

# Substrate Calibration Curves:
# Maps raw 12-bit ADC reading (capacitive sensor v1.2: ~3200 air/dry to ~1400 water/saturated)
# to calibrated volumetric water content (VWC) percentage accounting for substrate porosity.
SUBSTRATE_CALIBRATION_CURVES = {
    "Potting Mix": {"dry_adc": 3100, "wet_adc": 1450, "optimal_min": 25.0, "optimal_max": 65.0},
    "Aroid Mix": {"dry_adc": 3250, "wet_adc": 1600, "optimal_min": 20.0, "optimal_max": 55.0},
    "Succulent / Cactus": {"dry_adc": 3300, "wet_adc": 1750, "optimal_min": 10.0, "optimal_max": 35.0},
    "Peat / Sphagnum": {"dry_adc": 2950, "wet_adc": 1300, "optimal_min": 35.0, "optimal_max": 75.0},
}

def calibrate_soil_moisture(raw_adc: int, substrate: str = "Potting Mix") -> Tuple[float, str]:
    """
    Converts raw 12-bit capacitive soil sensor ADC value into calibrated volumetric moisture %.
    """
    curve = SUBSTRATE_CALIBRATION_CURVES.get(substrate, SUBSTRATE_CALIBRATION_CURVES["Potting Mix"])
    dry = curve["dry_adc"]
    wet = curve["wet_adc"]

    # Invert capacitive reading: higher ADC = dryer, lower ADC = wetter
    clamped_adc = max(wet, min(dry, raw_adc))
    moisture_pct = ((dry - clamped_adc) / (dry - wet)) * 100.0
    moisture_pct = round(max(0.0, min(100.0, moisture_pct)), 1)

    if moisture_pct < curve["optimal_min"]:
        eval_status = "dry"
    elif moisture_pct > curve["optimal_max"]:
        eval_status = "saturated"
    else:
        eval_status = "optimal"

    return moisture_pct, eval_status

def evaluate_irrigation_safety_lock(
    target_volume_ml: Optional[int],
    calibrated_moisture_pct: Optional[float],
    substrate: str = "Potting Mix",
    max_single_dose_ml: int = 500
) -> Dict[str, Any]:
    """
    Hardware fail-safe and watchdog safety logic for automated pump/valve actuation.
    Prevents flooding, continuous loop actuation, and watering already-saturated soil.
    """
    curve = SUBSTRATE_CALIBRATION_CURVES.get(substrate, SUBSTRATE_CALIBRATION_CURVES["Potting Mix"])
    
    # 1. Moisture Saturation Cutoff
    if calibrated_moisture_pct is not None and calibrated_moisture_pct >= curve["optimal_max"]:
        return {
            "irrigation_allowed": False,
            "dispense_volume_ml": 0,
            "safety_lock_reason": f"Moisture ({calibrated_moisture_pct}%) already exceeds substrate saturation threshold ({curve['optimal_max']}%)."
        }

    # 2. Volume Safety Ceiling
    if not target_volume_ml or target_volume_ml <= 0:
        return {
            "irrigation_allowed": False,
            "dispense_volume_ml": 0,
            "safety_lock_reason": "No positive target watering volume requested."
        }

    clamped_dose = min(target_volume_ml, max_single_dose_ml)
    # 3. Calculate max pump run time at standard 12V 100ml/min mini pump
    max_pump_duration_seconds = max(2, int(clamped_dose / 100.0 * 60))

    return {
        "irrigation_allowed": True,
        "dispense_volume_ml": clamped_dose,
        "safety_lock_reason": "Safe to dispense within watchdog volume and time bounds.",
        "pump_watchdog_timeout_sec": max_pump_duration_seconds
    }

def calculate_watering_recommendation(
    species: str,
    health_status: str,
    stress_status: str,
    pot_size_cm: Optional[int] = 15,
    soil_type: Optional[str] = "Potting Mix",
    moisture_sensor_reading: Optional[float] = None,
    ambient_temp_c: Optional[float] = None
) -> Dict[str, Any]:
    """
    Intelligent botanical watering recommendation engine.
    Calculates watering state, checks soil requirements, and computes
    ml estimation strictly when pot dimensions and species context exist.
    """
    norm_status = health_status.lower()
    norm_stress = stress_status.lower()
    norm_species = (species or "").lower()

    # Species water appetite profile
    # drought tolerant: succulents, snake plant, zz plant, cacti
    is_drought_tolerant = any(x in norm_species for x in ["succulent", "snake", "sansevieria", "zz", "zamioculcas", "cactus", "aloe"])
    # moisture loving: ferns, calathea, peace lily, fittonia
    is_moisture_loving = any(x in norm_species for x in ["calathea", "peace lily", "spathiphyllum", "fern", "boston", "fittonia", "pothos"])

    # 1. Evaluate Condition & Stress
    if moisture_sensor_reading is not None:
        if moisture_sensor_reading < 20:
            status = "Water may be required"
            reason = f"Soil moisture reading ({moisture_sensor_reading:.0f}%) is below the healthy threshold for {species or 'indoor plants'}."
        elif moisture_sensor_reading > 70:
            status = "Possible overwatering"
            reason = f"Soil moisture reading ({moisture_sensor_reading:.0f}%) indicates saturated soil. Avoid adding water."
        else:
            status = "No immediate watering recommendation"
            reason = f"Soil moisture is currently in the optimal range ({moisture_sensor_reading:.0f}%)."
    elif "wilting" in norm_status or "wilting" in norm_stress or "droop" in norm_stress:
        # Wilting can stem from both dry root zone and root rot / waterlogging
        status = "Check soil before watering"
        reason = (
            "Visual drooping was detected. Because foliage drooping can be caused by both underwatering (desiccation) "
            "and overwatering (root hypoxia / suffocation), manual soil moisture verification is required."
        )
    elif "chlorosis" in norm_stress or ("yellow" in norm_stress and not norm_stress.startswith("no ")):
        if is_drought_tolerant:
            status = "Possible overwatering"
            reason = f"Yellowing foliage on drought-tolerant {species or 'succulent'} often indicates root zone over-saturation."
        else:
            status = "Check soil before watering"
            reason = "Leaf chlorosis detected. Check whether soil is waterlogged or depleted of nutrients."
    elif ("brown" in norm_stress and not norm_stress.startswith("no ")) or "necrosis" in norm_stress:
        status = "Check soil before watering"
        reason = "Visible browning has several possible causes. Check soil moisture before changing watering; the photo cannot confirm the cause."
    elif norm_status == "healthy":
        status = "No immediate watering recommendation"
        reason = "Foliage exhibits healthy turgor and normal vegetative vitality. Maintain scheduled checking cycle."
    elif norm_status in ["image unsuitable", "unscanned"]:
        status = "Insufficient information"
        reason = "Foliage condition could not be verified from the image."
    elif "not assessed" in norm_stress or "no visible" in norm_stress or "no obvious" in norm_stress or "inconclusive" in norm_status:
        status = "Check soil moisture before watering"
        reason = "A photo cannot measure soil moisture. Check the top 2 inches of soil and water only if it feels dry."
    else:
        status = "Watering condition uncertain"
        reason = "Symptoms observed may not be directly moisture-related. Check soil 2 inches below surface before watering."

    # 2. Water quantity estimation in millilitres (strictly when pot dimensions are known)
    quantity_ml = None
    assumptions = []
    limitations = []

    if pot_size_cm and pot_size_cm > 5 and pot_size_cm < 100:
        # Pot radius and approximate depth
        radius_cm = pot_size_cm / 2.0
        height_cm = pot_size_cm * 0.95
        # Soil volume = pi * r^2 * h (in cm^3 = ml)
        pot_volume_ml = math.pi * (radius_cm ** 2) * height_cm
        
        # Safe root zone hydration fraction: 12% to 18% of pot volume for potting soil
        if is_drought_tolerant:
            hydration_fraction = 0.08
        elif is_moisture_loving:
            hydration_fraction = 0.16
        else:
            hydration_fraction = 0.12

        suggested = int(round(pot_volume_ml * hydration_fraction / 25.0) * 25)
        
        if status in ["Water may be required", "Check soil before watering"]:
            quantity_ml = max(50, min(1500, suggested))
            assumptions.append(f"Standard {pot_size_cm} cm container diameter with {soil_type or 'well-draining potting soil'}.")
            assumptions.append(f"Estimated soil volume ~{int(pot_volume_ml)} ml.")
        elif status == "Possible overwatering":
            quantity_ml = None
            limitations.append("Water quantity omitted to prevent worsening suspected root waterlogging.")
    else:
        limitations.append("Precise millilitre quantity omitted: pot diameter is not configured.")

    if moisture_sensor_reading is None:
        limitations.append("No active hardware soil moisture sensor connected; assessment relies on visual leaf posture and species profile.")

    # 3. Practical watering instructions
    if status == "Water may be required":
        instructions = (
            f"If the top 2 inches of soil feel dry to the touch, slowly pour approximately {quantity_ml or 'a moderate quantity of'} ml "
            "at room temperature around the base of the plant until slight drainage occurs from the bottom holes. Empty the saucer after 15 minutes."
        )
    elif status == "Possible overwatering":
        instructions = (
            "Withhold watering immediately. Inspect the drainage holes to ensure excess water is not pooled. "
            "Allow soil to dry out significantly before applying any further water. Ensure bright, indirect airflow."
        )
    elif status == "Check soil before watering":
        instructions = (
            "Insert your finger or a wooden chopstick 2–3 inches into the soil. "
            f"If it comes out clean and dry, provide approximately {quantity_ml or '150–250'} ml of water. "
            "If it comes out damp with sticking soil, do not add water."
        )
    elif status == "Check soil moisture before watering":
        instructions = "Check the top 2 inches of soil by touch. If dry, water gradually; if damp, do not water. No amount is estimated because the image does not reveal soil moisture."
    else:
        instructions = (
            "No immediate hydration needed today. Continue periodic observation and inspect soil before the next scheduled check."
        )

    return {
        "watering_status": status,
        "watering_quantity_ml": quantity_ml,
        "watering_reason": reason,
        "watering_instructions": instructions,
        "assumptions": assumptions,
        "limitations": limitations,
        "pot_size_cm": pot_size_cm,
        "soil_type": soil_type,
    }
