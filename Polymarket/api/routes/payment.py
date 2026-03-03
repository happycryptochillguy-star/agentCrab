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
    """Get prepaid balance and Polymarket trading balance for a wallet."""
    await payment_svc.sync_balance(wallet_address)
    deposited, consumed, remaining = await balance_svc.get_remaining(wallet_address)
    calls = balance_svc.calls_remaining(remaining)

    from decimal import Decimal
    remaining_usdt = float(Decimal(remaining) / 10**18)

    # Derive Safe address (pure CREATE2 math, no RPC call)
    safe_address = payment_svc.derive_safe_address(wallet_address)

    # Query Polymarket trading balance (USDC.e on Polygon Safe)
    trading_balance_usdc = 0.0
    try:
        raw_bal = await payment_svc.get_polygon_usdc_balance_async(safe_address)
        trading_balance_usdc = round(raw_bal / 1e6, 4)  # USDC.e has 6 decimals
    except Exception:
        logger.warning("Failed to fetch Polygon USDC balance for %s", safe_address)

    # Build summary
    parts = []
    if calls > 0:
        parts.append(f"{calls} API calls remaining ({remaining_usdt:.4f} USDT)")
    else:
        parts.append(f"No prepaid balance. Deposit USDT to contract {settings.contract_address} on BSC")
    parts.append(f"Polymarket trading balance: {trading_balance_usdc} USDC")
    summary = f"Wallet {wallet_address[:10]}...: {'. '.join(parts)}."

    return SuccessResponse(
        summary=summary,
        data={
            "calls_remaining": calls,
            "remaining_usdt": round(remaining_usdt, 4),
            "safe_address": safe_address,
            "trading_balance_usdc": trading_balance_usdc,
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

    from decimal import Decimal
    amount_dec = Decimal(str(req.amount_usdt))
    amount_wei = int(amount_dec * 10**18)
    calls = int(amount_dec / Decimal("0.01"))

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

    # Batch size limit
    if req.signed_txs and len(req.signed_txs) > 10:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="BATCH_TOO_LARGE",
                message="Maximum 10 transactions per batch.",
            ).model_dump(),
        )

    # Validate all tx targets against whitelist
    all_txs = req.signed_txs or ([req.signed_tx] if req.signed_tx else [])
    for i, raw_tx in enumerate(all_txs):
        if not payment_svc.validate_tx_target(raw_tx, req.chain):
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="INVALID_TX_TARGET",
                    message=f"Transaction {i} targets an unknown contract. Only agentCrab and Polymarket contracts are allowed.",
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
