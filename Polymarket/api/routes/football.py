from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.models import SuccessResponse, ErrorResponse
from api.services.polymarket import fetch_football_events

router = APIRouter(prefix="/football", tags=["football"])


@router.get("/markets")
async def get_football_markets(
    league: str | None = Query(None, description="Filter by league slug (e.g. premier_league, la_liga, ucl)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    # Fetch Polymarket data
    try:
        events = await fetch_football_events(league=league, limit=limit, offset=offset)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch data from Polymarket. Please retry in a few seconds.",
            ).model_dump(),
        )

    # Build summary
    total = len(events)
    if total == 0:
        summary = "No active football events found on Polymarket."
        if league:
            summary = f"No active football events found for league '{league}' on Polymarket."
    else:
        top_event = max(events, key=lambda e: e.volume or 0)
        top_vol = f"${top_event.volume:,.0f}" if top_event.volume else "N/A"
        summary = f"Found {total} active football event{'s' if total != 1 else ''} on Polymarket."
        if league:
            summary = f"Found {total} active '{league}' event{'s' if total != 1 else ''} on Polymarket."
        summary += f" Top event: \"{top_event.title}\" with {top_vol} in volume."

    return SuccessResponse(
        summary=summary,
        data=[e.model_dump() for e in events],
    )
