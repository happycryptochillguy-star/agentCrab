"""Category leaderboard endpoints — per-category trader rankings."""

import asyncio

from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import verify_auth_and_payment, verify_auth_only
from api.models import SuccessResponse, ErrorResponse
from api.services import category_leaderboard as cat_lb_svc
from api.services.categories import resolve_category

router = APIRouter(prefix="/traders/categories", tags=["category-leaderboard"])


@router.get("/leaderboard")
async def get_category_leaderboard(
    category: str = Query(..., description="Category path, e.g. 'crypto', 'sports.nba', 'politics.trump'"),
    sort_by: str = Query("pnl", description="Sort by: pnl, volume, positions, win_rate"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get top traders in a specific category.

    Returns traders ranked by their performance in the given category.
    Data is synced every 4 hours from top 200 global traders.
    """
    node = resolve_category(category)
    if node is None:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CATEGORY",
                message=f"Unknown category '{category}'. Use GET /markets/categories to see available categories.",
            ).model_dump(),
        )

    if sort_by not in ("pnl", "volume", "positions", "win_rate"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_SORT",
                message="sort_by must be one of: pnl, volume, positions, win_rate",
            ).model_dump(),
        )

    entries, meta = await cat_lb_svc.get_category_leaderboard(
        category_path=category, sort_by=sort_by, limit=limit, offset=offset
    )

    label = node.get("label", category)
    total = meta["total_count"]

    if total == 0:
        summary = f"No category leaderboard data for {label}. Data syncs every 4 hours from top 200 global traders."
    else:
        top = entries[0] if entries else None
        if top:
            name = top["display_name"] or top["address"][:10] + "..."
            pnl_str = f"${top['total_pnl']:,.2f}" if top["total_pnl"] else "N/A"
            summary = f"Top {len(entries)} of {total} traders in {label} (sorted by {sort_by}). #1: {name} ({pnl_str} PnL)."
        else:
            summary = f"{total} traders found in {label}."

    return SuccessResponse(
        summary=summary,
        data={"entries": entries, "meta": meta},
    )


@router.get("/{address}/profile")
async def get_trader_category_profile(
    address: str,
    category: str | None = Query(None, description="Optional: filter to specific category"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get a trader's per-category performance breakdown.

    Without category: returns all categories this trader has positions in.
    With category: returns that category's stats + individual positions.
    """
    if category:
        node = resolve_category(category)
        if node is None:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="INVALID_CATEGORY",
                    message=f"Unknown category '{category}'.",
                ).model_dump(),
            )

    profile = await cat_lb_svc.get_trader_category_profile(address, category)

    cats = profile.get("categories", [])
    name = profile.get("display_name") or address[:10] + "..."

    if not cats:
        summary = f"No category data found for {name}. Data syncs every 4 hours from top 200 global traders."
    elif category:
        c = cats[0] if cats else {}
        pnl_str = f"${c.get('total_pnl', 0):,.2f}"
        pos_count = c.get("total_positions", 0)
        n_positions = len(profile.get("positions", []))
        summary = f"{name} in {category}: {pnl_str} PnL across {pos_count} positions. {n_positions} active positions shown."
    else:
        top_cat = cats[0] if cats else {}
        summary = f"{name} active in {len(cats)} categories. Best: {top_cat.get('category_path', '?')} (${top_cat.get('total_pnl', 0):,.2f} PnL)."

    return SuccessResponse(summary=summary, data=profile)


@router.get("/stats")
async def get_category_stats(
    category: str = Query(..., description="Category path, e.g. 'crypto', 'sports'"),
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get aggregate statistics for a category.

    Shows total traders, volume, average PnL, best/worst performers.
    """
    node = resolve_category(category)
    if node is None:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CATEGORY",
                message=f"Unknown category '{category}'.",
            ).model_dump(),
        )

    stats = await cat_lb_svc.get_category_stats(category)

    label = node.get("label", category)
    total = stats["total_traders"]

    if total == 0:
        summary = f"No stats for {label}. Data syncs every 4 hours."
    else:
        avg_pnl_str = f"${stats['avg_pnl']:,.2f}"
        summary = f"{label}: {total} traders, avg PnL {avg_pnl_str}."
        if stats.get("best_trader_pnl") is not None:
            summary += f" Best: ${stats['best_trader_pnl']:,.2f}."

    return SuccessResponse(summary=summary, data=stats)


@router.post("/sync")
async def trigger_sync(
    wallet_address: str = Depends(verify_auth_only),
):
    """Manually trigger category leaderboard sync. Free, auth only. Throttled to 2 hours."""
    if not cat_lb_svc.can_sync():
        status = await cat_lb_svc.get_sync_status()
        return SuccessResponse(
            summary=f"Sync skipped — last sync was less than 2 hours ago. {status['leaderboard_entries']} leaderboard entries cached.",
            data=status,
        )

    async def _bg_sync():
        try:
            await cat_lb_svc.sync_category_leaderboard()
        except Exception as e:
            import logging
            logging.getLogger("agentcrab.category_lb").error(f"Background sync failed: {e}")

    asyncio.create_task(_bg_sync())

    status = await cat_lb_svc.get_sync_status()
    return SuccessResponse(
        summary="Category leaderboard sync started in background.",
        data=status,
    )
