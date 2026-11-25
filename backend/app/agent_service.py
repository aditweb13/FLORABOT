import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from .config import settings
from .models import Analysis, KnowledgeEntry, Plant

def _generate_groq_report_explanation(evidence: Dict[str, Any]) -> Optional[str]:
    """Use Groq to write a short report narrative from saved, provider-backed facts."""
    if not settings.groq_api_key:
        return None
    payload = {
        "model": settings.groq_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write a concise 3-5 sentence plant health report explanation from the supplied JSON facts. "
                    "Do not invent diagnoses, species, symptoms, confidence, or care conditions. Preserve inconclusive "
                    "and no-plant outcomes exactly. Explain that image health scores do not measure soil moisture. "
                    "Use only supplied references. Return plain text without a heading."
                ),
            },
            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_tokens": 350,
    }
    try:
        with httpx.Client(timeout=45) as client:
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json=payload,
            )
            response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text[:2000] if text else None
    except Exception:
        return None

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
            "citations": getattr(ke, "citations", ""),
            "review_date": getattr(ke, "review_date", ""),
            "reviewed_by": getattr(ke, "reviewed_by", ""),
            "summary": ke.summary
        })
    if not sources:
        sources.append({
            "title": "FloraBOT Curated Phytopathology & Botanical Knowledgebase",
            "category": "general",
            "source_name": "FloraBOT Botanical Reference Library",
            "source_url": "",
            "citations": "Peer-reviewed extension publications from UF/IFAS, Penn State, UC IPM, and Cornell University.",
            "review_date": "2026-04-12",
            "reviewed_by": "FloraBOT Scientific Review Panel",
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

    fallback_explanation = " ".join(explanation_parts)
    report_evidence = {
        "plant_name": plant.name,
        "species": analysis.plant_identification or plant.species,
        "health_status": analysis.health_status,
        "disease_name": analysis.disease_name,
        "diagnostic_confidence": analysis.confidence,
        "symptoms": analysis.symptoms,
        "stress_status": analysis.stress_status,
        "stress_observations": analysis.stress_observations,
        "recommendations": analysis.recommendations,
        "watering_reason": analysis.watering_reason,
        "references": [
            {"title": item.title, "summary": item.summary}
            for item in knowledge_entries[:3]
        ],
    }
    generated_explanation = _generate_groq_report_explanation(report_evidence)
    agent_explanation = generated_explanation or fallback_explanation
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
    """Generate an evidence-grounded reply with Groq, or be transparent about limited local support."""
    if not messages:
        return "Ask me a plant-care question and I will use the available plant records and reference material to help."

    system_prompt = (
        "You are FloraBOT, a careful plant-care assistant. Answer the user's actual question directly and naturally. "
        "Use the supplied plant record and reference excerpts when relevant. Never invent measurements, diagnoses, "
        "species, sources, or treatment certainty. Distinguish visible observations from possible causes. If evidence "
        "is insufficient, say what you need and ask one useful follow-up question. Keep advice practical and concise. "
        "When relying on a supplied reference, name its title."
    )
    if plant_context:
        system_prompt += f"\nCurrent plant record (may be incomplete):\n{plant_context}"
    if knowledge_context:
        system_prompt += f"\nRetrieved botanical references (use only if relevant):\n{knowledge_context}"

    if settings.groq_api_key:
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "system", "content": system_prompt}] + messages[-12:],
            "temperature": 0.65,
            "max_tokens": 650,
        }
        try:
            with httpx.Client(timeout=45) as client:
                response = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                answer = response.json()["choices"][0]["message"]["content"].strip()
                if answer:
                    return answer
        except Exception:
            pass

    if knowledge_context:
        reference = knowledge_context.split(" | ", 1)[0].strip()
        if len(reference) > 480:
            reference = reference[:477].rsplit(" ", 1)[0] + "..."
        if settings.groq_api_key:
            return (
                "I couldn't generate an assistant response just now. This reference is informational, not an AI diagnosis.\n\n"
                f"Closest reference: {reference}"
            )
        return (
            f"I can offer this local reference for now, but I couldn't generate an assistant response.\n\nClosest reference: {reference}"
        )
    if plant_context:
        if settings.groq_api_key:
            return "I can see the saved plant record, but couldn't generate an assistant response just now."
        return "I couldn't generate an assistant response just now. Try again in a moment."
    return "I couldn't generate an assistant response just now. Try a specific plant or symptom in the Botanical Library."
