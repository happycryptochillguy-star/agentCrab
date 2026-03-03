"""Trigger endpoints — stop loss / take profit with pre-signed orders."""

import base64
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

logger = logging.getLogger("agentcrab")

from api.auth import verify_auth_and_payment, verify_auth_only
from api.config import settings
from api.models import (
    SuccessResponse,
    ErrorResponse,
    PrepareTriggerRequest,
    CreateTriggerRequest,
)
from api.services import clob as clob_svc
from api.services import triggers as trigger_svc

router = APIRouter(prefix="/trading/triggers", tags=["triggers"])


def _get_poly_creds(
    x_poly_api_key: str = Header(..., alias="X-Poly-Api-Key"),
    x_poly_secret: str = Header(..., alias="X-Poly-Secret"),
    x_poly_passphrase: str = Header(..., alias="X-Poly-Passphrase"),
) -> dict:
    # Validate non-empty
    if not x_poly_api_key or not x_poly_secret or not x_poly_passphrase:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CREDENTIALS",
                message="X-Poly-Api-Key, X-Poly-Secret, and X-Poly-Passphrase headers must all be non-empty.",
            ).model_dump(),
        )
    # Validate base64 format for secret
    try:
        base64.urlsafe_b64decode(x_poly_secret)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CREDENTIALS",
                message="X-Poly-Secret is not valid base64. Check your L2 credentials.",
            ).model_dump(),
        )
    return {
        "api_key": x_poly_api_key,
        "secret": x_poly_secret,
        "passphrase": x_poly_passphrase,
    }


@router.post("/prepare")
async def prepare_trigger(
    req: PrepareTriggerRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Build EIP-712 typed data for a trigger's exit order.

    Agent signs the typed_data, then submits to POST /trading/triggers/create.
    Free — no payment required.
    """
    if req.trigger_type not in ("stop_loss", "take_profit"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_TRIGGER_TYPE",
                message="trigger_type must be 'stop_loss' or 'take_profit'.",
            ).model_dump(),
        )

    if req.exit_side.upper() not in ("BUY", "SELL"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_SIDE",
                message="exit_side must be 'BUY' or 'SELL'.",
            ).model_dump(),
        )

    if req.trigger_price < 0.001 or req.trigger_price > 0.999:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_TRIGGER_PRICE",
                message="trigger_price must be between 0.001 and 0.999.",
            ).model_dump(),
        )

    if req.size <= 0:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_SIZE",
                message="size must be positive.",
            ).model_dump(),
        )

    if req.exit_price < 0.001 or req.exit_price > 0.999:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_EXIT_PRICE",
                message="exit_price must be between 0.001 and 0.999.",
            ).model_dump(),
        )

    try:
        result = await clob_svc.build_order_typed_data(
            eoa_address=wallet_address,
            token_id=req.token_id,
            side=req.exit_side,
            size=req.size,
            price=req.exit_price,
        )
    except Exception as e:
        logger.exception("Failed to build exit order for trigger (token=%s)", req.token_id)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="ORDER_BUILD_FAILED",
                message="Failed to build exit order. Internal error, please retry.",
            ).model_dump(),
        )

    market = result.get("market", {})
    question = market.get("question", "")
    outcome = market.get("outcome", "")
    label = f'"{outcome}" on "{question}"' if question and outcome else f"token {req.token_id[:12]}..."

    trigger_desc = "Stop Loss" if req.trigger_type == "stop_loss" else "Take Profit"
    summary = (
        f"{trigger_desc} ready: {req.exit_side.upper()} {result['size']} shares of {label} "
        f"@ ${result['price']} when price hits ${req.trigger_price}. "
        f"Sign typed_data and submit to POST /trading/triggers/create."
    )

    return SuccessResponse(
        summary=summary,
        data={
            "typed_data": result["typed_data"],
            "clob_order": result["clob_order"],
            "order_type": "GTC",
            "side": result["side"],
            "price": result["price"],
            "size": result["size"],
            "cost_usdc": result["cost_usdc"],
            "trigger_type": req.trigger_type,
            "trigger_price": req.trigger_price,
            "market": market,
        },
    )


@router.post("/create")
async def create_trigger(
    req: CreateTriggerRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds),
):
    """Store a trigger with pre-signed order. Server monitors and executes.

    Cost: 0.01 USDT.
    """
    if req.trigger_type not in ("stop_loss", "take_profit"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_TRIGGER_TYPE",
                message="trigger_type must be 'stop_loss' or 'take_profit'.",
            ).model_dump(),
        )

    try:
        result = await trigger_svc.create_trigger(
            wallet_address=wallet_address,
            token_id=req.token_id,
            trigger_type=req.trigger_type,
            trigger_price=req.trigger_price,
            exit_side=req.exit_side,
            clob_order=req.clob_order.model_dump(),
            signature=req.signature,
            order_type=req.order_type,
            l2_api_key=creds["api_key"],
            l2_secret=creds["secret"],
            l2_passphrase=creds["passphrase"],
            size=req.size,
            price=req.exit_price,
            market_question=req.market_question,
            market_outcome=req.market_outcome,
            expires_in_hours=req.expires_in_hours,
        )
    except Exception as e:
        logger.exception("Failed to create trigger for %s (token=%s)", wallet_address, req.token_id)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="TRIGGER_CREATE_FAILED",
                message="Failed to create trigger. Internal error, please retry.",
            ).model_dump(),
        )

    trigger_desc = "Stop Loss" if req.trigger_type == "stop_loss" else "Take Profit"
    summary = (
        f"{trigger_desc} trigger created (ID: {result['trigger_id'][:12]}...). "
        f"Monitoring {req.token_id[:12]}... for price {'<=' if req.trigger_type == 'stop_loss' and req.exit_side.upper() == 'SELL' else '>='} ${req.trigger_price}."
    )

    return SuccessResponse(summary=summary, data=result)


@router.get("")
async def get_triggers(
    status: str | None = Query(None, description="Filter: active, triggered, cancelled, failed, expired"),
    token_id: str | None = Query(None, description="Filter by token_id"),
    wallet_address: str = Depends(verify_auth_only),
):
    """List your triggers. Free."""
    triggers = await trigger_svc.list_triggers(
        wallet_address=wallet_address,
        status=status,
        token_id=token_id,
    )

    total = len(triggers)
    active = sum(1 for t in triggers if t.get("status") == "active")
    if total == 0:
        summary = "No triggers found."
    else:
        summary = f"{total} trigger(s) ({active} active)."

    return SuccessResponse(summary=summary, data=triggers)


@router.get("/{trigger_id}")
async def get_trigger(
    trigger_id: str,
    wallet_address: str = Depends(verify_auth_only),
):
    """Get a single trigger. Free."""
    trigger = await trigger_svc.get_trigger(trigger_id, wallet_address)
    if not trigger:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="TRIGGER_NOT_FOUND",
                message=f"Trigger {trigger_id} not found.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Trigger {trigger_id[:12]}... ({trigger['status']}).",
        data=trigger,
    )


@router.delete("/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
    wallet_address: str = Depends(verify_auth_only),
):
    """Cancel a single trigger. Free."""
    cancelled = await trigger_svc.cancel_trigger(trigger_id, wallet_address)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="TRIGGER_NOT_FOUND",
                message=f"Trigger {trigger_id} not found or not active.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Trigger {trigger_id[:12]}... cancelled.",
        data={"trigger_id": trigger_id, "status": "cancelled"},
    )


@router.delete("")
async def delete_all_triggers(
    token_id: str | None = Query(None, description="Filter by token_id"),
    wallet_address: str = Depends(verify_auth_only),
):
    """Cancel all active triggers. Free."""
    count = await trigger_svc.cancel_all_triggers(wallet_address, token_id)
    if token_id:
        summary = f"{count} trigger(s) for token {token_id[:12]}... cancelled."
    else:
        summary = f"{count} trigger(s) cancelled."

    return SuccessResponse(
        summary=summary,
        data={"cancelled_count": count},
    )
