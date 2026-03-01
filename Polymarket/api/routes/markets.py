"""Market search, browsing, and details endpoints — all categories."""

import asyncio

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment, verify_auth_only
from api.models import SuccessResponse, ErrorResponse
from api.services import gamma as gamma_svc
from api.services import history as history_svc
from api.services.categories import build_category_tree, get_tag_slugs, resolve_category

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/categories")
async def get_categories():
    """Get hierarchical market category taxonomy. Free, no auth required."""
    tree = build_category_tree()
    return SuccessResponse(
        summary=f"{len(tree)} top-level categories available. Use category paths like 'sports.nba' or 'crypto.bitcoin' with /markets/browse.",
        data=tree,
    )


@router.get("/browse")
async def browse_markets(
    category: str = Query(..., description="Category path, e.g. 'sports.nba', 'crypto.bitcoin', 'politics.geopolitics.ukraine'"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    closed: bool = Query(False, description="Include closed events"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Browse markets by category. Resolves category to tag slugs and fetches from Polymarket."""
    node = resolve_category(category)
    if node is None:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CATEGORY",
                message=f"Unknown category '{category}'. Use GET /markets/categories to see available categories.",
            ).model_dump(),
        )

    tag_slugs = get_tag_slugs(category)
    if not tag_slugs:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CATEGORY",
                message=f"Category '{category}' has no tag mappings.",
            ).model_dump(),
        )

    try:
        events = await gamma_svc.browse_by_tags(
            tag_slugs=tag_slugs, limit=limit, offset=offset, closed=closed
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch markets from Polymarket. Please retry.",
            ).model_dump(),
        )

    label = node.get("label", category)
    total = len(events)
    if total == 0:
        summary = f"No active events found in {label}."
    else:
        top = max(events, key=lambda e: e.volume or 0)
        top_vol = f"${top.volume:,.0f}" if top.volume else "N/A"
        summary = f"Found {total} event{'s' if total != 1 else ''} in {label}."
        summary += f" Top: \"{top.title}\" ({top_vol} volume)."

    return SuccessResponse(
        summary=summary,
        data=[e.model_dump() for e in events],
    )


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
    category: str | None = Query(None, description="Filter by category path (e.g. sports.nba, crypto.bitcoin). Overrides 'tag' param."),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    closed: bool = Query(False, description="Include closed events"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Search events across all Polymarket categories. Supports optional category filter."""
    # If category is provided, resolve to tag slugs and use browse_by_tags
    if category:
        node = resolve_category(category)
        if node is None:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="INVALID_CATEGORY",
                    message=f"Unknown category '{category}'. Use GET /markets/categories to see available categories.",
                ).model_dump(),
            )
        tag_slugs = get_tag_slugs(category)
        try:
            events = await gamma_svc.browse_by_tags(
                tag_slugs=tag_slugs, query=query, limit=limit, offset=offset, closed=closed
            )
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    error_code="UPSTREAM_ERROR",
                    message="Failed to search Polymarket events. Please retry.",
                ).model_dump(),
            )
    else:
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
        if category:
            label = (node or {}).get("label", category)
            summary = summary.rstrip(".") + f" in {label}."
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


@router.get("/history")
async def search_history(
    query: str | None = Query(None, description="Keyword search in title"),
    category: str | None = Query(None, description="Category path prefix (e.g. politics, sports.soccer)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Search historical (closed) Polymarket events. Paid endpoint."""
    results = await history_svc.search_history(
        query=query, category=category, limit=limit, offset=offset
    )

    total = len(results)
    if total == 0:
        summary = "No historical events found."
        if query:
            summary = f"No historical events found for '{query}'."
    else:
        top = results[0]  # already sorted by volume desc
        top_vol = f"${top['volume']:,.0f}" if top.get("volume") else "N/A"
        summary = f"Found {total} historical event{'s' if total != 1 else ''}."
        if query:
            summary = f"Found {total} historical event{'s' if total != 1 else ''} for '{query}'."
        if category:
            summary = summary.rstrip(".") + f" in {category}."
        summary += f" Top: \"{top['title']}\" ({top_vol} volume)."

    return SuccessResponse(summary=summary, data=results)


@router.post("/history/sync")
async def sync_history(
    wallet_address: str = Depends(verify_auth_only),
):
    """Trigger a sync of closed events from Polymarket. Free, auth only. Throttled to 1 hour."""
    if not history_svc.can_sync():
        stats = await history_svc.get_history_stats()
        return SuccessResponse(
            summary=f"Sync skipped — last sync was less than 1 hour ago. Database has {stats['total_events']} events.",
            data=stats,
        )

    # Run sync in background so the response returns immediately
    async def _bg_sync():
        try:
            await history_svc.sync_historical_events()
        except Exception as e:
            import logging
            logging.getLogger("agentcrab.history").error(f"Background sync failed: {e}")

    asyncio.create_task(_bg_sync())

    stats = await history_svc.get_history_stats()
    return SuccessResponse(
        summary=f"Historical events sync started in background. Current database has {stats['total_events']} events.",
        data=stats,
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
