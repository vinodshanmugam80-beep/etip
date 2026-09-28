"""HTTP route for the board-pack Excel export."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import IntelligenceServiceDep, require_permission
from app.modules.export.builder import build_board_pack
from app.modules.export.builder_pdf import build_board_pack_pdf

router = APIRouter(tags=["Exports"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/exports/board-pack.xlsx",
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Download the executive board pack (Excel)",
)
def board_pack_xlsx(
    service: IntelligenceServiceDep,
    portfolio_id: uuid.UUID | None = Query(default=None),
) -> StreamingResponse:
    """Stream a multi-sheet Excel board pack (org-wide or portfolio-scoped)."""
    content = build_board_pack(service, portfolio_id=portfolio_id)
    suffix = "portfolio" if portfolio_id else "transformation"
    filename = f"etip-board-pack-{suffix}-{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/exports/board-pack.pdf",
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Download the executive board pack (PDF)",
)
def board_pack_pdf(
    service: IntelligenceServiceDep,
    portfolio_id: uuid.UUID | None = Query(default=None),
) -> StreamingResponse:
    """Stream an executive PDF board pack (org-wide or portfolio-scoped)."""
    content = build_board_pack_pdf(service, portfolio_id=portfolio_id)
    suffix = "portfolio" if portfolio_id else "transformation"
    filename = f"etip-board-pack-{suffix}-{date.today().isoformat()}.pdf"
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
