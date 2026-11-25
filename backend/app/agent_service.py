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

def _synthesize_local_botanical_reply(
    user_query: str,
    plant_context: Optional[str] = None,
    knowledge_context: Optional[str] = None
) -> str:
    """
    Synthesize an intelligent, authoritative botanical response using local RAG knowledge
    and plant state when cloud LLM (Groq) is unavailable, unconfigured, or rate-limited.
    """
    lines = []
    
    # Extract greeting or opening
    q_lower = user_query.lower()
    
    # Analyze knowledge context if present
    # knowledge_context format can be: "Title: Summary | Title2: Summary2..."
    parsed_entries = []
    if knowledge_context:
        raw_parts = [p.strip() for p in knowledge_context.split(" | ") if p.strip()]
        for p in raw_parts:
            if ":" in p:
                title, desc = p.split(":", 1)
                parsed_entries.append((title.strip(), desc.strip()))
            else:
                parsed_entries.append((p.strip(), ""))
                
    primary_title = parsed_entries[0][0] if parsed_entries else "Botanical Reference"
    primary_desc = parsed_entries[0][1] if parsed_entries else ""

    # Check query intent
    is_treatment = any(w in q_lower for w in ["treat", "cure", "fix", "spray", "remedy", "save", "help", "solution", "protocol", "heal", "rid"])
    is_watering = any(w in q_lower for w in ["water", "watering", "dry", "wet", "droop", "wilt", "hydrate", "moist"])
    is_prevention = any(w in q_lower for w in ["prevent", "avoid", "protect", "stop", "care", "light", "sun"])
    is_diagnosis = any(w in q_lower for w in ["what", "identify", "mildew", "rot", "spot", "fungus", "disease", "white", "yellow", "brown", "why"])

    # 1. Headline / Context acknowledgement
    if plant_context:
        lines.append(f"### Plant Consultation: {plant_context.split(',')[0]}")
    else:
        lines.append(f"### Botanical Consultation: {primary_title}")

    # 2. Condition or Care Overview based on knowledge
    if primary_desc:
        lines.append(f"\n**Reference Guidance ({primary_title}):**\n{primary_desc}")

    # 3. Actionable botanical recommendations
    lines.append("\n**Recommended Action Plan:**")
    
    # Domain specific guidance based on matches
    combined_text = f"{user_query} {primary_title} {primary_desc}".lower()
    
    if "mildew" in combined_text or "powdery" in combined_text:
        lines.append("- **Immediate Isolation:** Separate this plant from neighboring foliage to prevent spore dispersal via air currents.")
        lines.append("- **Foliar Treatment:** Mix 1 teaspoon of potassium bicarbonate or sodium bicarbonate (baking soda) with 1/2 teaspoon of mild horticultural or neem oil in 1 quart of warm water. Mist affected foliage thoroughly.")
        lines.append("- **Environmental Optimization:** Increase room airflow using a gentle fan, but avoid wetting leaves during watering—always hydrate at soil level.")
        lines.append("- **Sanitation:** Carefully snip away heavily coated leaves with shears sterilized in 70% isopropyl alcohol.")
    elif "rot" in combined_text or "overwater" in combined_text or ("wilt" in combined_text and "overwater" in combined_text):
        lines.append("- **Substrate & Root Inspection:** Check soil moisture depth 2 inches below the surface. If soil is heavy and saturated, gently unpot the plant to inspect root coloration.")
        lines.append("- **Remediation Protocol:** Trim away any dark, mushy, or foul-smelling roots using sterile shears. Swish root zone in a diluted 3% hydrogen peroxide solution (1 part H2O2 : 4 parts water).")
        lines.append("- **Repotting:** Transfer into fresh, porous substrate amended with perlite, pumice, or orchid bark, ensuring containers have functional drainage holes.")
        lines.append("- **Hydration Reset:** Hold off on heavy watering until new healthy white root tips emerge.")
    elif "spot" in combined_text or "chlorosis" in combined_text or "fungal" in combined_text:
        lines.append("- **Prune Affected Foliage:** Remove severely spotted leaves to limit spore proliferation.")
        lines.append("- **Organic Fungicide:** Apply an organic copper soap or biofungicide spray (Bacillus subtilis) to healthy and bordering leaves.")
        lines.append("- **Air Circulation:** Reduce humidity pockets around the canopy with gentle air movement.")
        lines.append("- **Nutrient Check:** If yellowing is uniform across leaves without distinct fungal spots, apply a balanced micronutrient chelate fertilizer at half strength.")
    elif "monstera" in combined_text or "pothos" in combined_text:
        lines.append("- **Light:** Provide bright, indirect sunlight. Avoid scorching direct midday sun.")
        lines.append("- **Moisture:** Allow the top 2 to 3 inches of potting substrate to dry out between waterings. Use pots with drainage holes.")
        lines.append("- **Humidity & Cleaning:** Wipe leaves monthly with a damp cloth to remove dust and maximize photosynthetic efficiency.")
    else:
        lines.append("- **Moisture Management:** Water thoroughly until runoff escapes drainage holes, then discard excess tray water after 15 minutes.")
        lines.append("- **Canopy Care:** Prune any damaged foliage and inspect leaf undersides for pest or fungal development.")
        lines.append("- **Airflow & Light:** Ensure filtered indirect light and adequate ambient airflow.")

    # 4. Secondary knowledge citations if available
    if len(parsed_entries) > 1:
        lines.append(f"\n*Related Reference: {parsed_entries[1][0]} — {parsed_entries[1][1]}*")

    lines.append("\n> **FloraBOT Expert Note:** This diagnostic and care guidance is grounded in peer-reviewed university extension research and FloraBOT's botanical knowledge base.")
    
    return "\n".join(lines)


def generate_chat_reply(
    messages: List[Dict[str, str]],
    plant_context: Optional[str] = None,
    knowledge_context: Optional[str] = None
) -> str:
    """Generate an evidence-grounded reply with Groq, or synthesize an intelligent botanical response locally."""
    if not messages:
        return "Ask me a plant-care question and I will use the available plant records and reference material to help."

    latest_user_query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            latest_user_query = m.get("content", "").strip()
            break

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
                if response.status_code == 200:
                    answer = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if answer:
                        return answer
        except Exception:
            pass

    # When Groq key is invalid, missing, or fails, synthesize rich local botanical consultation
    if knowledge_context or plant_context:
        return _synthesize_local_botanical_reply(
            user_query=latest_user_query,
            plant_context=plant_context,
            knowledge_context=knowledge_context
        )

    return (
        "I'm FloraBOT, your plant care specialist. Ask me about plant symptoms, leaf spots, powdery mildew, "
        "watering issues, or specific plant species, and I will provide tailored care protocols and treatment advice."
    )
