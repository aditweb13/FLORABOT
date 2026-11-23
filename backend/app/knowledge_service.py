from typing import List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from .models import KnowledgeEntry
from .knowledge_data import KNOWLEDGE_SEED_ENTRIES

def seed_knowledge_base(db: Session):
    """Populates the local knowledge base if empty."""
    existing_count = db.query(KnowledgeEntry).count()
    if existing_count == 0:
        for entry in KNOWLEDGE_SEED_ENTRIES:
            ke = KnowledgeEntry(
                title=entry["title"],
                category=entry["category"],
                plant_species=entry.get("plant_species", ""),
                disease_name=entry.get("disease_name", ""),
                summary=entry["summary"],
                details_markdown=entry["details_markdown"],
                care_data_json=entry.get("care_data_json", "{}"),
                treatment_plan=entry.get("treatment_plan", ""),
                prevention_tips=entry.get("prevention_tips", ""),
                source_name=entry.get("source_name", "FloraBOT Botanical Reference Library"),
                source_url=entry.get("source_url", ""),
            )
            db.add(ke)
        db.commit()

def search_knowledge(
    db: Session,
    query: str = "",
    category: Optional[str] = None,
    limit: int = 25
) -> List[KnowledgeEntry]:
    """Searches knowledge entries with optional category filtering and keyword matching."""
    q = db.query(KnowledgeEntry)
    if category and category != "all":
        q = q.filter(KnowledgeEntry.category == category)
        
    if query.strip():
        term = f"%{query.strip()}%"
        q = q.filter(
            or_(
                KnowledgeEntry.title.ilike(term),
                KnowledgeEntry.summary.ilike(term),
                KnowledgeEntry.plant_species.ilike(term),
                KnowledgeEntry.disease_name.ilike(term),
                KnowledgeEntry.details_markdown.ilike(term)
            )
        )
    return q.order_by(KnowledgeEntry.title.asc()).limit(limit).all()

def retrieve_context_for_analysis(
    db: Session,
    plant_species: str = "",
    disease_name: str = "",
    health_status: str = ""
) -> List[KnowledgeEntry]:
    """
    RAG retrieval: finds relevant botanical knowledge matching the analyzed plant and disease.
    """
    results: List[KnowledgeEntry] = []
    seen_ids = set()

    # 1. Match disease if detected
    if disease_name and disease_name not in ["None", "None Identified", ""]:
        first_term = disease_name.split()[0].replace(",", "")
        matches = db.query(KnowledgeEntry).filter(
            or_(
                KnowledgeEntry.disease_name.ilike(f"%{disease_name}%"),
                KnowledgeEntry.disease_name.ilike(f"%{first_term}%"),
                KnowledgeEntry.title.ilike(f"%{first_term}%"),
                KnowledgeEntry.details_markdown.ilike(f"%{first_term}%")
            )
        ).all()
        for m in matches:
            if m.id not in seen_ids:
                results.append(m)
                seen_ids.add(m.id)

    # 2. Match species
    if plant_species and plant_species not in ["Unknown", "Unknown Plant", ""]:
        species_first = plant_species.split()[0]
        matches = db.query(KnowledgeEntry).filter(
            or_(
                KnowledgeEntry.plant_species.ilike(f"%{plant_species}%"),
                KnowledgeEntry.plant_species.ilike(f"%{species_first}%"),
                KnowledgeEntry.title.ilike(f"%{species_first}%")
            )
        ).all()
        for m in matches:
            if m.id not in seen_ids:
                results.append(m)
                seen_ids.add(m.id)

    # 3. Match wilting/stress care guide if applicable
    if "wilting" in health_status.lower() or "stress" in health_status.lower():
        wilting_guide = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.title.ilike("%wilting%")
        ).first()
        if wilting_guide and wilting_guide.id not in seen_ids:
            results.append(wilting_guide)
            seen_ids.add(wilting_guide.id)

    return results
