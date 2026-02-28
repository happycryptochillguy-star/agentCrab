"""Market search and details endpoints — all categories."""

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services import gamma as gamma_svc

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/tags")
async def get_tags():
    """Get all available Polymarket tags. Free, no auth required."""
    try:
        tags = await gamma_svc.get_tags()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch tags from Polymarket. Please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Found {len(tags)} available tags on Polymarket.",
        data=tags,
    )


@router.get("/search")
async def search_markets(
    query: str | None = Query(None, description="Search by event title"),
    tag: str | None = Query(None, description="Filter by tag slug (e.g. politics, sports, crypto)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    closed: bool = Query(False, description="Include closed events"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Search events across all Polymarket categories."""
    try:
        events = await gamma_svc.search_events(
            query=query, tag=tag, limit=limit, offset=offset, closed=closed
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to search Polymarket events. Please retry.",
            ).model_dump(),
        )

    total = len(events)
    if total == 0:
        summary = "No events found on Polymarket matching your search."
        if query:
            summary = f"No events found for '{query}' on Polymarket."
    else:
        top = max(events, key=lambda e: e.volume or 0)
        top_vol = f"${top.volume:,.0f}" if top.volume else "N/A"
        summary = f"Found {total} event{'s' if total != 1 else ''} on Polymarket."
        if query:
            summary = f"Found {total} event{'s' if total != 1 else ''} for '{query}'."
        summary += f" Top: \"{top.title}\" ({top_vol} volume)."

    return SuccessResponse(
        summary=summary,
        data=[e.model_dump() for e in events],
    )


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get detailed information about a specific event."""
    try:
        event = await gamma_svc.get_event_by_id(event_id)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch event from Polymarket. Please retry.",
            ).model_dump(),
        )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="NOT_FOUND",
                message=f"Event {event_id} not found on Polymarket.",
            ).model_dump(),
        )

    market_count = len(event.markets)
    vol = f"${event.volume:,.0f}" if event.volume else "N/A"
    summary = f"\"{event.title}\" — {market_count} market{'s' if market_count != 1 else ''}, {vol} volume."

    return SuccessResponse(
        summary=summary,
        data=event.model_dump(),
    )


@router.get("/events/slug/{slug}")
async def get_event_by_slug(
    slug: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get event details by slug."""
    try:
        event = await gamma_svc.get_event_by_slug(slug)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch event from Polymarket. Please retry.",
            ).model_dump(),
        )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="NOT_FOUND",
                message=f"Event with slug '{slug}' not found on Polymarket.",
            ).model_dump(),
        )

    market_count = len(event.markets)
    vol = f"${event.volume:,.0f}" if event.volume else "N/A"
    summary = f"\"{event.title}\" — {market_count} market{'s' if market_count != 1 else ''}, {vol} volume."

    return SuccessResponse(
        summary=summary,
        data=event.model_dump(),
    )


@router.get("/{market_id}")
async def get_market(
    market_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get detailed information about a specific market."""
    try:
        market = await gamma_svc.get_market_by_id(market_id)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch market from Polymarket. Please retry.",
            ).model_dump(),
        )

    if market is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="NOT_FOUND",
                message=f"Market {market_id} not found on Polymarket.",
            ).model_dump(),
        )

    vol = f"${market.volume:,.0f}" if market.volume else "N/A"
    outcomes_str = ", ".join(
        f"{o.outcome} ({o.price:.1%})" if o.price else o.outcome
        for o in market.outcomes
    )
    summary = f"\"{market.question}\" — {outcomes_str}. Volume: {vol}."

    return SuccessResponse(
        summary=summary,
        data=market.model_dump(),
    )
