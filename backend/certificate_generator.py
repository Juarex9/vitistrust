# backend/certificate_generator.py
"""
Generador de certificados PDF para viñedos auditados.

El certificado incluye:
- Datos del viñedo (ID, coordenadas, ubicación)
- VitisScore y justificación
- Hashes de Hedera (notarización) y Stellar (on-chain)
- Timestamp de auditoría
- Código QR con evidencia CID
"""

import base64
import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("vitistrust.certificate")

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, SimpleDocTemplate,
        Image as RLImage,
    )
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not available - PDF generation disabled")


def generate_certificate(
    farm_id: str,
    lat: float,
    lon: float,
    region: str,
    vitis_score: int,
    justification: str,
    ndvi: float,
    ndmi: float,
    hedera_txn_id: str,
    stellar_tx_hash: str,
    evidence_cid: str,
    timestamp: str,
    score_breakdown: dict[str, Any] | None = None,
    regional_benchmark: dict[str, Any] | None = None,
) -> bytes:
    """
    Genera certificado PDF de auditoría.
    
    Args:
        farm_id: Identificador del viñedo
        lat, lon: Coordenadas
        region: Región vinícola
        vitis_score: Score (0-100)
        justification: Justificación del score
        ndvi, ndmi: Índices satelitales
        hedera_txn_id: Transaction ID de Hedera
        stellar_tx_hash: Transaction hash de Stellar
        evidence_cid: CID de evidencia en IPFS
        timestamp: ISO timestamp
        score_breakdown: Desglose del score
        regional_benchmark: comparativa regional
        
    Returns:
        PDF en bytes (base64 encoded)
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab not installed")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor("#2D5016"),
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor("#1a1a1a"),
    )
    normal_style = styles["Normal"]
    
    story = []
    
    # === TÍTULO ===
    story.append(Paragraph("🍇 VitisTrust Certificate", title_style))
    story.append(Spacer(1, 20))
    
    # === DATOS DEL VIÑEDO ===
    story.append(Paragraph("Vineyard Data", heading_style))
    
    vineyard_data = [
        ["Farm ID", farm_id],
        ["Region", region or "Unknown"],
        ["Coordinates", f"{lat:.6f}, {lon:.6f}"],
    ]
    t_vineyard = Table(vineyard_data, colWidths=[2*inch, 4*inch])
    t_vineyard.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_vineyard)
    story.append(Spacer(1, 20))
    
    # === VITIS SCORE ===
    score_color = "#22c55e" if vitis_score >= 70 else "#eab308" if vitis_score >= 40 else "#ef4444"
    score_style = ParagraphStyle(
        "Score",
        fontSize=36,
        textColor=colors.HexColor(score_color),
    )
    story.append(Paragraph(f"VitisScore: <b>{vitis_score}</b>/100", score_style))
    story.append(Spacer(1, 10))
    
    # === BREAKDOWN ===
    if score_breakdown:
        story.append(Paragraph("Score Breakdown", heading_style))
        breakdown_data = []
        for component, values in score_breakdown.get("components", {}).items():
            weight = values.get("weight", 0)
            component_score = values.get("component_score", 0)
            contribution = values.get("contribution", 0)
            breakdown_data.append([
                component.replace("_", " ").title(),
                f"{component_score:.1f}%",
                f"×{weight}",
                f"+{contribution:.1f}",
            ])
        
        t_breakdown = Table(
            [["Component", "Score", "Weight", "Contrib"]] + breakdown_data,
            colWidths=[2*inch, 1.5*inch, 1*inch, 1*inch],
        )
        t_breakdown.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2D5016")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_breakdown)
        story.append(Spacer(1, 20))
    
    # === SATELLITE INDICES ===
    story.append(Paragraph("Satellite Indices", heading_style))
    indices_data = [
        ["NDVI", f"{ndvi:.3f}"],
        ["NDMI", f"{ndmi:.3f}"],
    ]
    if regional_benchmark:
        percentile = regional_benchmark.get("percentile")
        if percentile:
            indices_data.append(["Regional Percentile", f"{percentile}th"])
    
    t_indices = Table(indices_data, colWidths=[2*inch, 4*inch])
    t_indices.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_indices)
    story.append(Spacer(1, 20))
    
    # === JUSTIFICATION ===
    story.append(Paragraph("Analysis", heading_style))
    story.append(Paragraph(justification[:500] + "..." if len(justification) > 500 else justification, normal_style))
    story.append(Spacer(1, 20))
    
    # === TRANSACTION PROOF ===
    story.append(Paragraph("Transaction Proofs", heading_style))
    
    proof_data = [
        ["Hedera (Notarization)", hedera_txn_id[:32] + "..." if len(hedera_txn_id) > 32 else hedera_txn_id],
        ["Stellar (On-Chain)", stellar_tx_hash[:32] + "..." if len(stellar_tx_hash) > 32 else stellar_tx_hash],
        ["Evidence (IPFS)", evidence_cid[:32] + "..." if len(evidence_cid) > 32 else evidence_cid],
        ["Timestamp", timestamp],
    ]
    t_proof = Table(proof_data, colWidths=[2*inch, 4*inch])
    t_proof.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_proof)
    story.append(Spacer(1, 30))
    
    # === FOOTER ===
    footer_style = ParagraphStyle(
        "Footer",
        fontSize=9,
        textColor=colors.grey,
    )
    story.append(Paragraph(
        "This certificate was generated by VitisTrust Oracle. "
        "Verify the transaction proofs on Hedera (mainnet/testnet) and Stellar (mainnet/testnet).",
        footer_style,
    ))
    
    # Build PDF
    doc.build(story)
    
    return buffer.getvalue()


def generate_certificate_base64(**kwargs) -> str:
    """Genera certificado y retorna base64."""
    pdf_bytes = generate_certificate(**kwargs)
    return base64.b64encode(pdf_bytes).decode()