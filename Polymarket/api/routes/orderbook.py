"""Orderbook and price endpoints."""

import logging

from fastapi import APIRouter, Depends, Body, HTTPException

logger = logging.getLogger("agentcrab")

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse, Orderbook
from api.services import clob as clob_svc

router = APIRouter(tags=["orderbook"])

MAX_LEVELS = 10  # Top N bid/ask levels to return


def _simplify_orderbook(book: Orderbook) -> dict:
    """Trim orderbook to top N levels and add counts."""
    return {
        "token_id": book.token_id,
        "best_bid": book.best_bid,
        "best_ask": book.best_ask,
        "spread": book.spread,
        "bids": [{"price": b.price, "size": b.size} for b in book.bids[:MAX_LEVELS]],
        "asks": [{"price": a.price, "size": a.size} for a in book.asks[:MAX_LEVELS]],
        "total_bids": len(book.bids),
        "total_asks": len(book.asks),
    }


@router.get("/orderbook/{token_id}")
async def get_orderbook(
    token_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get the full orderbook for a specific token."""
    try:
        book = await clob_svc.get_orderbook(token_id)
    except Exception as e:
        logger.exception("Failed to fetch orderbook for token %s", token_id)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch orderbook from Polymarket. Please retry.",
            ).model_dump(),
        )

    bid_count = len(book.bids)
    ask_count = len(book.asks)
    spread_str = f", spread {book.spread}" if book.spread else ""
    summary = (
        f"Orderbook for {token_id[:12]}...: "
        f"{bid_count} bids, {ask_count} asks. "
        f"Best bid: {book.best_bid or 'N/A'}, best ask: {book.best_ask or 'N/A'}"
        f"{spread_str}."
    )

    return SuccessResponse(summary=summary, data=_simplify_orderbook(book))


@router.post("/orderbook/batch")
async def get_orderbooks_batch(
    token_ids: list[str] = Body(..., description="List of token IDs"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Batch fetch orderbooks for multiple tokens. Counts as 1 API call."""
    if len(token_ids) > 20:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="TOO_MANY_TOKENS",
                message="Maximum 20 tokens per batch request.",
            ).model_dump(),
        )

    try:
        books = await clob_svc.get_orderbooks_batch(token_ids)
    except Exception as e:
        logger.exception("Failed to fetch batch orderbooks (%d tokens)", len(token_ids))
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch orderbooks from Polymarket. Please retry.",
            ).model_dump(),
        )

    summary = f"Fetched orderbooks for {len(books)} token{'s' if len(books) != 1 else ''}."
    return SuccessResponse(
        summary=summary,
        data=[_simplify_orderbook(b) for b in books],
    )


@router.get("/prices/{token_id}")
async def get_price(
    token_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get price summary for a specific token."""
    try:
        price = await clob_svc.get_price(token_id)
    except Exception as e:
        logger.exception("Failed to fetch price for token %s", token_id)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch price from Polymarket. Please retry.",
            ).model_dump(),
        )

    if not price.midpoint and not price.best_bid and not price.best_ask and not price.last_trade_price:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="NOT_FOUND",
                message=f"No price data found for token_id '{token_id[:20]}...'. Check that the token_id is valid and the market is active.",
            ).model_dump(),
        )

    mid = price.midpoint or "N/A"
    summary = (
        f"Price for {token_id[:12]}...: "
        f"bid {price.best_bid or 'N/A'}, ask {price.best_ask or 'N/A'}, "
        f"mid {mid}."
    )

    return SuccessResponse(summary=summary, data={
        "token_id": price.token_id,
        "best_bid": price.best_bid,
        "best_ask": price.best_ask,
        "midpoint": price.midpoint,
        "spread": price.spread,
        "last_trade_price": price.last_trade_price,
    })


@router.post("/prices/batch")
async def get_prices_batch(
    token_ids: list[str] = Body(..., description="List of token IDs"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Batch fetch prices for multiple tokens. Counts as 1 API call."""
    if len(token_ids) > 20:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="TOO_MANY_TOKENS",
                message="Maximum 20 tokens per batch request.",
            ).model_dump(),
        )

    try:
        prices = await clob_svc.get_prices_batch(token_ids)
    except Exception as e:
        logger.exception("Failed to fetch batch prices (%d tokens)", len(token_ids))
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch prices from Polymarket. Please retry.",
            ).model_dump(),
        )

    summary = f"Fetched prices for {len(prices)} token{'s' if len(prices) != 1 else ''}."
    return SuccessResponse(
        summary=summary,
        data=[{
            "token_id": p.token_id,
            "best_bid": p.best_bid,
            "best_ask": p.best_ask,
            "midpoint": p.midpoint,
            "spread": p.spread,
            "last_trade_price": p.last_trade_price,
        } for p in prices],
    )
