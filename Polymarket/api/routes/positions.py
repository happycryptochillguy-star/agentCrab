"""Positions, trades, and activity endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import data_api
from api.services.payment import derive_safe_address

router = APIRouter(prefix="/positions", tags=["positions"])


def _simplify_position(p) -> dict:
    """Strip noise from position, keep trading-relevant fields."""
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
    if p.pnl_percent:
        d["pnl_percent"] = p.pnl_percent
    d["token_id"] = p.token_id
    return d


def _simplify_trade(t) -> dict:
    """Strip noise from trade."""
    d: dict = {
        "side": t.side,
        "outcome": t.outcome,
        "size": t.size,
        "price": t.price,
    }
    if t.timestamp:
        d["timestamp"] = t.timestamp
    return d


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
        data=[_simplify_position(p) for p in positions],
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
        data=[_simplify_trade(t) for t in trades],
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
        data=[{
            "type": a.type,
            "amount": a.amount,
            "timestamp": a.timestamp,
        } for a in activities],
    )
