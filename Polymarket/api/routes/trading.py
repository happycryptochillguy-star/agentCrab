"""Trading endpoints — order placement, cancellation, and setup guide."""

import time as _time

import httpx
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import BaseModel

from api.auth import verify_auth_and_payment, verify_auth_only
from api.config import settings
from api.models import (
    SuccessResponse, ErrorResponse,
    SubmitDeploySafeRequest, SubmitApprovalsRequest,
    PrepareOrderRequest, SubmitOrderRequest,
)

from api.services import clob as clob_svc
from api.services import payment as payment_svc
from api.services import relayer as relayer_svc

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


# === Safe Deployment ===


@router.post("/prepare-deploy-safe")
async def prepare_deploy_safe(
    wallet_address: str = Depends(verify_auth_only),
):
    """Check if Safe is deployed; if not, return EIP-712 typed data to sign.

    Agent signs with Account.sign_typed_data(domain, types, message),
    then submits signature to POST /trading/submit-deploy-safe.
    """
    safe_address = payment_svc.derive_safe_address(wallet_address)
    try:
        deployed = relayer_svc.is_safe_deployed(wallet_address)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="RELAYER_ERROR",
                message=f"Failed to check Safe deployment: {e}",
            ).model_dump(),
        )

    if deployed:
        return SuccessResponse(
            summary=f"Safe already deployed at {safe_address}. Skip to /trading/prepare-enable.",
            data={"already_deployed": True, "safe_address": safe_address},
        )

    typed_data = relayer_svc.build_create_proxy_typed_data()
    return SuccessResponse(
        summary=(
            f"Safe not yet deployed. Sign the typed data with sign_typed_data() "
            f"and submit to POST /trading/submit-deploy-safe."
        ),
        data={
            "already_deployed": False,
            "safe_address": safe_address,
            "typed_data": typed_data,
            "signing_method": "Account.sign_typed_data(domain, types, message)",
        },
    )


@router.post("/submit-deploy-safe")
async def submit_deploy_safe(
    req: SubmitDeploySafeRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Submit CreateProxy signature to deploy Safe via Polymarket relayer.

    Gasless — relayer pays Polygon gas. Polls until deployment confirms.
    """
    safe_address = payment_svc.derive_safe_address(wallet_address)
    try:
        result = relayer_svc.deploy_safe(wallet_address, req.signature)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="DEPLOY_FAILED",
                message=f"Failed to deploy Safe via relayer: {e}",
            ).model_dump(),
        )

    tx_id = result.get("transactionID")
    tx_hash = result.get("transactionHash")

    # Poll until confirmed (non-blocking)
    if tx_id:
        try:
            await relayer_svc.poll_transaction(tx_id, max_polls=30, interval=2.0)
        except Exception as e:
            return SuccessResponse(
                summary=f"Safe deployment submitted but not yet confirmed: {e}",
                data={
                    "safe_address": safe_address,
                    "transaction_id": tx_id,
                    "transaction_hash": tx_hash,
                    "status": "pending",
                },
            )

    return SuccessResponse(
        summary=f"Safe deployed at {safe_address}. Proceed to /trading/prepare-enable.",
        data={
            "safe_address": safe_address,
            "transaction_id": tx_id,
            "transaction_hash": tx_hash,
            "status": "confirmed",
        },
    )


# === Enable Trading ===


class SubmitCredentialsRequest(BaseModel):
    signature: str  # EIP-712 signature (0x-prefixed hex)
    timestamp: str  # The timestamp used in the typed data


@router.post("/prepare-enable")
async def prepare_enable(
    wallet_address: str = Depends(verify_auth_only),
):
    """Prepare everything needed to enable Polymarket trading.

    Returns:
    1. approval_data — SafeTx hash for agent to personal_sign (approvals via relayer)
    2. clob_typed_data — EIP-712 typed data for agent to sign_typed_data (L2 credentials)

    Both are gasless. Approvals go through Polymarket's relayer; CLOB credentials
    are derived via HTTP.
    """
    # Check Safe deployment
    safe_address = payment_svc.derive_safe_address(wallet_address)
    try:
        deployed = relayer_svc.is_safe_deployed(wallet_address)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="RELAYER_ERROR",
                message=f"Failed to check Safe deployment: {e}",
            ).model_dump(),
        )

    if not deployed:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="SAFE_NOT_DEPLOYED",
                message=(
                    f"Safe at {safe_address} is not deployed. "
                    f"Call POST /trading/prepare-deploy-safe first."
                ),
            ).model_dump(),
        )

    # Check on-chain approval status
    try:
        approval_status = relayer_svc.check_approval_status(safe_address)
    except Exception as e:
        # If check fails, fall back to building all approvals
        approval_status = {"all_approved": False, "missing": [], "approved": []}

    # Build SafeTx hash only for missing approvals
    approval_data = None
    if not approval_status["all_approved"]:
        try:
            only_missing = approval_status["missing"] if approval_status["missing"] else None
            approval_data = relayer_svc.build_approval_data(
                wallet_address, only_missing=only_missing,
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    error_code="APPROVAL_BUILD_FAILED",
                    message=f"Failed to build approval data: {e}",
                ).model_dump(),
            )

    # Build CLOB auth typed data
    timestamp = str(int(_time.time()))
    clob_typed_data = {
        "domain": {
            "name": "ClobAuthDomain",
            "version": "1",
            "chainId": settings.polygon_chain_id,
        },
        "types": {
            "ClobAuth": [
                {"name": "address", "type": "address"},
                {"name": "timestamp", "type": "string"},
                {"name": "nonce", "type": "uint256"},
                {"name": "message", "type": "string"},
            ],
        },
        "primaryType": "ClobAuth",
        "message": {
            "address": wallet_address,
            "timestamp": timestamp,
            "nonce": 0,
            "message": "This message attests that I control the given wallet",
        },
    }

    # Build response summary based on approval status
    if approval_status["all_approved"]:
        summary = (
            f"All token approvals already set. Only sign clob_typed_data "
            f"with sign_typed_data and submit to /trading/submit-credentials."
        )
    elif approval_data:
        n_missing = len(approval_status.get("missing", []))
        summary = (
            f"{n_missing} of 7 approvals missing. "
            f"Sign approval_data.hash with personal_sign and clob_typed_data with sign_typed_data. "
            f"Submit to /trading/submit-approvals and /trading/submit-credentials."
        )
    else:
        summary = (
            f"Sign clob_typed_data with sign_typed_data "
            f"and submit to /trading/submit-credentials."
        )

    return SuccessResponse(
        summary=summary,
        data={
            "safe_address": safe_address,
            "approvals_needed": not approval_status["all_approved"],
            "approval_status": approval_status,
            "approval_data": approval_data,
            "clob_typed_data": clob_typed_data,
        },
    )


@router.post("/submit-approvals")
async def submit_approvals(
    req: SubmitApprovalsRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Submit token approval signature to Polymarket relayer.

    Gasless — relayer executes Safe.execTransaction() on Polygon.
    The signature should be a personal_sign of the SafeTx hash
    from prepare-enable's approval_data.
    """
    try:
        result = relayer_svc.submit_approvals(
            wallet_address, req.signature, req.approval_data,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="APPROVAL_SUBMIT_FAILED",
                message=f"Failed to submit approvals via relayer: {e}",
            ).model_dump(),
        )

    tx_id = result.get("transactionID")
    return SuccessResponse(
        summary="Token approvals submitted to relayer. They will confirm shortly.",
        data={
            "transaction_id": tx_id,
            "transaction_hash": result.get("transactionHash"),
            "status": "submitted",
        },
    )


@router.post("/submit-credentials")
async def submit_credentials(
    req: SubmitCredentialsRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
):
    """Submit EIP-712 signature to derive Polymarket L2 API credentials.

    The agent signs clob_typed_data from POST /trading/prepare-enable
    with sign_typed_data(), then sends the signature here.
    """
    try:
        creds = await clob_svc.derive_api_credentials(
            wallet_address=wallet_address,
            signature=req.signature,
            timestamp=req.timestamp,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="DERIVE_FAILED",
                message=f"Failed to derive API credentials from Polymarket: {e}",
            ).model_dump(),
        )

    return SuccessResponse(
        summary="Polymarket L2 credentials derived. Store these securely and use as X-Poly-* headers for trading.",
        data={
            "api_key": creds.get("apiKey"),
            "secret": creds.get("secret"),
            "passphrase": creds.get("passphrase"),
            "usage": {
                "X-Poly-Api-Key": creds.get("apiKey"),
                "X-Poly-Secret": creds.get("secret"),
                "X-Poly-Passphrase": creds.get("passphrase"),
                "X-Poly-Address": wallet_address,
            },
        },
    )


# === Order Placement (prepare-submit pattern) ===


def _get_poly_creds_no_address(
    x_poly_api_key: str = Header(..., alias="X-Poly-Api-Key"),
    x_poly_secret: str = Header(..., alias="X-Poly-Secret"),
    x_poly_passphrase: str = Header(..., alias="X-Poly-Passphrase"),
) -> dict:
    """Extract Polymarket L2 credentials from headers (address derived server-side)."""
    return {
        "api_key": x_poly_api_key,
        "secret": x_poly_secret,
        "passphrase": x_poly_passphrase,
    }


@router.post("/prepare-order")
async def prepare_order(
    req: PrepareOrderRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Build EIP-712 typed data for a Polymarket order.

    Agent signs with Account.sign_typed_data(domain, types, message),
    then submits signature + clob_order to POST /trading/submit-order.
    """
    try:
        result = await clob_svc.build_order_typed_data(
            eoa_address=wallet_address,
            token_id=req.token_id,
            side=req.side,
            size=req.size,
            price=req.price,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="ORDER_BUILD_FAILED",
                message=f"Failed to build order: {e}",
            ).model_dump(),
        )

    # Build human-readable summary
    market = result.get("market", {})
    question = market.get("question", "")
    outcome = market.get("outcome", "")
    label = f'"{outcome}" on "{question}"' if question and outcome else f"token {req.token_id[:12]}..."
    summary = (
        f"Order ready: {result['side']} {result['size']} shares of {label} "
        f"@ ${result['price']} (${result['cost_usdc']} total). "
        f"Sign typed_data and submit to POST /trading/submit-order."
    )

    return SuccessResponse(summary=summary, data=result)


@router.post("/submit-order")
async def submit_order(
    req: SubmitOrderRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Submit a signed order to Polymarket CLOB.

    Takes the EIP-712 signature and clob_order from prepare-order.
    """
    try:
        result = await clob_svc.post_signed_order(
            clob_order=req.clob_order,
            signature=req.signature,
            order_type=req.order_type,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            eoa_address=wallet_address,
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
                message=f"Failed to submit order: {e}",
            ).model_dump(),
        )

    order_id = result.get("orderID", result.get("id", ""))
    status = result.get("status", "unknown")
    success = result.get("success", False)
    tx_hashes = result.get("transactionsHashes", [])

    # Build human-readable summary
    if status == "matched" and success:
        taking = result.get("takingAmount", "?")
        making = result.get("makingAmount", "?")
        side = req.clob_order.get("side", "?")
        if side == "BUY":
            summary = f"Order filled: bought {taking} shares for ${making} USDC."
        else:
            summary = f"Order filled: sold {making} shares for ${taking} USDC."
    elif status == "delayed":
        summary = f"Order accepted, pending fill. ID: {order_id[:16]}..."
    elif not success:
        error_msg = result.get("errorMsg", "Unknown error")
        summary = f"Order failed: {error_msg}"
    else:
        summary = f"Order submitted ({status}). ID: {order_id[:16]}..."

    # Include tx hash for on-chain verification
    data = dict(result)
    if tx_hashes:
        data["polygonscan_url"] = f"https://polygonscan.com/tx/{tx_hashes[0]}"

    return SuccessResponse(summary=summary, data=data)


# === Cancel / Query Orders (L2 auth, server derives EOA) ===


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Cancel a single order."""
    try:
        result = await clob_svc.cancel_order(
            order_id=order_id,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=wallet_address,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="CANCEL_ERROR",
                message=f"Failed to cancel order: {e}",
            ).model_dump(),
        )

    summary = f"Order {order_id[:16]}... cancelled."
    return SuccessResponse(summary=summary, data=result)


@router.delete("/orders")
async def cancel_orders(
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Cancel all open orders."""
    try:
        result = await clob_svc.cancel_all_orders(
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=wallet_address,
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
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Get your open orders on Polymarket."""
    try:
        orders = await clob_svc.get_open_orders(
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            poly_address=wallet_address,
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
        summary = f"{total} open order{'s' if total != 1 else ''} on Polymarket."

    return SuccessResponse(summary=summary, data=orders)
