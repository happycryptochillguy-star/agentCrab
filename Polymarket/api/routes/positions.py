"""Positions, trades, and activity endpoints."""

from fastapi import APIRouter, Depends, Query, Header, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import data_api

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def get_positions(
    x_poly_address: str = Header(..., alias="X-Poly-Address", description="Polymarket (Polygon) wallet address"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your Polymarket positions with current prices and P&L."""
    try:
        positions = await data_api.get_positions(x_poly_address)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch positions from Polymarket. Please retry.",
            ).model_dump(),
        )

    total = len(positions)
    if total == 0:
        summary = f"No open positions found for {x_poly_address[:10]}... on Polymarket."
    else:
        summary = f"Found {total} position{'s' if total != 1 else ''} for {x_poly_address[:10]}... on Polymarket."

    return SuccessResponse(
        summary=summary,
        data=[p.model_dump() for p in positions],
    )


@router.get("/trades")
async def get_trades(
    x_poly_address: str = Header(..., alias="X-Poly-Address"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your trade history on Polymarket."""
    try:
        trades = await data_api.get_trades(x_poly_address, limit=limit, offset=offset)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch trades from Polymarket. Please retry.",
            ).model_dump(),
        )

    total = len(trades)
    if total == 0:
        summary = f"No trades found for {x_poly_address[:10]}... on Polymarket."
    else:
        summary = f"Found {total} trade{'s' if total != 1 else ''} for {x_poly_address[:10]}..."

    return SuccessResponse(
        summary=summary,
        data=[t.model_dump() for t in trades],
    )


@router.get("/activity")
async def get_activity(
    x_poly_address: str = Header(..., alias="X-Poly-Address"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your on-chain activity on Polymarket (trades, splits, merges, redemptions)."""
    try:
        activities = await data_api.get_activity(x_poly_address, limit=limit, offset=offset)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch activity from Polymarket. Please retry.",
            ).model_dump(),
        )

    total = len(activities)
    if total == 0:
        summary = f"No on-chain activity found for {x_poly_address[:10]}... on Polymarket."
    else:
        summary = f"Found {total} activity record{'s' if total != 1 else ''} for {x_poly_address[:10]}..."

    return SuccessResponse(
        summary=summary,
        data=[a.model_dump() for a in activities],
    )
