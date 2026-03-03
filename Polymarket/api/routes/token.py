"""$CRAB token endpoints: points query, leaderboard, token info."""

from fastapi import APIRouter, Depends, Query

from api.auth import verify_auth_only
from api.models import SuccessResponse
from api.config import settings
from api.services import points as points_svc

router = APIRouter(prefix="/token", tags=["token"])


@router.get("/points")
async def get_points(wallet: str = Depends(verify_auth_only)):
    """Get your $CRAB airdrop points. Free, auth required."""
    data = await points_svc.get_points(wallet)
    total = data["total_points"]
    return SuccessResponse(
        summary=f"You have {total:,} points ({data['deposit_points']:,} from deposits + {data['usage_points']:,} from usage).",
        data=data,
    )


@router.get("/points/leaderboard")
async def get_points_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Points leaderboard. Free, no auth required."""
    entries = await points_svc.get_leaderboard(limit=limit, offset=offset)
    stats = await points_svc.get_total_stats()
    return SuccessResponse(
        summary=f"Points leaderboard: {stats['total_users']} users, {stats['total_points']:,} total points.",
        data={
            "leaderboard": entries,
            "stats": stats,
        },
    )


@router.get("/info")
async def get_token_info():
    """$CRAB token info and rules. Free, no auth required."""
    crab_address = settings.crab_token_address
    airdrop_address = settings.crab_airdrop_address

    stats = await points_svc.get_total_stats()

    token_info = {
        "name": "Crab Token",
        "symbol": "CRAB",
        "chain": "BSC (BEP-20)",
        "decimals": 18,
        "total_supply": "1,000,000,000",
        "contract_address": crab_address or "Not yet deployed",
        "airdrop_contract": airdrop_address or "Not yet deployed",
    }

    points_rules = {
        "deposit": "1 USDT deposited = 100 points",
        "usage": "1 API call = 1 point (0.01 USDT consumed)",
        "formula": "total_points = deposit_points + usage_points",
        "example": "Deposit 10 USDT + use all 1000 calls = 1,000 + 1,000 = 2,000 points",
        "retroactive": True,
        "note": "All historical deposits and usage count — points are retroactive from day 1.",
    }

    airdrop_info = {
        "phase_1_allocation": "25% (250,000,000 CRAB)",
        "claim_window_days": 90,
        "value_multiplier": "2x — your airdrop value will be at least 2× your total spend",
        "status": "accumulating" if not crab_address else "live",
    }

    distribution = {
        "airdrop_phase_1": "25%",
        "liquidity_pool": "5%",
        "team": "15% (6mo cliff + 18mo vesting)",
        "treasury": "20%",
        "future_airdrops": "20%",
        "ecosystem": "15%",
    }

    return SuccessResponse(
        summary=f"$CRAB token — {stats['total_users']} users earning points. {'Token live!' if crab_address else 'Token not yet deployed — keep earning points!'}",
        data={
            "token": token_info,
            "points_rules": points_rules,
            "airdrop": airdrop_info,
            "distribution": distribution,
            "current_stats": stats,
        },
    )
