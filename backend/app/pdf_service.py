import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, KeepTogether, HRFlowable
)
from .models import Analysis, Plant

def build_pdf_report(
    plant: Plant,
    analysis: Analysis,
    report_data: Dict[str, Any],
    output_pdf_path: str
):
    """
    Generates a professional botanical AI health report PDF
    containing comprehensive diagnosis, watering instructions, care plan, and sources.
    """
    Path(output_pdf_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Custom color palette matching FloraBOT brand
    c_primary = colors.HexColor("#1b4332")
    c_secondary = colors.HexColor("#2d6a4f")
    c_accent = colors.HexColor("#52b788")
    c_bg_light = colors.HexColor("#f4f7f4")
    c_border = colors.HexColor("#d8e2dc")
    c_text_dark = colors.HexColor("#1f2937")
    c_text_muted = colors.HexColor("#4b5563")

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        name="FloraTitle",
        parent=styles["Title"],
        textColor=c_primary,
        fontSize=22,
        leading=26,
        fontName="Helvetica-Bold",
        alignment=0,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        name="FloraSubtitle",
        parent=styles["Normal"],
        textColor=c_secondary,
        fontSize=11,
        leading=15,
        fontName="Helvetica",
        spaceAfter=12
    )
    h2_style = ParagraphStyle(
        name="FloraH2",
        parent=styles["Heading2"],
        textColor=c_secondary,
        fontSize=13,
        leading=17,
        fontName="Helvetica-Bold",
        spaceBefore=14,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        name="FloraBody",
        parent=styles["BodyText"],
        textColor=c_text_dark,
        fontSize=9.5,
        leading=14,
        fontName="Helvetica"
    )
    meta_style = ParagraphStyle(
        name="FloraMeta",
        parent=styles["Normal"],
        textColor=c_text_muted,
        fontSize=8.5,
        leading=12,
        fontName="Helvetica"
    )

    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=40,
        bottomMargin=40
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("FloraBOT AI — Intelligent Plant Health Report", title_style))
    report_id = report_data.get("report_id", f"FB-{analysis.id}")
    gen_time = report_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M UTC"))
    story.append(Paragraph(f"Report ID: <b>{report_id}</b> · Generated on {gen_time} · Automated Vision Analysis", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_accent, spaceBefore=0, spaceAfter=12))

    # 2. Plant & Device Overview Table
    story.append(Paragraph("A. Plant & Device Information", h2_style))
    overview_data = [
        ["Plant Name:", plant.name, "Species:", analysis.plant_identification or plant.species],
        ["Category:", plant.category or "Houseplant", "Location:", plant.location or "Indoor Monitor"],
        ["Container Size:", f"{plant.pot_size_cm} cm diameter", "Soil Type:", plant.soil_type or "Potting Mix"],
        ["Diagnostics Engine:", analysis.provider_engine or "FloraBOT Vision", "Device ID:", str(analysis.device_id or "Direct")],
    ]
    t_overview = Table(overview_data, colWidths=[1.3*inch, 2.3*inch, 1.3*inch, 2.3*inch])
    t_overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), c_bg_light),
        ("BACKGROUND", (2, 0), (2, -1), c_bg_light),
        ("TEXTCOLOR", (0, 0), (-1, -1), c_text_dark),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_overview)
    story.append(Spacer(1, 10))

    # 3. Leaf Photo & Health Classification side-by-side
    story.append(Paragraph("B. Monitored Leaf Observation & Health Status", h2_style))
    
    img_element = None
    if os.path.exists(analysis.image):
        try:
            img_element = RLImage(analysis.image, width=2.6*inch, height=1.9*inch, kind="proportional")
        except Exception:
            img_element = Paragraph("[Analyzed Leaf Image]", meta_style)

    health_summary = (
        f"<b>Health Status:</b> {analysis.health_status}<br/>"
        f"<b>Disease Detected:</b> {analysis.disease_detected.upper()}<br/>"
        f"<b>Identified Condition:</b> {analysis.disease_name or 'None Identified'}<br/>"
        f"<b>AI Confidence:</b> {f'{int(analysis.confidence*100)}%' if analysis.confidence else 'Uncalibrated'}<br/>"
        f"<b>Observed Symptoms:</b> {analysis.symptoms or 'Uniform green pigmentation'}<br/>"
        f"<b>Stress Assessment:</b> {analysis.stress_status} — {analysis.stress_observations or 'Normal turgor'}"
    )

    t_health = Table([[img_element or "", Paragraph(health_summary, body_style)]], colWidths=[2.8*inch, 4.4*inch])
    t_health.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (1, 0), (1, 0), c_bg_light),
        ("BOX", (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_health)
    story.append(Spacer(1, 10))

    # 4. Watering Recommendation Section
    story.append(Paragraph("C. Intelligent Watering Recommendation", h2_style))
    qty_text = f"<b>{analysis.watering_quantity_ml} ml</b>" if analysis.watering_quantity_ml else "Quantity not specified (manual moisture check required)"
    water_data = [
        ["Watering Status:", analysis.watering_status],
        ["Target Quantity:", qty_text],
        ["Botanical Reason:", analysis.watering_reason or "Calculated based on leaf condition and pot dimensions."],
        ["Instructions:", analysis.watering_instructions or "Check soil 2 inches deep before applying moisture."],
    ]
    t_water = Table([[Paragraph(k, styles["Normal"]), Paragraph(v, body_style)] for k, v in water_data], colWidths=[1.8*inch, 5.4*inch])
    t_water.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), c_bg_light),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(t_water)
    story.append(Spacer(1, 10))

    # 5. Treatment, Prevention & Recovery Plan
    story.append(Paragraph("D. Care Recommendations & Treatment Plan", h2_style))
    care_data = [
        ["Treatment & Action:", analysis.recommendations or "Continue regular maintenance."],
        ["Prevention Protocol:", analysis.prevention or "Ensure proper airflow, clean tools, and appropriate lighting."],
        ["Recovery Timeline:", analysis.recovery_plan or "Observe plant over 5–7 days for new shoots or condition changes."],
    ]
    t_care = Table([[Paragraph(k, styles["Normal"]), Paragraph(v, body_style)] for k, v in care_data], colWidths=[1.8*inch, 5.4*inch])
    t_care.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), c_bg_light),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(t_care)
    story.append(Spacer(1, 10))

    # 6. AI Agent Explanation & Botanical References
    story.append(Paragraph("E. AI Agent Synthesis & Knowledge Sources", h2_style))
    agent_text = report_data.get("agent_explanation", "Analysis completed successfully.")
    story.append(Paragraph(f"<b>Agent Synthesis:</b> {agent_text}", body_style))
    story.append(Spacer(1, 6))

    sources = report_data.get("sources", [])
    if sources:
        items = []
        for s in sources[:4]:
            url = f"({s.get('source_url')})" if s.get('source_url') else ""
            items.append(f"• <b>{s.get('title')}</b> — {s.get('source_name')} {url}")
        sources_text = "<br/>".join(items)
        story.append(Paragraph(f"<b>Retrieved References:</b><br/>{sources_text}", meta_style))

    # Footer note
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_border, spaceBefore=4, spaceAfter=6))
    story.append(Paragraph(
        "<i>Disclaimer: FloraBOT AI provides diagnostic guidance based on computer vision observation and botanical knowledge bases. "
        "Confidence metrics reflect image feature classification rather than definitive laboratory pathology. Always confirm with physical soil checks.</i>",
        meta_style
    ))

    doc.build(story)
