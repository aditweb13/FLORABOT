import math
from typing import Any, Dict, Optional

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
    elif "chlorosis" in norm_stress or "yellow" in norm_stress:
        if is_drought_tolerant:
            status = "Possible overwatering"
            reason = f"Yellowing foliage on drought-tolerant {species or 'succulent'} often indicates root zone over-saturation."
        else:
            status = "Check soil before watering"
            reason = "Leaf chlorosis detected. Check whether soil is waterlogged or depleted of nutrients."
    elif norm_status == "healthy":
        status = "No immediate watering recommendation"
        reason = "Foliage exhibits healthy turgor and normal vegetative vitality. Maintain scheduled checking cycle."
    elif norm_status in ["image unsuitable", "unscanned"]:
        status = "Insufficient information"
        reason = "Foliage condition could not be verified from the image."
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
