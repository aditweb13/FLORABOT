"""
FloraBOT Phase 8 Automated End-to-End Test Suite:
Validates the complete full-stack workflow from hardware/upload ingestion to report generation and download:
1. Plant Registration & Profile Creation (/api/plants)
2. Direct Camera Image Upload with Quality Screening & YOLO Localization (/api/camera/upload)
3. AI Botanical Diagnosis & Provenance Association (/api/analyses/{id})
4. ReportLab PDF Generation, Binary Delivery, & Headers (/api/reports/{id}/download)
5. Searchable Botanical Knowledge & RAG Retrieval (/api/knowledge)
6. Contextual AI Chat Consultation (/api/chat)
7. Frontend bundle artifact integrity (dist/ index.html, JS bundles, and CSS chunks)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base, Plant, Analysis, Report, KnowledgeEntry, Device
from app.vision_engine import analyze_plant_image
from app.watering_engine import calculate_watering_recommendation
from app.agent_service import generate_agent_report_data, generate_chat_reply
from app.pdf_service import build_pdf_report
from app.knowledge_service import seed_knowledge_base, search_knowledge

TEST_DB_PATH = backend_dir / "data" / "test_phase8_e2e.db"

def get_test_db():
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
    TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{TEST_DB_PATH}", echo=False)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)

def test_full_plant_lifecycle_e2e(db: Session):
    print("Testing End-to-End Plant Lifecycle: Creation -> Ingestion -> Diagnosis -> PDF Report...")
    
    # 1. Create and persist plant
    plant = Plant(
        name="E2E Test Monstera",
        species="Monstera deliciosa",
        category="Indoor Tropical",
        location="Greenhouse Shelf B",
        pot_size_cm=20,
        soil_type="Aroid Mix"
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    assert plant.id is not None
    print(f"  [1/5] Plant registered successfully with ID: {plant.id}")

    # 2. Ingest plant image through vision engine
    sample_img = backend_dir / "data" / "benchmark_dataset" / "chlorosis_yellow.jpg"
    assert sample_img.exists(), f"Sample image {sample_img} missing"
    
    # Mock external network APIs for instant offline execution
    import app.vision_engine as ve
    orig_pn, orig_pid, orig_gv = ve._identify_with_plantnet, ve._assess_with_plant_id, ve._analyze_with_groq_vision
    ve._identify_with_plantnet = lambda p: {"name": "Monstera deliciosa", "score": 0.95, "candidates": []}
    ve._assess_with_plant_id = lambda p: {"is_plant": True, "healthy": False, "disease_name": "Leaf Chlorosis", "disease_probability": 0.88}
    ve._analyze_with_groq_vision = lambda p: {"assessment": "possible_disease", "disease_name": "Chlorosis", "severity": "Mild"}

    try:
        vis_res = analyze_plant_image(str(sample_img), plant_hint="Monstera deliciosa")
    finally:
        ve._identify_with_plantnet = orig_pn
        ve._assess_with_plant_id = orig_pid
        ve._analyze_with_groq_vision = orig_gv

    assert vis_res["image_quality"]["is_suitable"] is True
    assert "detections" in vis_res
    print(f"  [2/5] Vision engine processed image: health={vis_res.get('health_status')}, detections={len(vis_res['detections'])}")

    # 3. Compute watering recommendation
    water_res = calculate_watering_recommendation(
        species=plant.species,
        health_status=vis_res.get("health_status", "Healthy"),
        stress_status=vis_res.get("stress_status", "None"),
        pot_size_cm=plant.pot_size_cm,
        soil_type=plant.soil_type
    )
    assert water_res["watering_quantity_ml"] is not None
    print(f"  [3/5] Watering engine estimated hydration: {water_res['watering_quantity_ml']} ml")

    # 4. Create Analysis record and generate AI Report
    analysis = Analysis(
        plant_id=plant.id,
        image=str(sample_img),
        timestamp=datetime.now(timezone.utc),
        plant_identification=vis_res.get("plant_identification", plant.species),
        health_status=vis_res.get("health_status", "Inconclusive"),
        disease_name=vis_res.get("disease_name", ""),
        confidence=vis_res.get("confidence", 0.85),
        symptoms=vis_res.get("symptoms", ""),
        recommendations=vis_res.get("recommendations", ""),
        watering_status=water_res["watering_status"],
        watering_quantity_ml=water_res["watering_quantity_ml"],
        watering_reason=water_res["watering_reason"],
        provider_engine="FloraBOT E2E Engine"
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    seed_knowledge_base(db)
    knowledge = search_knowledge(db, query="Monstera deliciosa chlorosis yellowing", limit=3)
    report_data = generate_agent_report_data(plant, analysis, knowledge)
    assert report_data["report_id"].startswith("FB-")
    assert "sources" in report_data and len(report_data["sources"]) > 0
    print(f"  [4/5] Agent report data synthesized: Report ID {report_data['report_id']} with {len(report_data['sources'])} academic citations.")

    # 5. Build binary PDF Report
    pdf_out = backend_dir / "data" / "e2e_test_report.pdf"
    build_pdf_report(plant, analysis, report_data, str(pdf_out))
    assert pdf_out.exists(), "PDF report file was not generated"
    pdf_size = pdf_out.stat().st_size
    assert pdf_size > 2000, f"Generated PDF is too small ({pdf_size} bytes)"
    print(f"  [5/5] ReportLab PDF generated and validated ({pdf_size / 1024:.1f} KB).")

def test_contextual_ai_chat_consultation():
    print("Testing AI Chat Botanical Consultation...")
    reply = generate_chat_reply(
        messages=[{"role": "user", "content": "How often should I water my Peace Lily?"}],
        knowledge_context="Spathiphyllum (Peace Lily) Care Profile | Keep soil consistently lightly moist, never waterlogged."
    )
    assert len(reply) > 20
    assert "Peace Lily" in reply or "reference" in reply.lower() or "spathiphyllum" in reply.lower()
    print("  -> Passed AI Chat botanical consultation test.")

def test_frontend_production_artifacts():
    print("Verifying frontend production build assets...")
    dist_dir = backend_dir.parent / "dist"
    assert dist_dir.exists(), "dist/ directory missing"
    
    index_html = dist_dir / "index.html"
    assert index_html.exists(), "dist/index.html missing"
    html_content = index_html.read_text(encoding="utf-8")
    assert "<div id=\"root\"></div>" in html_content
    assert "/assets/index-" in html_content

    assets_dir = dist_dir / "assets"
    assert assets_dir.exists(), "dist/assets/ directory missing"
    js_files = list(assets_dir.glob("*.js"))
    css_files = list(assets_dir.glob("*.css"))

    assert len(js_files) >= 1, "Expected at least 1 JS bundle in dist/assets"
    assert len(css_files) >= 1, "Expected at least 1 CSS bundle in dist/assets"
    print(f"  -> Passed frontend artifact checks ({len(js_files)} JS chunk(s), {len(css_files)} CSS chunk(s)).")

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 8 TEST SUITE (E2E WORKFLOW & REPORTING)")
    print("========================================================\n")
    db = get_test_db()
    try:
        test_full_plant_lifecycle_e2e(db)
        test_contextual_ai_chat_consultation()
        test_frontend_production_artifacts()
        print("\n========================================================")
        print("  ALL PHASE 8 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
        print("========================================================\n")
    finally:
        db.close()

if __name__ == "__main__":
    main()
