import base64
import json
import logging
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
from .config import settings

try:
    import numpy as np
    from scipy.ndimage import laplace
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

logger = logging.getLogger(__name__)

def _provider_failure(provider: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = ""
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("message") or body.get("error") or "")
        except (ValueError, TypeError):
            pass
        suffix = f": {detail[:240]}" if detail else ""
        message = f"{provider} returned HTTP {exc.response.status_code}{suffix}."
    else:
        message = f"{provider} request failed ({type(exc).__name__})."
    logger.warning("%s", message)
    return message

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


def render_detection_overlay(image_path: str, detections: list[dict], output_path: str) -> str:
    """Write a derived annotated copy; never modify the source capture."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    line_width = max(2, round(min(width, height) / 240))
    font = ImageFont.load_default(size=max(12, min(24, round(min(width, height) / 30))))
    for item in detections:
        x1 = max(0, min(width - 1, round(float(item["x1"]) * width)))
        y1 = max(0, min(height - 1, round(float(item["y1"]) * height)))
        x2 = max(x1 + 1, min(width, round(float(item["x2"]) * width)))
        y2 = max(y1 + 1, min(height, round(float(item["y2"]) * height)))
        draw.rectangle((x1, y1, x2, y2), outline="#ffc857", width=line_width)
        caption = f'{item["label"]} {float(item["confidence"]):.0%}'
        bounds = draw.textbbox((0, 0), caption, font=font)
        text_w, text_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        text_y = max(0, y1 - text_h - 6)
        draw.rectangle((x1, text_y, min(width, x1 + text_w + 8), text_y + text_h + 6), fill="#244232")
        draw.text((x1 + 4, text_y + 3), caption, fill="white", font=font)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "JPEG", quality=92, optimize=True)
    return output_path

def assess_image_quality(image_path: str) -> Dict[str, Any]:
    """
    Algorithmic image quality check analyzing focus blur, exposure levels,
    and contrast dynamics. Rejects unanalyzable frames before running diagnostics.
    """
    with Image.open(image_path) as raw_img:
        gray = raw_img.convert("L")

    if HAS_SCIPY:
        arr = np.array(gray, dtype=np.float64)
        lap_var = float(laplace(arr).var())
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr))
        over_pct = float(np.mean(arr >= 248))
        under_pct = float(np.mean(arr <= 12))
    else:
        stat = ImageStat.Stat(gray)
        mean_val = float(stat.mean[0])
        std_val = float(stat.stddev[0])
        edges = gray.filter(ImageFilter.FIND_EDGES)
        lap_var = float(ImageStat.Stat(edges).var[0]) / 15.0
        pixels = list(gray.getdata())
        total = max(1, len(pixels))
        over_pct = sum(1 for p in pixels if p >= 248) / total
        under_pct = sum(1 for p in pixels if p <= 12) / total

    is_blurry = lap_var < 3.0
    is_dark = mean_val < 22.0 or under_pct > 0.65
    is_bright = mean_val > 235.0 or over_pct > 0.45
    is_low_contrast = std_val < 10.0

    issues = []
    if is_blurry:
        issues.append(f"Image is out of focus / blurry (blur score: {lap_var:.2f})")
    if is_dark:
        issues.append(f"Severe underexposure / scene too dark (mean brightness: {mean_val:.1f})")
    if is_bright:
        issues.append(f"Severe overexposure / excessive glare (mean brightness: {mean_val:.1f})")
    if is_low_contrast and not (is_dark or is_bright):
        issues.append(f"Extremely low contrast or blank scene (contrast: {std_val:.1f})")

    is_suitable = len(issues) == 0

    return {
        "is_suitable": is_suitable,
        "blur_score": round(lap_var, 2),
        "is_blurry": is_blurry,
        "exposure_status": "underexposed" if is_dark else ("overexposed" if is_bright else "normal"),
        "mean_brightness": round(mean_val, 1),
        "contrast_std": round(std_val, 1),
        "issues": issues,
        "rejection_reason": "; ".join(issues) if issues else ""
    }

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

def _identify_with_plantnet(image_path: str) -> Dict[str, Any]:
    if not settings.plantnet_api_key:
        return {"error": "PLANTNET_API_KEY is not configured."}
    try:
        with open(image_path, "rb") as image_file, httpx.Client(timeout=25) as client:
            response = client.post(
                "https://my-api.plantnet.org/v2/identify/all",
                params={"api-key": settings.plantnet_api_key, "lang": "en"},
                files={"images": (Path(image_path).name, image_file, "image/jpeg")},
                data={"organs": "leaf"},
            )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return {}
        first = results[0]
        species = first.get("species", {})
        scientific_name = species.get("scientificNameWithoutAuthor") or species.get("scientificName") or ""
        return {
            "name": scientific_name,
            "score": float(first.get("score", 0)),
            "common_names": species.get("commonNames", []),
            "candidates": [
                {"scientific_name": item.get("species", {}).get("scientificNameWithoutAuthor") or item.get("species", {}).get("scientificName", ""),
                 "common_names": item.get("species", {}).get("commonNames", []),
                 "score": float(item.get("score", 0))}
                for item in results[:5]
            ],
            "provider_version": "Pl@ntNet API v2",
        }
    except Exception as exc:
        return {"error": _provider_failure("Pl@ntNet", exc)}


def _analyze_with_groq_vision(image_path: str) -> Dict[str, Any]:
    if not settings.groq_api_key:
        return {"error": "GROQ_API_KEY is not configured."}
    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=82, optimize=True)
            image_bytes = buffer.getvalue()
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "Assess only visible evidence in this plant photo. Return one JSON object with keys: "
            "assessment (healthy, possible_disease, or inconclusive), disease_name, "
            "severity, symptoms, recommendations, prevention, recovery_plan, stress_status, stress_observations. "
            "Do not infer root, watering, pest, or environmental conditions that are not visible. "
            "Do not call a leaf healthy just because it is green. Separate observed symptoms from possible causes. "
            "If disease cannot be distinguished from this view, use inconclusive and say what photo/details are needed. "
            "Do not claim a specific pathogen without distinctive visual evidence."
        )
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "temperature": 0.1,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=12) as client:
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json=payload,
            )
            response.raise_for_status()
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError("Vision model returned an invalid response.")
        return result
    except Exception as exc:
        return {"error": f"Groq vision request failed: {exc}"}


def _assess_with_plant_id(image_path: str) -> Dict[str, Any]:
    """Call the configured Plant.id v3 health-assessment endpoint."""
    if not settings.plant_id_api_key:
        return {}
    try:
        image_bytes = Path(image_path).read_bytes()
        payload = {
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "health": "only",
        }
        with httpx.Client(timeout=10) as client:
            response = client.post(
                settings.plant_id_api_url,
                headers={"Api-Key": settings.plant_id_api_key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        result = data.get("result", {})
        is_plant = result.get("is_plant", {}).get("binary")
        if is_plant is False:
            return {"is_plant": False, "is_plant_probability": result.get("is_plant", {}).get("probability")}
        health = result.get("is_healthy", {})
        disease_suggestions = result.get("disease", {}).get("suggestions", []) or []
        top_disease = disease_suggestions[0] if disease_suggestions else None
        return {
            "is_plant": is_plant,
            "is_plant_probability": result.get("is_plant", {}).get("probability"),
            "healthy": health.get("binary"),
            "health_probability": health.get("probability"),
            "disease_name": top_disease.get("name", "") if top_disease else "",
            "disease_probability": top_disease.get("probability") if top_disease else None,
            "disease_candidates": disease_suggestions[:5],
            "model": data.get("model_version", "Plant.id v3"),
        }
    except Exception as exc:
        return {"error": f"Plant.id request failed: {exc}"}


def analyze_plant_image(image_path: str, plant_hint: Optional[str] = None) -> Dict[str, Any]:
    """Run PlantNet species identification and hosted image health assessors with quality screening."""

    # 0. Algorithmic Image Quality Gate
    quality = assess_image_quality(image_path)
    if not quality["is_suitable"]:
        return {
            "plant_identification": plant_hint or "Unknown Plant",
            "plant_confidence": None,
            "identification_candidates": [],
            "detections": [],
            "model_metadata": {},
            "diagnostic_error": quality["rejection_reason"],
            "disease_detected": "uncertain",
            "disease_name": "",
            "disease_confidence": None,
            "severity": "Unassessed",
            "health_status": "Image needs a clearer view",
            "confidence": None,
            "symptoms": f"Quality screening check rejected image: {quality['rejection_reason']}. Reliable leaf diagnosis requires an in-focus capture under clear lighting.",
            "recommendations": "Retake the photo with the camera focused on the leaf surface and balanced lighting.",
            "prevention": "Avoid direct lens glare or dark shadows when capturing plant leaves.",
            "recovery_plan": "Position camera 15-40 cm away and trigger a new capture.",
            "stress_status": "Unknown",
            "stress_observations": f"Quality gate rejected image: {quality['rejection_reason']}",
            "provider_engine": "FloraBOT Quality Gate + Heuristic Screening",
            "provider_reference": "quality_gate_screening",
            "image_quality": quality
        }

    species_result = _identify_with_plantnet(image_path)
    species_name = species_result.get("name", "")
    species_score = species_result.get("score")
    diagnostics = []
    if species_result.get("error"):
        diagnostics.append(species_result["error"])
    if not species_name or (species_score is not None and species_score < 0.15):
        known_hint = (plant_hint or "").strip()
        species_name = known_hint if known_hint.casefold() not in {"unknown", "unknown plant", "species not identified"} else "Unknown Plant"
        species_score = None

    providers_not_called = object()
    plant_id_result: Any = providers_not_called
    groq_vision_result: Any = providers_not_called

    def get_plant_id_result() -> Dict[str, Any]:
        nonlocal plant_id_result
        if plant_id_result is providers_not_called:
            plant_id_result = {}
            if settings.plant_id_api_key:
                try:
                    plant_id_result = _assess_with_plant_id(image_path)
                except Exception as exc:
                    diagnostics.append(_provider_failure("Plant.id", exc))
            else:
                diagnostics.append("PLANT_ID_API_KEY is not configured; Plant.id health assessment was skipped.")
        return plant_id_result

    def get_groq_vision_result() -> Dict[str, Any]:
        nonlocal groq_vision_result
        if groq_vision_result is providers_not_called:
            groq_vision_result = {}
            if settings.groq_api_key:
                try:
                    groq_vision_result = _analyze_with_groq_vision(image_path)
                except Exception as exc:
                    diagnostics.append(_provider_failure("Groq Vision", exc))
            else:
                diagnostics.append("GROQ_API_KEY is not configured; Groq image assessment was skipped.")
        return groq_vision_result

    # Run YOLO localized plant disease detection
    try:
        from .yolo_detector import detect_plant_diseases
        yolo_res = detect_plant_diseases(image_path, conf_threshold=settings.min_confidence_threshold)
        detections = yolo_res.get("detections", [])
        yolo_meta = yolo_res.get("model_metadata", {})
    except Exception as exc:
        diagnostics.append(_provider_failure("YOLO Disease Detector", exc))
        detections = []
        yolo_meta = {}

    def result(**values: Any) -> Dict[str, Any]:
        # Ensure every capture invokes both hosted image assessors.
        get_plant_id_result()
        get_groq_vision_result()
        return {
            "plant_identification": species_name,
            "plant_confidence": round(float(species_score), 4) if species_score is not None else None,
            "identification_candidates": species_result.get("candidates", []),
            "detections": detections,
            "model_metadata": yolo_meta,
            "diagnostic_error": "; ".join(diagnostics),
            "image_quality": quality,
            **values,
        }

    # Prime provider results before choosing the primary image assessor.
    health = None
    if settings.plant_id_api_key:
        health = get_plant_id_result()

    vision = None
    if settings.groq_api_key:
        vision = get_groq_vision_result()

    try:
        local = analyze_leaf_computer_vision(image_path)
    except Exception as exc:
        diagnostics.append(_provider_failure("Local visual stress analysis", exc))
        local = {"is_suitable": False, "symptoms": "The image could not be analyzed.", "metrics": {}}
    color_metrics = local.get("metrics", {})
    if not local.get("is_suitable"):
        visual_stress = "Unable to assess"
        visual_stress_detail = "Too little clear foliage is visible to assess stress."
    elif color_metrics.get("chlorosis_ratio", 0) > 0.08:
        visual_stress = "Visible yellowing"
        visual_stress_detail = f"Yellow pixels cover {color_metrics['chlorosis_ratio']:.1%} of the image; this may reflect foliage, lighting, or background."
    elif color_metrics.get("necrosis_ratio", 0) > 0.04:
        visual_stress = "Visible browning"
        visual_stress_detail = f"Brown pixels cover {color_metrics['necrosis_ratio']:.1%} of the image; this is a visual indicator, not a disease diagnosis."
    else:
        visual_stress = "No obvious yellowing or browning"
        visual_stress_detail = "The image color screen did not find a strong yellow or brown signal; it does not measure hydration."

    # Use Plant.id when configured; the local color screen is only a fallback.
    if settings.plant_id_api_key:
        try:
            health = get_plant_id_result()
            groq_recognized_plant = vision.get("assessment") in {"healthy", "possible_disease"}
            if health.get("is_plant") is False and not groq_recognized_plant:
                return result(
                    disease_detected="uncertain", disease_name="", disease_confidence=None,
                    confidence=health.get("is_plant_probability"), severity="Not assessed",
                    health_status="No plant detected by Plant.id",
                    symptoms="Plant.id did not confirm plant tissue in this image.",
                    recommendations="Point the camera at a clear, well-lit leaf or whole plant and capture again.",
                    prevention="", recovery_plan="", stress_status=visual_stress,
                    stress_observations=visual_stress_detail,
                    provider_engine="Plant.id v3 image-level health assessment",
                    provider_reference="plant_id_health_assessment",
                )
            health_probability = health.get("health_probability")
            suggestion = health.get("disease_name", "")
            disease_probability = health.get("disease_probability")
            if suggestion or health.get("healthy") is not None:
                confirmed_candidate = bool(suggestion and disease_probability is not None and disease_probability >= settings.min_confidence_threshold)
                disease_name = suggestion or ""
                score = disease_probability if suggestion else health_probability
                healthy = health.get("healthy") is True and not confirmed_candidate
                status = (f"Possible {disease_name} (Plant.id)" if confirmed_candidate else
                          "No disease indicated by Plant.id" if healthy else
                          f"Possible {disease_name} (below review threshold)" if suggestion else "Inconclusive")
                candidate_text = (f"Plant.id's top image-level candidate is {disease_name} ({disease_probability:.0%}); "
                                  "it is a candidate, not a localized lesion." if suggestion and disease_probability is not None else
                                  "Plant.id returned an image-level health assessment; it does not provide localized boxes.")
                return result(
                    disease_detected="yes" if confirmed_candidate else "no" if healthy else "uncertain",
                    disease_name=disease_name, disease_confidence=disease_probability if suggestion else None,
                    confidence=score, severity="Not graded by image-level provider", health_status=status,
                    symptoms=candidate_text,
                    recommendations="Inspect the affected leaves and confirm symptoms before applying treatment.",
                    prevention="Keep foliage dry and monitor for spread if visible lesions are present.",
                    recovery_plan="Capture a clear follow-up image of the same leaves.",
                    stress_status=visual_stress,
                    stress_observations=visual_stress_detail + " Plant.id's health probability is not a soil-moisture measurement.",
                    provider_engine="Plant.id v3 image-level health assessment",
                    provider_reference="plant_id_health_assessment",
                )
        except Exception as exc:
            diagnostics.append(_provider_failure("Plant.id", exc))

    if vision:
        try:
            vision = get_groq_vision_result()
            assessment = str(vision.get("assessment", "inconclusive")).casefold()
            disease_name = str(vision.get("disease_name", "")).strip()
            is_possible = assessment == "possible_disease" and bool(disease_name)
            is_healthy = assessment == "healthy"
            return result(
                disease_detected="uncertain" if is_possible or not is_healthy else "no",
                disease_name=disease_name if is_possible else "", disease_confidence=None, confidence=None,
                severity=str(vision.get("severity") or "Not assessed"),
                health_status=f"{'Possible visual issue' if is_possible else 'No visible disease signs' if is_healthy else 'Inconclusive'} (Groq Vision)",
                symptoms=str(vision.get("symptoms") or "Groq Vision returned no symptom description."),
                recommendations=str(vision.get("recommendations") or "Inspect the foliage and capture a closer image."),
                prevention=str(vision.get("prevention") or ""), recovery_plan=str(vision.get("recovery_plan") or ""),
                stress_status=str(vision.get("stress_status") or visual_stress),
                stress_observations=str(vision.get("stress_observations") or visual_stress_detail),
                provider_engine=f"Groq Vision ({settings.groq_model})",
                provider_reference="groq_vision_image_assessment",
            )
        except Exception as exc:
            diagnostics.append(_provider_failure("Groq Vision", exc))

    if not local.get("is_suitable"):
        stress_status = visual_stress
        stress_observations = visual_stress_detail
        health_status = "Image needs a clearer view"
        symptoms = local.get("symptoms", "Retake a close, well-lit image of the leaves.")
        recommendations = local.get("recommendations", "Frame several leaves clearly and retake the image.")
    else:
        stress_status = visual_stress
        stress_observations = visual_stress_detail
        health_status = "Inconclusive"
        symptoms = "The configured image providers found no confident disease result. The color screen reports visible changes only."
        recommendations = "Use a sharp, close-up photo of the affected leaf. Do not treat based on color screening alone."

    return result(
        disease_detected="uncertain", disease_name="", disease_confidence=None, confidence=None,
        severity="Not assessed", health_status=health_status, symptoms=symptoms,
        recommendations=recommendations, prevention="Avoid treatment until a specific problem is identified.",
        recovery_plan="Retake the same leaf in bright, even light and compare visible changes.",
        stress_status=stress_status, stress_observations=stress_observations,
        provider_engine="Plant.id / Groq Vision + local image color screen",
        provider_reference="hosted_health_assessment_and_local_visual_fallback",
    )
