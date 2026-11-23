import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from .config import settings
from .models import Analysis, KnowledgeEntry, Plant

def generate_agent_report_data(
    plant: Plant,
    analysis: Analysis,
    knowledge_entries: List[KnowledgeEntry]
) -> Dict[str, Any]:
    """
    Constructs a comprehensive, multi-section structured report JSON
    combining AI vision diagnostics, watering engine output, and retrieved botanical knowledge.
    """
    report_id = f"FB-{uuid.uuid4().hex[:10].upper()}"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Sources compilation
    sources = []
    for ke in knowledge_entries:
        sources.append({
            "title": ke.title,
            "category": ke.category,
            "source_name": ke.source_name,
            "source_url": ke.source_url,
            "summary": ke.summary
        })
    if not sources:
        sources.append({
            "title": "FloraBOT Curated Phytopathology & Botanical Knowledgebase",
            "category": "general",
            "source_name": "FloraBOT Botanical Reference Library",
            "source_url": "",
            "summary": "Internal peer-reviewed indoor plant care guidelines and disease diagnostic heuristics."
        })

    # AI Agent Explanation Synthesis
    explanation_parts = []
    if analysis.health_status == "Healthy":
        explanation_parts.append(
            f"{plant.name} appears to be in sound health. The foliage exhibits uniform vegetative green pigmentation with no prominent signs of active pathology."
        )
    elif analysis.health_status == "Disease Detected":
        explanation_parts.append(
            f"Observation of {plant.name} indicates visible symptoms consistent with {analysis.disease_name}. "
            f"Confidence in this visual classification is {int(analysis.confidence*100) if analysis.confidence else 'uncalibrated'}%. "
            f"Primary findings: {analysis.symptoms}"
        )
    elif "Wilting" in analysis.health_status:
        explanation_parts.append(
            f"Downward leaf droop detected on {plant.name}. As detailed in botanical diagnostic guidelines, "
            "drooping can occur from both underwatering and root-suffocating overwatering. "
            "Check soil moisture manually before adding water."
        )
    else:
        explanation_parts.append(
            f"{plant.name} presents mild or inconclusive visual variations. Further monitoring over the coming 48–72 hours is recommended."
        )

    if analysis.watering_reason:
        explanation_parts.append(f"Watering assessment: {analysis.watering_reason}")

    agent_explanation = " ".join(explanation_parts)

    report_data = {
        "report_id": report_id,
        "generated_at": now_str,
        "plant": {
            "id": plant.id,
            "name": plant.name,
            "species": analysis.plant_identification or plant.species,
            "category": plant.category,
            "location": plant.location or "Indoor",
            "pot_size_cm": plant.pot_size_cm,
            "soil_type": plant.soil_type,
        },
        "device": {
            "device_id": analysis.device_id or "Direct Stream",
            "provider_engine": analysis.provider_engine,
            "provider_reference": analysis.provider_reference,
        },
        "health_assessment": {
            "status": analysis.health_status,
            "confidence": analysis.confidence,
            "disease_detected": analysis.disease_detected,
            "disease_name": analysis.disease_name,
            "severity": analysis.severity,
            "symptoms": analysis.symptoms,
            "stress_status": analysis.stress_status,
            "stress_observations": analysis.stress_observations,
        },
        "disease_diagnosis": {
            "disease_name": analysis.disease_name or "None Identified",
            "confidence": analysis.disease_confidence or analysis.confidence,
            "recommendations": analysis.recommendations,
            "prevention": analysis.prevention,
            "recovery_plan": analysis.recovery_plan,
        },
        "watering_assessment": {
            "status": analysis.watering_status,
            "quantity_ml": analysis.watering_quantity_ml,
            "reason": analysis.watering_reason,
            "instructions": analysis.watering_instructions,
        },
        "agent_explanation": agent_explanation,
        "sources": sources,
    }
    return report_data

def generate_chat_reply(
    messages: List[Dict[str, str]],
    plant_context: Optional[str] = None,
    knowledge_context: Optional[str] = None
) -> str:
    """
    Generates a knowledgeable plant care response using Groq LLM when configured,
    or a rich botanical expert response system based on retrieved knowledge when offline.
    """
    user_query = messages[-1]["content"] if messages else ""
    
    # 1. Try Groq API if key is present
    if settings.groq_api_key:
        system_prompt = (
            "You are FloraBOT AI, an expert horticulturalist and indoor plant diagnostic assistant. "
            "Give practical, scientifically grounded, empathetic advice in clear English (typically 2 to 5 sentences). "
            "Never invent sensor readings or diagnoses. "
            "When wilting is mentioned, remind the user that both underwatering and overwatering cause droop. "
        )
        if plant_context:
            system_prompt += f"\nMonitored Plant Context:\n{plant_context}"
        if knowledge_context:
            system_prompt += f"\nRetrieved Knowledge Context:\n{knowledge_context}"

        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "system", "content": system_prompt}] + messages[-12:],
            "temperature": 0.35,
            "max_tokens": 550
        }
        try:
            with httpx.Client(timeout=30) as client:
                res = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json=payload
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
        except Exception:
            # Fall back to structured botanical intelligence
            pass

    # 2. Local Grounded Botanical Response Engine
    # Uses genuine retrieved knowledge and plant state
    lower_q = user_query.lower()
    
    context_prefix = ""
    if plant_context:
        context_prefix = f"Regarding {plant_context.split('.')[0]}: "

    if any(k in lower_q for k in ["wilt", "droop", "drooping", "limp"]):
        reply = (
            f"{context_prefix}Leaf drooping can be caused by either dry soil (underwatering) or suffocated roots (overwatering). "
            "Before adding any water, test the soil moisture 2 inches below the surface. "
            "If the soil is bone dry, provide a gentle thorough watering. If it is wet or soggy, withhold water and improve container drainage."
        )
    elif any(k in lower_q for k in ["water", "how much water", "when to water", "watering"]):
        reply = (
            f"{context_prefix}Water only when the top 2–3 inches of potting mix feel dry to the touch. "
            "Most indoor plants thrive when watered deeply until liquid trickles from the drainage holes, "
            "then allowing the root zone to aerate. Avoid leaving the pot in standing runoff water."
        )
    elif any(k in lower_q for k in ["yellow", "yellowing", "chlorosis"]):
        reply = (
            f"{context_prefix}Yellowing foliage (chlorosis) is commonly triggered by moisture imbalance (especially overwatering), "
            "poor drainage, or nitrogen/iron deficiency. Check that the pot has functioning drainage holes and inspect leaf undersides for fine webbing or mites."
        )
    elif any(k in lower_q for k in ["disease", "spots", "fungus", "blight", "rot", "mildew"]):
        reply = (
            f"{context_prefix}When fungal or bacterial leaf spots appear, isolate the plant to prevent airborne spore spread. "
            "Gently prune off severely blemished leaves with sterilized scissors, avoid wetting foliage during watering, "
            "and ensure adequate air circulation around the canopy."
        )
    elif any(k in lower_q for k in ["light", "sun", "sunlight", "window"]):
        reply = (
            f"{context_prefix}Most indoor plants prefer medium to bright indirect sunlight (such as near an east-facing or shaded south/west window). "
            "Harsh direct midday sun can scorch leaf tissue, while low light can slow growth and reduce water uptake."
        )
    elif any(k in lower_q for k in ["report", "scan", "diagnosis", "latest", "status"]):
        if plant_context:
            reply = f"Based on your plant's latest records: {plant_context} You can view or download the full diagnostic report in the Reports section."
        else:
            reply = "You don't have an active scan selected right now. Once your ESP32-CAM transmits an image or you run a diagnosis, I will analyze the full health details for you here."
    else:
        if knowledge_context:
            reply = f"{context_prefix}From our botanical reference library: {knowledge_context[:280]}... Feel free to ask about specific care, watering volumes, or disease management!"
        else:
            reply = (
                f"{context_prefix}I am your FloraBOT Plant AI Assistant. I can assist with diagnosing visible symptoms, "
                "calculating appropriate watering amounts, explaining disease treatment protocols, and interpreting your ESP32-CAM monitoring records. "
                "What would you like to check today?"
            )

    return reply
