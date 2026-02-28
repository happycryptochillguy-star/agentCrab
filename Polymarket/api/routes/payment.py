from fastapi import APIRouter, Depends, Query

from api.auth import verify_auth_only
from api.config import settings
from api.models import SuccessResponse, BalanceResponse, VerifyResponse
from api.services import payment as payment_svc
from api.services import balance as balance_svc

router = APIRouter(prefix="/payment", tags=["payment"])


@router.get("/balance")
async def get_balance(
    wallet_address: str = Depends(verify_auth_only),
):
    """Get prepaid balance for a wallet."""
    deposited, consumed, remaining = await balance_svc.get_remaining(wallet_address)
    calls = balance_svc.calls_remaining(remaining)

    balance_data = BalanceResponse(
        wallet_address=wallet_address.lower(),
        total_deposited_wei=str(deposited),
        total_consumed_wei=str(consumed),
        remaining_wei=str(remaining),
        calls_remaining=calls,
    )

    if calls > 0:
        summary = f"Wallet {wallet_address[:10]}... has {calls} API calls remaining ({remaining / 10**18:.4f} USDT)."
    else:
        summary = f"Wallet {wallet_address[:10]}... has no prepaid balance. Deposit USDT to contract {settings.contract_address} on BSC."

    return SuccessResponse(
        summary=summary,
        data=balance_data.model_dump(),
    )


@router.post("/verify")
async def verify_payment(
    tx_hash: str = Query(..., description="BSC transaction hash to verify"),
    wallet_address: str = Depends(verify_auth_only),
):
    """Verify a direct payment transaction."""
    verified = await payment_svc.verify_direct_payment(tx_hash, wallet_address)

    verify_data = VerifyResponse(
        tx_hash=tx_hash,
        verified=verified,
        wallet_address=wallet_address.lower() if verified else None,
        message="Payment verified successfully." if verified else f"Could not verify DirectPayment event. Ensure you called pay() on {settings.contract_address} on BSC.",
    )

    if verified:
        summary = f"Transaction {tx_hash[:10]}... verified. DirectPayment from {wallet_address[:10]}... confirmed."
    else:
        summary = f"Transaction {tx_hash[:10]}... could NOT be verified. Check that pay() was called on the correct contract."

    return SuccessResponse(
        summary=summary,
        data=verify_data.model_dump(),
    )
