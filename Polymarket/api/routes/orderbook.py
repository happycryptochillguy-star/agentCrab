"""Orderbook and price endpoints."""

from fastapi import APIRouter, Depends, Body, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import clob as clob_svc

router = APIRouter(tags=["orderbook"])


@router.get("/orderbook/{token_id}")
async def get_orderbook(
    token_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get the full orderbook for a specific token."""
    try:
        book = await clob_svc.get_orderbook(token_id)
    except Exception:
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

    return SuccessResponse(summary=summary, data=book.model_dump())


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
    except Exception:
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
        data=[b.model_dump() for b in books],
    )


@router.get("/prices/{token_id}")
async def get_price(
    token_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get price summary for a specific token."""
    try:
        price = await clob_svc.get_price(token_id)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch price from Polymarket. Please retry.",
            ).model_dump(),
        )

    mid = price.midpoint or "N/A"
    summary = (
        f"Price for {token_id[:12]}...: "
        f"bid {price.best_bid or 'N/A'}, ask {price.best_ask or 'N/A'}, "
        f"mid {mid}."
    )

    return SuccessResponse(summary=summary, data=price.model_dump())


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
    except Exception:
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
        data=[p.model_dump() for p in prices],
    )
