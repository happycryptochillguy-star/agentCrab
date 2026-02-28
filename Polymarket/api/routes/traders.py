"""Leaderboard and other-user query endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import leaderboard as lb_svc

router = APIRouter(prefix="/traders", tags=["traders"])


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get top traders leaderboard."""
    try:
        entries = await lb_svc.get_leaderboard(limit=limit, offset=offset)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch leaderboard from Polymarket. Please retry.",
            ).model_dump(),
        )

    total = len(entries)
    if total == 0:
        summary = "No leaderboard data available."
    else:
        top = entries[0]
        name = top.display_name or top.address[:10] + "..."
        summary = f"Top {total} traders. #1: {name} with {top.volume or 'N/A'} volume."

    return SuccessResponse(
        summary=summary,
        data=[e.model_dump() for e in entries],
    )


@router.get("/{address}/positions")
async def get_trader_positions(
    address: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get positions for any trader by wallet address."""
    try:
        positions = await lb_svc.get_trader_positions(address)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch trader positions. Please retry.",
            ).model_dump(),
        )

    total = len(positions)
    if total == 0:
        summary = f"No positions found for trader {address[:10]}..."
    else:
        summary = f"Found {total} position{'s' if total != 1 else ''} for trader {address[:10]}..."

    return SuccessResponse(
        summary=summary,
        data=[p.model_dump() for p in positions],
    )


@router.get("/{address}/trades")
async def get_trader_trades(
    address: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get trade history for any trader."""
    try:
        trades = await lb_svc.get_trader_trades(address, limit=limit, offset=offset)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch trader trades. Please retry.",
            ).model_dump(),
        )

    total = len(trades)
    if total == 0:
        summary = f"No trades found for trader {address[:10]}..."
    else:
        summary = f"Found {total} trade{'s' if total != 1 else ''} for trader {address[:10]}..."

    return SuccessResponse(
        summary=summary,
        data=[t.model_dump() for t in trades],
    )
