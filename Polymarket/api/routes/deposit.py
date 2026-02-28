"""Deposit and withdrawal endpoints — Polymarket native bridge."""

from fastapi import APIRouter, Depends, HTTPException

from api.auth import verify_auth_and_payment
from api.models import (
    SuccessResponse,
    ErrorResponse,
    DepositCreateRequest,
    WithdrawCreateRequest,
)
from api.services import bridge as bridge_svc

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
