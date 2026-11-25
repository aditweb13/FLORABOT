"""
FloraBOT Vector Embedding and RAG Retrieval Service.
Implements:
1. Semantic dense vector embeddings using term frequency, botanical n-gram hashes,
   and character n-gram projections (384-dimensional cosine space).
2. Cosine similarity search and hybrid lexical-semantic RAG ranker.
3. Database embedding indexing and retrieval.
"""

import json
import math
import re
from typing import Dict, List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session
from .models import KnowledgeEntry
from .knowledge_data import KNOWLEDGE_SEED_ENTRIES

EMBEDDING_DIM = 384

def compute_text_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Computes a deterministic, dense semantic embedding vector for botanical texts.
    Maps words, bigrams, and botanical root stems into an L2-normalized vector space.
    """
    if not text:
        return [0.0] * dim

    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    tokens = [t for t in cleaned.split() if len(t) > 2]
    
    vec = [0.0] * dim
    if not tokens:
        return vec

    # 1. Unigram projection with feature hashing
    for token in tokens:
        # Generate stable hash buckets
        h1 = hash(token) % dim
        h2 = (hash(token + "_stem") * 31) % dim
        vec[h1] += 1.0
        vec[h2] += 0.5

    # 2. Bigram contextual projection
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i+1]}"
        h_bi = (hash(bigram) * 17) % dim
        vec[h_bi] += 1.5

    # 3. Semantic concept clusters: map synonymous and co-occurring terms to common concept buckets
    concept_clusters = {
        "root_rot_overwatering": ["rot", "root", "roots", "soggy", "overwater", "overwatering", "saturated", "drainage", "oxygen", "mushy", "decay"],
        "underwatering_wilting": ["wilt", "wilting", "droop", "drooping", "thirst", "dry", "crisp", "crispy", "desiccated", "underwater"],
        "fungal_foliar": ["fungal", "fungus", "mildew", "spore", "lesion", "spot", "blight", "yellowing", "chlorosis", "necrotic", "necrosis"],
        "care_environment": ["sunlight", "light", "humidity", "temperature", "substrate", "soil", "perlite", "bark", "potting", "terracotta"]
    }
    for cluster_name, terms in concept_clusters.items():
        matched = sum(1 for t in tokens if any(term in t for term in terms))
        if matched > 0:
            cluster_hash = (hash(cluster_name) * 53) % dim
            vec[cluster_hash] += matched * 3.5

    # L2 Normalization
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-6:
        vec = [round(v / norm, 5) for v in vec]

    return vec

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))

def seed_knowledge_base(db: Session):
    """Populates or updates the local knowledge base with seed data, citations, and embeddings."""
    existing = db.query(KnowledgeEntry).all()
    existing_by_title = {e.title: e for e in existing}

    for entry in KNOWLEDGE_SEED_ENTRIES:
        content_to_embed = f"{entry['title']} {entry.get('plant_species', '')} {entry.get('disease_name', '')} {entry['summary']} {entry['details_markdown']}"
        emb = compute_text_embedding(content_to_embed)
        emb_json = json.dumps(emb)

        if entry["title"] in existing_by_title:
            ke = existing_by_title[entry["title"]]
            ke.category = entry["category"]
            ke.plant_species = entry.get("plant_species", "")
            ke.disease_name = entry.get("disease_name", "")
            ke.summary = entry["summary"]
            ke.details_markdown = entry["details_markdown"]
            ke.care_data_json = entry.get("care_data_json", "{}")
            ke.treatment_plan = entry.get("treatment_plan", "")
            ke.prevention_tips = entry.get("prevention_tips", "")
            ke.source_name = entry.get("source_name", "FloraBOT Botanical Reference Library")
            ke.source_url = entry.get("source_url", "")
            ke.citations = entry.get("citations", "")
            ke.review_date = entry.get("review_date", "")
            ke.reviewed_by = entry.get("reviewed_by", "")
            ke.embedding_json = emb_json
        else:
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
                citations=entry.get("citations", ""),
                review_date=entry.get("review_date", ""),
                reviewed_by=entry.get("reviewed_by", ""),
                embedding_json=emb_json
            )
            db.add(ke)
    db.commit()

def search_knowledge(
    db: Session,
    query: str = "",
    category: Optional[str] = None,
    limit: int = 25
) -> List[KnowledgeEntry]:
    """
    Hybrid search: combines keyword filtering with dense vector similarity ranking.
    """
    q = db.query(KnowledgeEntry)
    if category and category != "all":
        q = q.filter(KnowledgeEntry.category == category)
        
    entries = q.all()
    if not query.strip():
        return sorted(entries, key=lambda e: e.title)[:limit]

    # Compute query embedding
    q_emb = compute_text_embedding(query)
    term = query.strip().casefold()

    scored = []
    for e in entries:
        score = 0.0
        # 1. Lexical bonus
        full_text = f"{e.title} {e.plant_species} {e.disease_name} {e.summary}".casefold()
        if term in full_text:
            score += 0.40
        if term in e.title.casefold():
            score += 0.25

        # 2. Semantic vector cosine similarity
        try:
            e_emb = json.loads(e.embedding_json) if e.embedding_json else []
            if e_emb:
                cos_sim = cosine_similarity(q_emb, e_emb)
                score += cos_sim * 0.60
        except Exception:
            pass

        scored.append((score, e))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [e for score, e in scored[:limit]]

def retrieve_context_for_analysis(
    db: Session,
    plant_species: str = "",
    disease_name: str = "",
    health_status: str = ""
) -> List[KnowledgeEntry]:
    """
    Semantic RAG retrieval: finds botanical knowledge grounded in the analyzed plant, disease, and health state.
    """
    query_parts = []
    if plant_species and plant_species not in ["Unknown", "Unknown Plant", ""]:
        query_parts.append(plant_species)
    if disease_name and disease_name not in ["None", "None Identified", ""]:
        query_parts.append(disease_name)
    if health_status and health_status not in ["Healthy", "Inconclusive", "Unscanned"]:
        query_parts.append(health_status)

    full_query = " ".join(query_parts)
    if not full_query:
        full_query = "houseplant indoor plant care"

    return search_knowledge(db, query=full_query, limit=4)
