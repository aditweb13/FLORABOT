import base64, json, os, uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, KeepTogether
from .config import settings

def ensure_dirs():
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.report_dir).mkdir(parents=True, exist_ok=True)

def save_image(data: bytes, filename: str) -> str:
    ensure_dirs()
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((1800, 1800))
        safe = f"{uuid.uuid4().hex}.jpg"
        path = Path(settings.upload_dir) / safe
        image.save(path, "JPEG", quality=88, optimize=True)
        return str(path)
    except Exception as exc:
        raise ValueError("Please upload a valid JPG, PNG, or WEBP image.") from exc

def analyze_plant(path: str):
    if not settings.plant_id_api_key:
        raise RuntimeError("Plant diagnosis is not configured. Add PLANT_ID_API_KEY to backend/.env.")
    image = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    with httpx.Client(timeout=45) as client:
        response = client.post(settings.plant_id_api_url, headers={"Api-Key": settings.plant_id_api_key, "Content-Type": "application/json"}, json={"images": [f"data:image/jpeg;base64,{image}"], "health": "all", "similar_images": True})
    if response.status_code == 429: raise RuntimeError("Plant diagnosis is busy. Please wait a moment and try again.")
    if response.status_code in (401, 403): raise RuntimeError("Plant diagnosis credentials were rejected. Check PLANT_ID_API_KEY.")
    response.raise_for_status()
    raw = response.json()
    result = raw.get("result", {})
    health = result.get("is_healthy", {}).get("binary")
    diseases = result.get("disease", {}).get("suggestions", [])
    species = result.get("classification", {}).get("suggestions", [])
    top_species = species[0] if species else {}
    top_disease = diseases[0] if diseases else {}
    confidence = top_disease.get("probability") if top_disease else (top_species.get("probability") if top_species else None)
    uncertain = health is None and not diseases
    detected = "yes" if diseases and top_disease.get("probability", 0) >= 0.25 else ("no" if health is True else "uncertain")
    status = "Disease Detected" if detected == "yes" else ("Healthy" if detected == "no" else "Inconclusive")
    if detected == "yes" and top_disease.get("probability", 0) < .65: status = "Needs Attention"
    details = top_disease.get("details") or {}
    symptoms = details.get("description") or ("The image appears healthy." if detected == "no" else "The image result is uncertain; capture a clear, well-lit close-up of the affected leaf.")
    care = details.get("treatment") or {}
    recs = care.get("chemical") or care.get("biological") or care.get("prevention") or ["Remove badly affected leaves with clean tools.", "Avoid wetting foliage and improve airflow.", "Recheck the plant in 5–7 days."]
    if isinstance(recs, list): recs = "\n".join(str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in recs)
    prevention = details.get("cause") or "Keep leaves dry, provide suitable light and airflow, and disinfect tools between plants."
    return {"raw": raw, "plant_identification": top_species.get("name", "Unknown"), "disease_detected": detected, "disease_name": top_disease.get("name", "") if detected == "yes" else "", "severity": details.get("severity", "") or "", "health_status": status, "confidence": confidence, "symptoms": symptoms, "recommendations": str(recs), "prevention": str(prevention), "provider_reference": str(raw.get("access_token", ""))}

def chat_reply(messages, context=""):
    if not settings.groq_api_key: raise RuntimeError("Plant chat is not configured. Add GROQ_API_KEY to backend/.env.")
    system = "You are FloraBot, a careful plant-care assistant. Answer in simple English, usually 2–6 sentences. Be practical and admit uncertainty. Do not diagnose from text alone. Use the supplied plant context when relevant. " + context
    payload = {"model": settings.groq_model, "messages": [{"role": "system", "content": system}] + messages[-16:], "temperature": .35, "max_tokens": 500}
    with httpx.Client(timeout=35) as client:
        response = client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.groq_api_key}"}, json=payload)
    if response.status_code == 429: raise RuntimeError("FloraBot chat is busy. Please try again shortly.")
    if response.status_code in (401, 403): raise RuntimeError("Chat credentials were rejected. Check GROQ_API_KEY.")
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_report(plant, analysis, output):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="GreenTitle", parent=styles["Title"], textColor=colors.HexColor("#174b35"), fontSize=21, leading=26, spaceAfter=8))
    styles.add(ParagraphStyle(name="SectionGreen", parent=styles["Heading2"], textColor=colors.HexColor("#26734d"), spaceBefore=12, spaceAfter=5))
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=48, leftMargin=48, topMargin=46, bottomMargin=46)
    story = [Paragraph("FloraBot", styles["GreenTitle"]), Paragraph("Plant Health &amp; Disease Analysis Report", styles["Heading2"]), Paragraph(f"Report ID FB-{uuid.uuid4().hex[:10].upper()}  ·  Generated {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}", styles["Normal"]), Spacer(1, 14)]
    story += [Paragraph("Plant details", styles["SectionGreen"])]
    rows = [["Plant", plant.name, "Species", analysis.plant_identification or plant.species], ["Plant ID", str(plant.id), "Registered", plant.registered_at.strftime("%Y-%m-%d") if plant.registered_at else "—"], ["Location", plant.location or "Not specified", "Analysis", analysis.timestamp.strftime("%Y-%m-%d %H:%M")]]
    table = Table(rows, colWidths=[.9*inch, 2.35*inch, .9*inch, 2.35*inch]); table.setStyle(TableStyle([("BACKGROUND", (0,0),(0,-1),colors.HexColor("#eef5ef")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#eef5ef")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#dce6df")),("PADDING",(0,0),(-1,-1),7)])); story.append(table)
    if os.path.exists(analysis.image):
        try:
            img = RLImage(analysis.image, width=3.2*inch, height=2.2*inch, kind="proportional"); story += [Paragraph("Analyzed leaf image", styles["SectionGreen"]), img]
        except Exception: pass
    severity=(analysis.severity or "").strip()
    if not severity or any(marker in severity.lower() for marker in ("not provided","unavailable","unknown")):severity="Severity unavailable"
    story += [Paragraph("Diagnosis", styles["SectionGreen"]), Paragraph(f"Health status: <b>{analysis.health_status}</b><br/>Disease detected: <b>{analysis.disease_detected.title()}</b><br/>Disease: {analysis.disease_name or 'None identified'}<br/>Severity: {severity}<br/>Provider confidence: {f'{analysis.confidence*100:.1f}%' if analysis.confidence is not None else 'Not provided'}", styles["Normal"])]
    for title, value in [("Symptoms & findings", analysis.symptoms), ("Treatment plan", analysis.recommendations), ("Prevention", analysis.prevention), ("Follow-up", "Recheck in 5–7 days. Monitor new growth, leaf spots, wilting, and spread to nearby leaves. Seek local horticultural advice if symptoms worsen.")]:
        story += [Paragraph(title, styles["SectionGreen"]), Paragraph((value or "No additional information provided.").replace("\n", "<br/>"), styles["BodyText"])]
    story += [Paragraph("What to do", styles["SectionGreen"]), Paragraph("• Follow the treatment guidance above<br/>• Use clean tools and observe the plant over the next week<br/>• Confirm product labels are suitable for your plant", styles["BodyText"]), Paragraph("What to avoid", styles["SectionGreen"]), Paragraph("• Avoid applying multiple treatments at once<br/>• Avoid aggressive treatment when the result is uncertain<br/>• Do not compost potentially infected leaves", styles["BodyText"])]
    doc.build(story)
