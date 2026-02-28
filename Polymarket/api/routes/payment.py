from fastapi import APIRouter, Header, Query, HTTPException

from api.config import settings
from api.models import SuccessResponse, ErrorResponse, BalanceResponse, VerifyResponse
from api.services import payment as payment_svc
from api.services import balance as balance_svc

router = APIRouter(prefix="/payment", tags=["payment"])


@router.get("/balance")
async def get_balance(
    x_wallet_address: str = Header(..., alias="X-Wallet-Address"),
    x_signature: str = Header(..., alias="X-Signature"),
    x_message: str = Header(..., alias="X-Message"),
):
    """Get prepaid balance for a wallet."""
    if not payment_svc.verify_signature(x_wallet_address, x_message, x_signature):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code="INVALID_SIGNATURE",
                message="Signature verification failed. Sign 'agentway:{unix_timestamp}' with your wallet.",
            ).model_dump(),
        )

    deposited, consumed, remaining = await balance_svc.get_remaining(x_wallet_address)
    calls = balance_svc.calls_remaining(remaining)

    balance_data = BalanceResponse(
        wallet_address=x_wallet_address.lower(),
        total_deposited_wei=str(deposited),
        total_consumed_wei=str(consumed),
        remaining_wei=str(remaining),
        calls_remaining=calls,
    )

    if calls > 0:
        summary = f"Wallet {x_wallet_address[:10]}... has {calls} API calls remaining ({remaining / 10**18:.4f} USDT)."
    else:
        summary = f"Wallet {x_wallet_address[:10]}... has no prepaid balance. Deposit USDT to contract {settings.contract_address} on BSC."

    return SuccessResponse(
        summary=summary,
        data=balance_data.model_dump(),
    )


@router.post("/verify")
async def verify_payment(
    tx_hash: str = Query(..., description="BSC transaction hash to verify"),
    x_wallet_address: str = Header(..., alias="X-Wallet-Address"),
    x_signature: str = Header(..., alias="X-Signature"),
    x_message: str = Header(..., alias="X-Message"),
):
    """Verify a direct payment transaction."""
    if not payment_svc.verify_signature(x_wallet_address, x_message, x_signature):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code="INVALID_SIGNATURE",
                message="Signature verification failed. Sign 'agentway:{unix_timestamp}' with your wallet.",
            ).model_dump(),
        )

    verified = await payment_svc.verify_direct_payment(tx_hash, x_wallet_address)

    verify_data = VerifyResponse(
        tx_hash=tx_hash,
        verified=verified,
        wallet_address=x_wallet_address.lower() if verified else None,
        message="Payment verified successfully." if verified else f"Could not verify DirectPayment event. Ensure you called pay() on {settings.contract_address} on BSC.",
    )

    if verified:
        summary = f"Transaction {tx_hash[:10]}... verified. DirectPayment from {x_wallet_address[:10]}... confirmed."
    else:
        summary = f"Transaction {tx_hash[:10]}... could NOT be verified. Check that pay() was called on the correct contract."

    return SuccessResponse(
        summary=summary,
        data=verify_data.model_dump(),
    )
