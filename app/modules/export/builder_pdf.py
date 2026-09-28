"""Server-side PDF board pack — a one/two-page executive snapshot of the
Intelligence Layer, scoped org-wide or to a single portfolio.

Point-in-time report built with reportlab from the same intelligence the
dashboard and the Excel pack use.
"""

from __future__ import annotations

import io
import uuid
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.intelligence.service import IntelligenceService

_NAVY = colors.HexColor("#0E1B36")
_MUTE = colors.HexColor("#5B6B85")
_LINE = colors.HexColor("#D6E0EE")
_RAG = {
    "green": colors.HexColor("#1EA97C"),
    "amber": colors.HexColor("#E8A33D"),
    "red": colors.HexColor("#D64550"),
}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t",
            parent=base["Title"],
            textColor=_NAVY,
            fontName="Helvetica-Bold",
            fontSize=20,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "s",
            parent=base["Normal"],
            textColor=_MUTE,
            fontName="Helvetica-Oblique",
            fontSize=9,
            spaceAfter=10,
        ),
        "h": ParagraphStyle(
            "h",
            parent=base["Heading2"],
            textColor=_NAVY,
            fontName="Helvetica-Bold",
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "c", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11
        ),
    }


def build_board_pack_pdf(service: IntelligenceService, *, portfolio_id: uuid.UUID | None) -> bytes:
    """Return a PDF board pack as bytes."""
    perf = (
        service.portfolio_performance(portfolio_id, as_of=None)
        if portfolio_id
        else service.transformation_performance(as_of=None)
    )
    benefits = (
        service.benefits_variance_portfolio(portfolio_id)
        if portfolio_id
        else service.benefits_variance_transformation()
    )
    kpis = (
        service.kpi_variance_portfolio(portfolio_id)
        if portfolio_id
        else service.kpi_variance_transformation()
    )
    recs = (
        service.portfolio_recommendations(portfolio_id, as_of=None)
        if portfolio_id
        else service.transformation_recommendations(as_of=None)
    )

    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="ETIP Board Pack",
    )
    story: list[Flowable] = [
        Paragraph("ETIP — Executive Board Pack", st["title"]),
        Paragraph(
            f"Scope: {perf.scope_label} &nbsp;·&nbsp; As of: {date.today().isoformat()} "
            f"&nbsp;·&nbsp; CONFIDENTIAL — DO NOT DISTRIBUTE",
            st["sub"],
        ),
    ]

    rag = perf.health.rag
    summary = [
        ["Overall health", rag.replace("_", " ").title()],
        ["Schedule (SPI)", str(perf.evm.spi)],
        ["Cost (CPI)", str(perf.evm.cpi)],
        ["Budget at completion", perf.evm.bac],
        ["Estimate at completion", perf.evm.eac],
        ["Projects", str(perf.project_count)],
        ["Benefits target / realized", f"{benefits.total_target} / {benefits.total_realized}"],
        ["Benefits realization %", str(benefits.realization_percent)],
        ["KPIs on target", f"{kpis.kpis_on_target} / {kpis.kpi_count}"],
    ]
    t = Table(summary, colWidths=[70 * mm, 108 * mm])
    tstyle = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _NAVY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if rag in _RAG:
        tstyle += [
            ("BACKGROUND", (1, 0), (1, 0), _RAG[rag]),
            ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
        ]
    t.setStyle(TableStyle(tstyle))
    story += [Paragraph("Summary", st["h"]), t]

    # Projects
    story += [Paragraph("Projects — earned-value health", st["h"])]
    prows = [["Code", "Health", "SPI", "CPI"]] + [
        [b.code, b.rag.replace("_", " "), str(b.spi), str(b.cpi)] for b in perf.breakdown
    ]
    pt = Table(prows, colWidths=[60 * mm, 46 * mm, 36 * mm, 36 * mm], repeatRows=1)
    pstyle = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, b in enumerate(perf.breakdown, start=1):
        if b.rag in _RAG:
            pstyle += [
                ("BACKGROUND", (1, i), (1, i), _RAG[b.rag]),
                ("TEXTCOLOR", (1, i), (1, i), colors.white),
            ]
    pt.setStyle(TableStyle(pstyle))
    story.append(pt)

    # Recommendations
    story += [Paragraph("Recommended actions", st["h"])]
    if recs.recommendations:
        rrows = [["Priority", "Title", "Rationale"]] + [
            [r.priority, Paragraph(r.title, st["cell"]), Paragraph(r.rationale, st["cell"])]
            for r in recs.recommendations[:8]
        ]
        rt = Table(rrows, colWidths=[24 * mm, 60 * mm, 94 * mm], repeatRows=1)
        rt.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                    ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(rt)
    else:
        story.append(Paragraph("Everything on track — no recommendations.", st["cell"]))

    story.append(Spacer(1, 6 * mm))
    doc.build(story)
    return buf.getvalue()
