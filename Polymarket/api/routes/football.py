from fastapi import APIRouter, Header, Query, HTTPException

from api.config import settings
from api.models import SuccessResponse, ErrorResponse
from api.services import payment as payment_svc
from api.services import balance as balance_svc
from api.services.polymarket import fetch_football_events

router = APIRouter(prefix="/football", tags=["football"])


@router.get("/markets")
async def get_football_markets(
    league: str | None = Query(None, description="Filter by league slug (e.g. premier_league, la_liga, ucl)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_wallet_address: str = Header(..., alias="X-Wallet-Address"),
    x_signature: str = Header(..., alias="X-Signature"),
    x_message: str = Header(..., alias="X-Message"),
    x_payment_mode: str = Header(..., alias="X-Payment-Mode"),
    x_tx_hash: str | None = Header(None, alias="X-Tx-Hash"),
):
    # 1. Verify signature
    if not payment_svc.verify_signature(x_wallet_address, x_message, x_signature):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code="INVALID_SIGNATURE",
                message="Signature verification failed. Sign the message 'agentway:{unix_timestamp}' with your wallet private key (EIP-191 personal_sign). Timestamp must be within 5 minutes.",
            ).model_dump(),
        )

    # 2. Verify payment
    if x_payment_mode == "direct":
        if not x_tx_hash:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="MISSING_TX_HASH",
                    message="X-Tx-Hash header is required for direct payment mode. First call pay() on the contract, then pass the transaction hash.",
                ).model_dump(),
            )
        verified = await payment_svc.verify_direct_payment(x_tx_hash, x_wallet_address)
        if not verified:
            raise HTTPException(
                status_code=402,
                detail=ErrorResponse(
                    error_code="PAYMENT_NOT_VERIFIED",
                    message=f"Could not verify DirectPayment event for your wallet in tx {x_tx_hash}. Ensure you called pay() on contract {settings.contract_address} on BSC and the transaction is confirmed.",
                ).model_dump(),
            )

    elif x_payment_mode == "prepaid":
        remaining = await payment_svc.check_prepaid_balance(x_wallet_address)
        if remaining < settings.payment_amount_wei:
            raise HTTPException(
                status_code=402,
                detail=ErrorResponse(
                    error_code="INSUFFICIENT_BALANCE",
                    message=f"Insufficient prepaid balance. Your remaining balance is {remaining} wei. Deposit USDT to contract {settings.contract_address} on BSC (chain ID 56). Each API call costs {settings.payment_amount_wei} wei (0.01 USDT).",
                ).model_dump(),
            )
        consumed = await balance_svc.consume(
            x_wallet_address, settings.payment_amount_wei, "/football/markets"
        )
        if not consumed:
            raise HTTPException(
                status_code=402,
                detail=ErrorResponse(
                    error_code="BALANCE_DEDUCTION_FAILED",
                    message="Failed to deduct from prepaid balance. Please try again.",
                ).model_dump(),
            )

    else:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_PAYMENT_MODE",
                message="X-Payment-Mode must be 'direct' or 'prepaid'.",
            ).model_dump(),
        )

    # 3. Fetch Polymarket data
    try:
        events = await fetch_football_events(league=league, limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message=f"Failed to fetch data from Polymarket: {e}",
            ).model_dump(),
        )

    # 4. Build summary
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
