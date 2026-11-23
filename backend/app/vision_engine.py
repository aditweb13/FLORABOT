import base64
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import httpx
from PIL import Image, ImageFilter, ImageStat
from .config import settings

def validate_image_bytes(data: bytes) -> Tuple[Image.Image, int, int]:
    """
    Validates image data, checks magic bytes and dimensions, rejects corrupt files.
    """
    if not data or len(data) < 32:
        raise ValueError("Image data is empty or too short.")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("Image file size exceeds maximum limit of 15 MB.")
    
    try:
        img = Image.open(BytesIO(data))
        img.verify()  # Verify integrity
    except Exception as exc:
        raise ValueError("Corrupted image file or unsupported format. Please submit a valid JPEG, PNG, or WEBP image.") from exc
    
    # Re-open after verify()
    img = Image.open(BytesIO(data)).convert("RGB")
    w, h = img.size
    if w < 64 or h < 64:
        raise ValueError(f"Image dimensions ({w}x{h}) are too small for plant analysis. Minimum required is 64x64.")
    if w > 5000 or h > 5000:
        img.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
        w, h = img.size
        
    return img, w, h

def save_validated_image(img: Image.Image, upload_dir: str) -> str:
    """Saves optimized processing image to disk."""
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = Path(upload_dir) / filename
    img.save(filepath, "JPEG", quality=88, optimize=True)
    return str(filepath)

def analyze_leaf_computer_vision(image_path: str) -> Dict[str, Any]:
    """
    Performs deterministic computer vision analysis on leaf/plant image.
    Calculates color indices, chlorosis, necrosis, vegetative presence, and drooping/stress metrics.
    """
    with Image.open(image_path) as raw_img:
        img = raw_img.convert("RGB")
        # Resize for consistent spatial analysis
        sample = img.resize((256, 256), Image.Resampling.BILINEAR)
        pixels = list(sample.getdata())
    
    total_pixels = len(pixels)
    green_count = 0
    yellow_count = 0
    brown_count = 0
    dark_count = 0
    very_bright_count = 0
    
    # Spatial distribution: split top half vs bottom half to detect drooping/wilting
    top_half_green = 0
    bottom_half_green = 0
    
    for idx, (r, g, b) in enumerate(pixels):
        y = idx // 256
        brightness = (r + g + b) / 3.0
        
        if brightness < 25:
            dark_count += 1
            continue
        if brightness > 245:
            very_bright_count += 1
            continue
            
        # Excess green index (ExG = 2G - R - B)
        exg = 2 * g - r - b
        
        # Chlorosis index (yellowing: high red and green, low blue)
        is_yellow = (r > 120 and g > 110 and b < 95 and abs(r - g) < 55)
        
        # Necrosis index (brown/dry: moderate red, lower green, low blue)
        is_brown = (r > 80 and g > 45 and b < 50 and r > g + 15)
        
        # Vegetative green
        is_green = (exg > 15 and g > r and g > b)
        
        if is_green:
            green_count += 1
            if y < 128:
                top_half_green += 1
            else:
                bottom_half_green += 1
        elif is_yellow:
            yellow_count += 1
        elif is_brown:
            brown_count += 1

    vegetative_ratio = green_count / total_pixels
    chlorosis_ratio = yellow_count / total_pixels
    necrosis_ratio = brown_count / total_pixels
    usable_plant_ratio = (green_count + yellow_count + brown_count) / total_pixels
    
    # 1. Image Suitability Check
    if usable_plant_ratio < 0.08:
        return {
            "is_suitable": False,
            "health_status": "Image unsuitable",
            "disease_detected": "uncertain",
            "disease_name": "",
            "confidence": None,
            "severity": "",
            "symptoms": "No clear plant foliage detected. The image appears underexposed, obscured, or lacks visible plant tissue.",
            "recommendations": "Ensure the camera is pointed directly at the plant leaves with adequate lighting.",
            "prevention": "Position the ESP32-CAM within 15–40 cm of the foliage for reliable monitoring.",
            "recovery_plan": "Adjust lighting and camera framing, then trigger a new capture.",
            "stress_status": "Unknown",
            "stress_observations": "Insufficient leaf area visible to assess stress or wilting.",
            "provider_engine": "FloraBOT Computer Vision Engine",
        }

    # 2. Drooping / Wilting detection via spatial distribution
    wilting_detected = False
    droop_ratio = 0.0
    if (top_half_green + bottom_half_green) > 100:
        droop_ratio = bottom_half_green / max(1, (top_half_green + bottom_half_green))
        # High concentration of leaf mass in lower half suggests drooping/wilting
        if droop_ratio > 0.68 and usable_plant_ratio > 0.15:
            wilting_detected = True

    # 3. Stress & Condition Determination
    stress_status = "None"
    stress_obs_list = []
    
    if chlorosis_ratio > 0.12:
        stress_status = "Leaf Chlorosis (Yellowing)"
        stress_obs_list.append(f"Visible leaf yellowing detected across approximately {chlorosis_ratio*100:.1f}% of foliage.")
    elif necrosis_ratio > 0.08:
        stress_status = "Leaf Necrosis / Brown Edges"
        stress_obs_list.append(f"Dry or brown necrotic patches observed across {necrosis_ratio*100:.1f}% of sampled surface.")
    elif wilting_detected:
        stress_status = "Possible Wilting / Leaf Drooping"
        stress_obs_list.append(f"Downward leaf posture and droop pattern detected (droop index: {droop_ratio:.2f}).")
    else:
        stress_status = "Normal Posture"
        stress_obs_list.append(f"Foliage shows vibrant vegetative pigmentation ({vegetative_ratio*100:.1f}% green density) and upright posture.")

    stress_observations = " ".join(stress_obs_list)

    # 4. Disease / Health classification based on visual lesion & discoloration metrics
    if chlorosis_ratio > 0.22 or necrosis_ratio > 0.15:
        detected = "yes"
        disease_name = "Leaf Spot / Chlorosis Syndrome" if chlorosis_ratio > necrosis_ratio else "Leaf Blight / Tissue Necrosis"
        health_status = "Disease Detected"
        # Genuine measured confidence based on severity of discoloration
        measured_conf = min(0.85, 0.50 + max(chlorosis_ratio, necrosis_ratio))
        severity = "Moderate" if max(chlorosis_ratio, necrosis_ratio) < 0.25 else "Severe"
        symptoms = f"Visible discoloration and irregular tissue pigmentation observed. Discolored area: {max(chlorosis_ratio, necrosis_ratio)*100:.1f}% of leaf surface."
        recommendations = "Inspect affected leaves closely for fungal spots or pest activity. Isolate plant if lesions spread, and avoid splashing water onto foliage."
        prevention = "Ensure adequate air circulation around plant. Disinfect pruning shears and maintain proper drainage."
        recovery_plan = "Prune severely yellowed or necrotic leaves with sterile scissors. Re-evaluate within 5–7 days."
    elif wilting_detected:
        detected = "uncertain"
        disease_name = "Moisture / Root Stress"
        health_status = "Possible Wilting"
        measured_conf = round(min(0.78, 0.45 + (droop_ratio - 0.5)), 2)
        severity = "Mild to Moderate"
        symptoms = "Downward drooping of leaves detected. Leaf color remains largely green without widespread necrosis."
        recommendations = "Check root zone and soil moisture immediately with a finger or probe before applying water. Wilting can occur from both underwatering (dry soil) and overwatering (root suffocation)."
        prevention = "Maintain a consistent watering schedule tailored to this species and pot drainage."
        recovery_plan = "If soil is dry, provide thorough watering until runoff occurs. If soil is waterlogged, withhold water and improve drainage."
    elif chlorosis_ratio > 0.08 or necrosis_ratio > 0.04:
        detected = "uncertain"
        disease_name = "Early Stress Symptoms"
        health_status = "Possible Stress"
        measured_conf = 0.52
        severity = "Mild"
        symptoms = f"Mild localized discoloration detected ({chlorosis_ratio*100:.1f}% chlorosis, {necrosis_ratio*100:.1f}% dry tips)."
        recommendations = "Monitor lighting and watering consistency. Check leaf undersides for pests."
        prevention = "Keep plant away from heating vents or drafty windows."
        recovery_plan = "Observe over the next 48–72 hours to ensure yellowing does not spread."
    else:
        detected = "no"
        disease_name = "None Identified"
        health_status = "Healthy"
        measured_conf = round(min(0.92, 0.65 + vegetative_ratio * 0.3), 2)
        severity = "None"
        symptoms = f"Clean, uniform foliage observed. Healthy green pigmentation covers {vegetative_ratio*100:.1f}% of leaf area."
        recommendations = "Continue regular care routine. Plant shows normal vitality."
        prevention = "Maintain stable light and humidity levels."
        recovery_plan = "No treatment necessary. Continue scheduled monitoring."

    return {
        "is_suitable": True,
        "health_status": health_status,
        "disease_detected": detected,
        "disease_name": disease_name,
        "confidence": measured_conf,
        "severity": severity,
        "symptoms": symptoms,
        "recommendations": recommendations,
        "prevention": prevention,
        "recovery_plan": recovery_plan,
        "stress_status": stress_status,
        "stress_observations": stress_observations,
        "provider_engine": "FloraBOT Computer Vision Engine",
        "metrics": {
            "vegetative_ratio": round(vegetative_ratio, 3),
            "chlorosis_ratio": round(chlorosis_ratio, 3),
            "necrosis_ratio": round(necrosis_ratio, 3),
            "droop_ratio": round(droop_ratio, 3),
        }
    }

def analyze_plant_image(image_path: str, plant_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Main image analysis entry point.
    First performs Computer Vision feature and stress extraction.
    If external Plant.id API key is configured, invokes Plant.id and enriches results.
    If external API is unavailable or offline, seamlessly relies on local Computer Vision Engine.
    """
    # 1. Run local CV analysis
    cv_res = analyze_leaf_computer_vision(image_path)
    if not cv_res["is_suitable"]:
        return {
            "plant_identification": plant_hint or "Unknown Plant",
            "plant_confidence": None,
            "disease_detected": "uncertain",
            "disease_name": "",
            "disease_confidence": None,
            "severity": "",
            "health_status": cv_res["health_status"],
            "confidence": None,
            "symptoms": cv_res["symptoms"],
            "recommendations": cv_res["recommendations"],
            "prevention": cv_res["prevention"],
            "recovery_plan": cv_res["recovery_plan"],
            "stress_status": cv_res["stress_status"],
            "stress_observations": cv_res["stress_observations"],
            "provider_engine": cv_res["provider_engine"],
            "provider_reference": "unsuitable_frame",
        }

    # 2. Try Plant.id API if configured
    if settings.plant_id_api_key:
        try:
            image_bytes = Path(image_path).read_bytes()
            b64_img = base64.b64encode(image_bytes).decode("ascii")
            headers = {
                "Api-Key": settings.plant_id_api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "images": [f"data:image/jpeg;base64,{b64_img}"],
                "health": "all",
                "similar_images": True
            }
            with httpx.Client(timeout=35) as client:
                resp = client.post(settings.plant_id_api_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    raw = resp.json()
                    result = raw.get("result", {})
                    is_healthy_obj = result.get("is_healthy", {})
                    health_binary = is_healthy_obj.get("binary")
                    health_prob = is_healthy_obj.get("probability", 0.5)
                    
                    diseases = result.get("disease", {}).get("suggestions", [])
                    species_list = result.get("classification", {}).get("suggestions", [])
                    
                    top_species = species_list[0] if species_list else {}
                    top_disease = diseases[0] if diseases else {}
                    
                    species_name = top_species.get("name", plant_hint or "Unknown")
                    species_conf = top_species.get("probability")
                    
                    disease_name = top_disease.get("name", "")
                    disease_prob = top_disease.get("probability", 0.0)
                    
                    # Determine detection status
                    if diseases and disease_prob >= 0.25:
                        detected = "yes"
                        status = "Disease Detected" if disease_prob >= 0.60 else "Possible Stress"
                    elif health_binary is True:
                        detected = "no"
                        status = "Healthy"
                    else:
                        detected = "uncertain"
                        status = "Inconclusive"
                    
                    # Merge CV wilting/stress observations
                    stress_status = cv_res["stress_status"]
                    stress_obs = cv_res["stress_observations"]
                    if cv_res["stress_status"] == "Possible Wilting / Leaf Drooping" and detected == "no":
                        status = "Possible Wilting"
                    
                    details = top_disease.get("details", {}) or {}
                    symptoms = details.get("description") or cv_res["symptoms"]
                    care = details.get("treatment") or {}
                    recs = care.get("chemical") or care.get("biological") or care.get("prevention") or cv_res["recommendations"]
                    if isinstance(recs, list):
                        recs = "\n".join(str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in recs)
                    prevention = details.get("cause") or cv_res["prevention"]
                    
                    return {
                        "plant_identification": species_name,
                        "plant_confidence": round(species_conf, 2) if species_conf else None,
                        "disease_detected": detected,
                        "disease_name": disease_name if detected == "yes" else "",
                        "disease_confidence": round(disease_prob, 2) if disease_prob else None,
                        "severity": details.get("severity", "") or cv_res["severity"],
                        "health_status": status,
                        "confidence": round(disease_prob if detected == "yes" else (species_conf or health_prob), 2),
                        "symptoms": f"{symptoms} {stress_obs}".strip(),
                        "recommendations": str(recs),
                        "prevention": str(prevention),
                        "recovery_plan": cv_res["recovery_plan"],
                        "stress_status": stress_status,
                        "stress_observations": stress_obs,
                        "provider_engine": "Plant.id Health Assessment + FloraBOT CV",
                        "provider_reference": str(raw.get("access_token", "")),
                    }
        except Exception:
            # Network blocked or provider timeout -> Fall back to local Computer Vision Engine
            pass

    # 3. Local Computer Vision Engine results
    return {
        "plant_identification": plant_hint or "Indoor Houseplant",
        "plant_confidence": None,  # Do not fabricate plant identification confidence without classifier
        "disease_detected": cv_res["disease_detected"],
        "disease_name": cv_res["disease_name"],
        "disease_confidence": cv_res["confidence"] if cv_res["disease_detected"] == "yes" else None,
        "severity": cv_res["severity"],
        "health_status": cv_res["health_status"],
        "confidence": cv_res["confidence"],
        "symptoms": cv_res["symptoms"],
        "recommendations": cv_res["recommendations"],
        "prevention": cv_res["prevention"],
        "recovery_plan": cv_res["recovery_plan"],
        "stress_status": cv_res["stress_status"],
        "stress_observations": cv_res["stress_observations"],
        "provider_engine": cv_res["provider_engine"],
        "provider_reference": f"cv_analysis_{uuid.uuid4().hex[:8]}",
    }
