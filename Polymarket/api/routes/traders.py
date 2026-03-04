"""Leaderboard and other-user query endpoints."""

import logging

from fastapi import APIRouter, Depends, Query, HTTPException

logger = logging.getLogger("agentcrab")

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import leaderboard as lb_svc
from api.services.payment import is_valid_address

router = APIRouter(prefix="/traders", tags=["traders"])


def _simplify_leaderboard_entry(e) -> dict:
    d: dict = {"rank": e.rank}
    d["name"] = e.display_name or e.address[:10] + "..."
    if e.volume:
        d["volume"] = e.volume
    if e.pnl:
        d["pnl"] = e.pnl
    if e.positions_count:
        d["positions"] = e.positions_count
    d["address"] = e.address
    return d


def _simplify_position(p) -> dict:
    d: dict = {
        "question": p.question,
        "outcome": p.outcome,
        "size": p.size,
    }
    if p.avg_price:
        d["avg_price"] = p.avg_price
    if p.current_price:
        d["current_price"] = p.current_price
    if p.pnl:
        d["pnl"] = p.pnl
    d["token_id"] = p.token_id
    return d


def _simplify_trade(t) -> dict:
    d: dict = {
        "side": t.side,
        "outcome": t.outcome,
        "size": t.size,
        "price": t.price,
    }
    if t.timestamp:
        d["timestamp"] = t.timestamp
    return d


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get top traders leaderboard."""
    try:
        entries = await lb_svc.get_leaderboard(limit=limit, offset=offset)
    except Exception as e:
        logger.exception("Failed to fetch leaderboard")
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
        data=[_simplify_leaderboard_entry(e) for e in entries],
    )


@router.get("/{address}/positions")
async def get_trader_positions(
    address: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get positions for any trader by wallet address."""
    if not is_valid_address(address):
        raise HTTPException(status_code=400, detail=ErrorResponse(
            error_code="INVALID_ADDRESS", message="Invalid Ethereum address format.",
        ).model_dump())
    try:
        positions = await lb_svc.get_trader_positions(address)
    except Exception as e:
        logger.exception("Failed to fetch positions for trader %s", address)
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
        data=[_simplify_position(p) for p in positions],
    )


@router.get("/{address}/trades")
async def get_trader_trades(
    address: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get trade history for any trader."""
    if not is_valid_address(address):
        raise HTTPException(status_code=400, detail=ErrorResponse(
            error_code="INVALID_ADDRESS", message="Invalid Ethereum address format.",
        ).model_dump())
    try:
        trades = await lb_svc.get_trader_trades(address, limit=limit, offset=offset)
    except Exception as e:
        logger.exception("Failed to fetch trades for trader %s", address)
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
        data=[_simplify_trade(t) for t in trades],
    )
