"""Trading endpoints — order placement, cancellation, and setup guide."""

from fastapi import APIRouter, Depends, Header, Query, HTTPException

from api.auth import verify_auth_and_payment
from api.config import settings
from api.models import SuccessResponse, ErrorResponse, OrderRequest, BatchCancelRequest

from api.services import clob as clob_svc

router = APIRouter(prefix="/trading", tags=["trading"])


# === Free Endpoints ===


@router.get("/setup")
async def get_setup_guide():
    """Polymarket trading setup guide — how to derive L2 credentials.
    Free, no auth required.
    """
    return SuccessResponse(
        summary="Polymarket trading setup guide. Follow these steps to derive your L2 credentials for trading.",
        data={
            "overview": (
                "To trade on Polymarket, you need L2 credentials (API key, secret, passphrase). "
                "These are derived from your Polygon wallet's private key using EIP-712 signatures. "
                "You only need to do this ONCE — then use the credentials for all trading API calls."
            ),
            "steps": [
                {
                    "step": 1,
                    "title": "Ensure you have a Polygon wallet",
                    "description": (
                        "Your Polymarket wallet is on Polygon (chain ID 137). "
                        "If you deposited via our /deposit/create endpoint, your funds are already on Polygon."
                    ),
                },
                {
                    "step": 2,
                    "title": "Approve tokens on Polymarket contracts",
                    "description": (
                        "Approve USDC.e and CTF tokens on the exchange contracts. "
                        "See /trading/contracts for the exact addresses."
                    ),
                },
                {
                    "step": 3,
                    "title": "Derive L2 API credentials",
                    "description": (
                        "Use the py-clob-client Python SDK to derive credentials:\n\n"
                        "```python\n"
                        "from py_clob_client.client import ClobClient\n"
                        "client = ClobClient(\n"
                        '    "https://clob.polymarket.com",\n'
                        '    key="YOUR_POLYGON_PRIVATE_KEY",\n'
                        "    chain_id=137,\n"
                        "    signature_type=0,  # 0 = EOA\n"
                        ")\n"
                        "creds = client.create_or_derive_api_creds()\n"
                        "print(creds)  # {apiKey, secret, passphrase}\n"
                        "```\n\n"
                        "Or use the CLOB API directly:\n"
                        "GET https://clob.polymarket.com/auth/derive-api-key\n"
                        "(requires L1 EIP-712 signature headers)"
                    ),
                },
                {
                    "step": 4,
                    "title": "Pass credentials in trading API calls",
                    "description": (
                        "Include these headers in all trading requests:\n"
                        "- X-Poly-Api-Key: your API key\n"
                        "- X-Poly-Secret: your secret\n"
                        "- X-Poly-Passphrase: your passphrase\n"
                        "- X-Poly-Address: your Polygon wallet address\n\n"
                        "These credentials don't expire. Store them securely."
                    ),
                },
            ],
            "sdk_install": "pip install py-clob-client",
            "sdk_repo": "https://github.com/Polymarket/py-clob-client",
        },
    )


@router.get("/contracts")
async def get_contracts():
    """Polymarket smart contract addresses and ABIs on Polygon.
    Free, no auth required.
    """
    return SuccessResponse(
        summary="Polymarket Polygon contract addresses. Approve USDC.e and CTF on the exchange contracts before trading.",
        data={
            "chain": "Polygon (Chain ID: 137)",
            "settlement_token": {
                "name": "USDC.e",
                "address": settings.polygon_usdc_address,
                "decimals": 6,
            },
            "contracts": {
                "ctf": {
                    "name": "Conditional Tokens Framework",
                    "address": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
                },
                "ctf_exchange": {
                    "name": "CTF Exchange",
                    "address": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
                },
                "neg_risk_ctf_exchange": {
                    "name": "Neg Risk CTF Exchange",
                    "address": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
                },
                "neg_risk_adapter": {
                    "name": "Neg Risk Adapter",
                    "address": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
                },
            },
            "approvals_needed": [
                {
                    "description": "Approve USDC.e on CTF Exchange",
                    "token": settings.polygon_usdc_address,
                    "spender": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
                },
                {
                    "description": "Approve USDC.e on Neg Risk CTF Exchange",
                    "token": settings.polygon_usdc_address,
                    "spender": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
                },
                {
                    "description": "Approve CTF on CTF Exchange (setApprovalForAll)",
                    "token": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
                    "spender": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
                },
                {
                    "description": "Approve CTF on Neg Risk CTF Exchange (setApprovalForAll)",
                    "token": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
                    "spender": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
                },
                {
                    "description": "Approve CTF on Neg Risk Adapter (setApprovalForAll)",
                    "token": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
                    "spender": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
                },
            ],
            "approval_abi": [
                "function approve(address spender, uint256 amount) returns (bool)",
                "function setApprovalForAll(address operator, bool approved)",
            ],
        },
    )


# === Paid Endpoints (require L2 credentials) ===


def _get_poly_creds(
    x_poly_api_key: str = Header(..., alias="X-Poly-Api-Key"),
    x_poly_secret: str = Header(..., alias="X-Poly-Secret"),
    x_poly_passphrase: str = Header(..., alias="X-Poly-Passphrase"),
    x_poly_address: str = Header(..., alias="X-Poly-Address"),
) -> dict:
    """Extract Polymarket L2 credentials from headers."""
    return {
        "api_key": x_poly_api_key,
        "secret": x_poly_secret,
        "passphrase": x_poly_passphrase,
        "poly_address": x_poly_address,
    }


@router.post("/order")
async def place_order(
    order: OrderRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds),
):
    """Place an order on Polymarket (limit or market)."""
    try:
        result = await clob_svc.place_order(
            order=order,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=creds["poly_address"],
        )
    except httpx.HTTPStatusError as e:
        detail = str(e.response.text) if hasattr(e, "response") else str(e)
        raise HTTPException(
            status_code=e.response.status_code if hasattr(e, "response") else 502,
            detail=ErrorResponse(
                error_code="ORDER_REJECTED",
                message=f"Polymarket rejected the order: {detail}",
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="ORDER_ERROR",
                message=f"Failed to place order: {e}",
            ).model_dump(),
        )

    summary = (
        f"Order placed: {result.side} {result.size} @ ${result.price} "
        f"({result.order_type}). Order ID: {result.order_id[:12]}..."
    )

    return SuccessResponse(summary=summary, data=result.model_dump())


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds),
):
    """Cancel a single order."""
    try:
        result = await clob_svc.cancel_order(
            order_id=order_id,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=creds["poly_address"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="CANCEL_ERROR",
                message=f"Failed to cancel order: {e}",
            ).model_dump(),
        )

    summary = f"Order {order_id[:12]}... cancelled successfully."
    return SuccessResponse(summary=summary, data=result)


@router.delete("/orders")
async def cancel_orders(
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds),
):
    """Cancel all open orders."""
    try:
        result = await clob_svc.cancel_all_orders(
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=creds["poly_address"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="CANCEL_ERROR",
                message=f"Failed to cancel orders: {e}",
            ).model_dump(),
        )

    summary = "All open orders cancelled."
    return SuccessResponse(summary=summary, data=result)


@router.get("/orders")
async def get_open_orders(
    market: str | None = Query(None, description="Filter by market condition ID"),
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds),
):
    """Get your open orders on Polymarket."""
    try:
        orders = await clob_svc.get_open_orders(
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=creds["poly_address"],
            market=market,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message=f"Failed to fetch open orders: {e}",
            ).model_dump(),
        )

    total = len(orders)
    if total == 0:
        summary = "No open orders on Polymarket."
    else:
        summary = f"Found {total} open order{'s' if total != 1 else ''} on Polymarket."

    return SuccessResponse(summary=summary, data=orders)
