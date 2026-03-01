"""Positions, trades, and activity endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import data_api
from api.services.payment import derive_safe_address

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def get_positions(
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your Polymarket positions with current prices and P&L."""
    safe_address = derive_safe_address(wallet_address)
    try:
        positions = await data_api.get_positions(safe_address)
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
        summary = "No open positions on Polymarket."
    else:
        # Build rich summary with P&L
        total_pnl = 0.0
        for p in positions:
            if p.pnl:
                try:
                    total_pnl += float(p.pnl)
                except ValueError:
                    pass
        pnl_str = f" Total P&L: ${total_pnl:+.2f}." if total_pnl != 0 else ""
        summary = f"{total} open position{'s' if total != 1 else ''} on Polymarket.{pnl_str}"

    return SuccessResponse(
        summary=summary,
        data=[p.model_dump() for p in positions],
    )


@router.get("/trades")
async def get_trades(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your trade history on Polymarket."""
    safe_address = derive_safe_address(wallet_address)
    try:
        trades = await data_api.get_trades(safe_address, limit=limit, offset=offset)
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
        summary = "No trade history found."
    else:
        summary = f"{total} trade{'s' if total != 1 else ''} found."

    return SuccessResponse(
        summary=summary,
        data=[t.model_dump() for t in trades],
    )


@router.get("/activity")
async def get_activity(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get your on-chain activity on Polymarket (trades, splits, merges, redemptions)."""
    safe_address = derive_safe_address(wallet_address)
    try:
        activities = await data_api.get_activity(safe_address, limit=limit, offset=offset)
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
        summary = "No on-chain activity found."
    else:
        summary = f"{total} activity record{'s' if total != 1 else ''} found."

    return SuccessResponse(
        summary=summary,
        data=[a.model_dump() for a in activities],
    )
