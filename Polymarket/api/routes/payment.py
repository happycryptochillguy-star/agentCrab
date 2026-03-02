import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import verify_auth_only

logger = logging.getLogger("agentcrab")
from api.config import settings
from api.models import (
    SuccessResponse,
    ErrorResponse,
    PrepareDepositRequest,
    PreparePayRequest,
    SubmitTxRequest,
)
from api.services import payment as payment_svc
from api.services import balance as balance_svc

router = APIRouter(prefix="/payment", tags=["payment"])


@router.get("/balance")
async def get_balance(
    wallet_address: str = Depends(verify_auth_only),
):
    """Get prepaid balance for a wallet."""
    await payment_svc.sync_balance(wallet_address)
    deposited, consumed, remaining = await balance_svc.get_remaining(wallet_address)
    calls = balance_svc.calls_remaining(remaining)

    remaining_usdt = remaining / 10**18

    if calls > 0:
        summary = f"Wallet {wallet_address[:10]}... has {calls} API calls remaining ({remaining_usdt:.4f} USDT)."
    else:
        summary = f"Wallet {wallet_address[:10]}... has no prepaid balance. Deposit USDT to contract {settings.contract_address} on BSC."

    return SuccessResponse(
        summary=summary,
        data={
            "calls_remaining": calls,
            "remaining_usdt": round(remaining_usdt, 4),
        },
    )


@router.post("/verify")
async def verify_payment(
    tx_hash: str = Query(..., description="BSC transaction hash to verify"),
    wallet_address: str = Depends(verify_auth_only),
):
    """Verify a direct payment transaction."""
    verified = await payment_svc.verify_direct_payment(tx_hash, wallet_address)

    if verified:
        summary = f"Transaction {tx_hash[:10]}... verified. DirectPayment from {wallet_address[:10]}... confirmed."
    else:
        summary = f"Transaction {tx_hash[:10]}... could NOT be verified. Check that pay() was called on the correct contract."

    return SuccessResponse(
        summary=summary,
        data={"verified": verified},
    )


@router.post("/prepare-deposit")
async def prepare_deposit(
    req: PrepareDepositRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Build unsigned BSC transactions for prepaid deposit.

    Returns transaction objects ready for the agent to sign with
    eth_account.sign_transaction(). Skips approve if allowance is sufficient.
    Free endpoint (auth only, no payment).
    """
    if req.amount_usdt <= 0:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_AMOUNT",
                message="amount_usdt must be greater than 0.",
            ).model_dump(),
        )

    amount_wei = int(req.amount_usdt * 10**18)
    calls = int(req.amount_usdt / 0.01)

    try:
        txs = await payment_svc.build_deposit_txs_async(wallet_address, amount_wei)
    except Exception as e:
        logger.exception("Failed to build deposit transactions for %s", wallet_address)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="TX_BUILD_FAILED",
                message="Failed to build transactions. Internal error, please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Sign and submit {len(txs)} transaction(s) to deposit {req.amount_usdt} USDT ({calls} API calls).",
        data={
            "amount_usdt": req.amount_usdt,
            "amount_wei": str(amount_wei),
            "calls": calls,
            "transactions": [
                {"step": tx["step"], "description": tx["description"], "transaction": tx["transaction"]}
                for tx in txs
            ],
        },
    )


@router.post("/prepare-pay")
async def prepare_pay(
    wallet_address: str = Depends(verify_auth_only),
):
    """Build unsigned BSC transactions for a single direct payment (0.01 USDT).

    Returns transaction objects ready for signing. Approves 100x on first use
    to avoid repeating the approve step.
    Free endpoint (auth only, no payment).
    """
    try:
        txs = await payment_svc.build_pay_tx_async(wallet_address)
    except Exception as e:
        logger.exception("Failed to build pay transactions for %s", wallet_address)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="TX_BUILD_FAILED",
                message="Failed to build transactions. Internal error, please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Sign and submit {len(txs)} transaction(s) to pay 0.01 USDT for one API call.",
        data={
            "amount_usdt": 0.01,
            "transactions": [
                {"step": tx["step"], "description": tx["description"], "transaction": tx["transaction"]}
                for tx in txs
            ],
        },
    )


@router.post("/submit-tx")
async def submit_tx(
    req: SubmitTxRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Broadcast signed transaction(s) to BSC or Polygon.

    Supports single tx (signed_tx) or batch (signed_txs).
    Batch mode broadcasts sequentially — each confirmed before the next.
    Free endpoint (auth only, no payment).
    """
    if req.chain not in ("bsc", "polygon"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_CHAIN",
                message="chain must be 'bsc' or 'polygon'.",
            ).model_dump(),
        )

    if not req.signed_tx and not req.signed_txs:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="MISSING_TX",
                message="Provide signed_tx (single) or signed_txs (batch).",
            ).model_dump(),
        )

    # Batch mode
    if req.signed_txs:
        try:
            hashes = await payment_svc.broadcast_signed_txs(req.signed_txs, chain=req.chain)
        except RuntimeError as e:
            logger.warning("Batch tx reverted on %s: %s", req.chain, e)
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="TX_REVERTED",
                    message="Transaction reverted. Please check inputs and retry.",
                ).model_dump(),
            )
        except Exception as e:
            logger.exception("Failed to broadcast batch transactions on %s", req.chain)
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error_code="BROADCAST_FAILED",
                    message="Failed to broadcast transactions. Internal error, please retry.",
                ).model_dump(),
            )

        return SuccessResponse(
            summary=f"All {len(hashes)} transaction(s) confirmed.",
            data={"tx_hashes": [f"0x{h}" for h in hashes]},
        )

    # Single tx mode (backward compatible)
    try:
        tx_hash = await payment_svc.broadcast_signed_tx(req.signed_tx, chain=req.chain)
    except RuntimeError as e:
        logger.warning("Single tx reverted on %s: %s", req.chain, e)
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="TX_REVERTED",
                message="Transaction reverted. Please check inputs and retry.",
            ).model_dump(),
        )
    except Exception as e:
        logger.exception("Failed to broadcast single transaction on %s", req.chain)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="BROADCAST_FAILED",
                message="Failed to broadcast transaction. Internal error, please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary=f"Transaction confirmed: {tx_hash}",
        data={"tx_hash": f"0x{tx_hash}"},
    )
