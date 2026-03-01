"""Deposit and withdrawal endpoints — Polymarket native bridge."""

from fastapi import APIRouter, Depends, HTTPException

from web3 import Web3

from api.auth import verify_auth_and_payment
from api.models import (
    SuccessResponse,
    ErrorResponse,
    DepositCreateRequest,
    PreparePolymarketDepositRequest,
    WithdrawCreateRequest,
)
from api.services import bridge as bridge_svc
from api.services import payment as payment_svc

router = APIRouter(prefix="/deposit", tags=["deposit"])


@router.post("/create")
async def create_deposit(
    req: DepositCreateRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get deposit addresses for funding a Polymarket account.

    Returns EVM, Solana, and Bitcoin deposit addresses. Send supported tokens
    to the EVM address from any chain (BSC, Ethereum, Polygon, Arbitrum, Base, etc.)
    and Polymarket handles the bridging automatically.
    """
    try:
        result = await bridge_svc.create_deposit_address(req.polymarket_address)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="BRIDGE_UPSTREAM_ERROR",
                message="Failed to create deposit address from Polymarket. Please retry.",
            ).model_dump(),
        )

    evm_addr = result.deposit_addresses.evm
    summary = (
        f"Deposit address created for {req.polymarket_address[:10]}... "
        f"Send supported tokens (USDT, USDC, etc.) to EVM address {evm_addr}. "
        f"Polymarket will automatically bridge to USDC.e on your Polygon account."
    )

    return SuccessResponse(
        summary=summary,
        data=result.model_dump(),
    )


@router.post("/withdraw")
async def create_withdraw(
    req: WithdrawCreateRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Get a withdrawal address for withdrawing from Polymarket to another chain.

    Send USDC.e on Polygon to the returned address, and Polymarket bridges
    to your destination chain/token.
    """
    try:
        result = await bridge_svc.create_withdraw_address(
            polymarket_address=req.polymarket_address,
            to_chain_id=req.to_chain_id,
            to_token_address=req.to_token_address,
            recipient_address=req.recipient_address,
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="BRIDGE_UPSTREAM_ERROR",
                message="Failed to create withdrawal address from Polymarket. Please retry.",
            ).model_dump(),
        )

    evm_addr = result.deposit_addresses.evm
    summary = (
        f"Withdrawal address created. Send USDC.e on Polygon to {evm_addr}. "
        f"Funds will be bridged to chain {req.to_chain_id} at {req.recipient_address[:10]}..."
    )

    return SuccessResponse(
        summary=summary,
        data=result.model_dump(),
    )


@router.post("/prepare-transfer")
async def prepare_transfer(
    req: PreparePolymarketDepositRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """One-step Polymarket deposit via fun.xyz relay.

    1. Derives Safe address from EOA
    2. Calls fun.xyz quoteV2 — returns pre-built approve + depositErc20 txs
    3. Agent signs and submits — relay delivers USDC.e to Safe on Polygon
    """
    if req.amount_usdt <= 0:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_AMOUNT",
                message="amount_usdt must be greater than 0.",
            ).model_dump(),
        )

    # 1. Derive Safe address
    try:
        safe_address = payment_svc.derive_safe_address(wallet_address)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="SAFE_DERIVATION_FAILED",
                message=f"Failed to derive Safe address: {e}",
            ).model_dump(),
        )

    # 2. Convert desired deposit to USDC.e base units (6 decimals)
    to_amount_usdc = int(req.amount_usdt * 10**6)

    # 3. Get quote from fun.xyz (returns pre-built transactions)
    try:
        quote = await bridge_svc.get_funxyz_deposit_quote(
            user_address=wallet_address,
            safe_address=safe_address,
            to_amount_usdc=to_amount_usdc,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="QUOTE_FAILED",
                message=f"Failed to get deposit quote: {e}",
            ).model_dump(),
        )

    # 4. Extract pre-built transactions, add nonces
    steps = quote["metadata"]["relayQuote"]["steps"]
    w3 = payment_svc.get_w3()
    nonce = w3.eth.get_transaction_count(w3.to_checksum_address(wallet_address))

    transactions = []
    for step in steps:
        raw_tx = step["items"][0]["data"]
        tx = {
            "from": Web3.to_checksum_address(raw_tx["from"]),
            "to": Web3.to_checksum_address(raw_tx["to"]),
            "data": raw_tx["data"],
            "value": int(raw_tx.get("value", "0")),
            "chainId": raw_tx["chainId"],
            "gas": int(raw_tx["gas"]),
            "nonce": nonce,
        }
        if "maxFeePerGas" in raw_tx:
            tx["maxFeePerGas"] = int(raw_tx["maxFeePerGas"])
            tx["maxPriorityFeePerGas"] = int(raw_tx["maxPriorityFeePerGas"])
        transactions.append({
            "step": step["id"],
            "description": step["description"],
            "transaction": tx,
        })
        nonce += 1

    est_total = quote.get("estTotalFromAmount", "?")
    est_fees = quote.get("estFeesUsd", 0)
    est_output = int(quote.get("finalToAmountBaseUnit", 0)) / 10**6

    return SuccessResponse(
        summary=(
            f"Ready to deposit ~{est_total} USDT to Polymarket. "
            f"Estimated receive: {est_output} USDC.e (fees: ~${est_fees:.4f}). "
            f"Sign all transaction(s), then POST /payment/submit-tx with signed_txs list."
        ),
        data={
            "amount_usdt": req.amount_usdt,
            "safe_address": safe_address,
            "quote_id": quote["quoteId"],
            "est_total_usdt": est_total,
            "est_output_usdc": est_output,
            "est_fees_usd": est_fees,
            "chain": "bsc",
            "transactions": transactions,
        },
    )


@router.get("/supported-assets")
async def get_supported_assets():
    """List supported chains and tokens for deposits and withdrawals.
    Free endpoint, no auth required.
    """
    try:
        assets = await bridge_svc.get_supported_assets()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch supported assets from Polymarket. Please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary="Supported chains and tokens for Polymarket deposits and withdrawals.",
        data=assets,
    )
