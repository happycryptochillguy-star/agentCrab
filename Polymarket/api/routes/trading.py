"""Trading endpoints — order placement, cancellation, and setup guide."""

import logging
import time as _time

import httpx

logger = logging.getLogger("agentcrab")
from fastapi import APIRouter, Depends, Header, Query, HTTPException, Request
from pydantic import BaseModel

from api.auth import verify_auth_and_payment, verify_auth_only
from api.config import settings
from api.models import (
    SuccessResponse, ErrorResponse,
    SubmitDeploySafeRequest, SubmitApprovalsRequest,
    PrepareOrderRequest, SubmitOrderRequest,
    PrepareBatchOrderRequest, SubmitBatchOrderRequest,
)

from api.services import balance as balance_svc
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
        summary="Polymarket trading setup guide. All steps are handled by our API — no SDK or direct contract calls needed.",
        data={
            "overview": (
                "To trade on Polymarket, you need L2 credentials (API key, secret, passphrase). "
                "These are derived via our API using EIP-712 signatures. "
                "You only need to do this ONCE — then use the credentials for all trading calls."
            ),
            "steps": [
                "1. POST /trading/prepare-deploy-safe → sign typed data → POST /trading/submit-deploy-safe",
                "2. POST /trading/prepare-enable → personal_sign SafeTx hash → POST /trading/submit-approvals",
                "3. Sign clob_typed_data → POST /trading/submit-credentials → get L2 creds",
                "4. Use X-Poly-Api-Key, X-Poly-Secret, X-Poly-Passphrase headers for all trading calls",
            ],
            "note": "All Polygon operations are gasless. No SDK install needed.",
        },
    )


@router.get("/contracts")
async def get_contracts():
    """Polymarket smart contract addresses and ABIs on Polygon.
    Free, no auth required.
    """
    return SuccessResponse(
        summary="Polymarket contracts on Polygon. All approvals are handled gaslessly by POST /trading/submit-approvals.",
        data={
            "chain": "Polygon (Chain ID: 137)",
            "settlement_token": "USDC.e (6 decimals)",
            "note": "You do NOT need to interact with these contracts directly. Use /trading/prepare-enable → /trading/submit-approvals for gasless setup.",
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
        deployed = await relayer_svc.is_safe_deployed(wallet_address)
    except Exception as e:
        logger.exception("Failed to check Safe deployment for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="RELAYER_ERROR",
                message="Failed to check Safe deployment. Internal error, please retry.",
            ).model_dump(),
        )

    if deployed:
        return SuccessResponse(
            summary=f"Safe already deployed at {safe_address}. Skip to /trading/prepare-enable.",
            data={"already_deployed": True, "safe_address": safe_address},
        )

    typed_data = relayer_svc.build_create_proxy_typed_data()  # pure computation, no HTTP
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
        result = await relayer_svc.deploy_safe(wallet_address, req.signature)
    except Exception as e:
        logger.exception("Failed to deploy Safe via relayer for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="DEPLOY_FAILED",
                message="Failed to deploy Safe via relayer. Internal error, please retry.",
            ).model_dump(),
        )

    tx_id = result.get("transactionID")
    tx_hash = result.get("transactionHash")

    # Poll until confirmed (non-blocking)
    if tx_id:
        try:
            await relayer_svc.poll_transaction(tx_id, max_polls=30, interval=2.0)
        except Exception as e:
            logger.warning("Safe deployment polling timed out for %s: %s", wallet_address, e)
            return SuccessResponse(
                summary="Safe deployment submitted but not yet confirmed. Please check back shortly.",
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
        deployed = await relayer_svc.is_safe_deployed(wallet_address)
    except Exception as e:
        logger.exception("Failed to check Safe deployment in prepare_enable for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="RELAYER_ERROR",
                message="Failed to check Safe deployment. Internal error, please retry.",
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
        approval_status = await relayer_svc.check_approval_status(safe_address)
    except Exception as e:
        # If check fails, fall back to building all approvals
        logger.warning("Approval status check failed for %s, falling back to full approvals: %s", safe_address, e)
        approval_status = {"all_approved": False, "missing": [], "approved": []}

    # Build SafeTx hash only for missing approvals
    approval_data = None
    if not approval_status["all_approved"]:
        try:
            only_missing = approval_status["missing"] if approval_status["missing"] else None
            approval_data = await relayer_svc.build_approval_data(
                wallet_address, only_missing=only_missing,
            )
        except Exception as e:
            logger.exception("Failed to build approval data for %s", wallet_address)
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    error_code="APPROVAL_BUILD_FAILED",
                    message="Failed to build approval data. Internal error, please retry.",
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

    # Strip verbose approval_status — agent only needs to know what's missing
    simplified_approval = {
        "all_approved": approval_status["all_approved"],
    }
    if approval_status.get("missing"):
        simplified_approval["missing_count"] = len(approval_status["missing"])

    return SuccessResponse(
        summary=summary,
        data={
            "safe_address": safe_address,
            "approvals_needed": not approval_status["all_approved"],
            "approval_status": simplified_approval,
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
        result = await relayer_svc.submit_approvals(
            wallet_address, req.signature, req.approval_data.model_dump(),
        )
    except Exception as e:
        logger.exception("Failed to submit approvals via relayer for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="APPROVAL_SUBMIT_FAILED",
                message="Failed to submit approvals via relayer. Internal error, please retry.",
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
        logger.exception("Failed to derive API credentials for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="DERIVE_FAILED",
                message="Failed to derive API credentials from Polymarket. Internal error, please retry.",
            ).model_dump(),
        )

    api_key = creds.get("apiKey")
    secret = creds.get("secret")
    passphrase = creds.get("passphrase")

    # Cache L2 credentials server-side for future retrieval
    try:
        await balance_svc.save_l2_credentials(wallet_address, api_key, secret, passphrase)
    except Exception:
        logger.warning("Failed to cache L2 credentials for %s (non-fatal)", wallet_address)

    # Tell CLOB to refresh cached balance/allowances for this wallet.
    # Without this, newly onboarded wallets show balance=0 even though
    # their Safe has USDC.e and all approvals set on-chain.
    balance_update = None
    try:
        balance_update = await clob_svc.update_balance_allowance(
            api_key=api_key,
            secret=secret,
            passphrase=passphrase,
            eoa_address=wallet_address,
        )
    except Exception:
        logger.warning("balance-allowance/update failed for %s (non-fatal)", wallet_address)

    return SuccessResponse(
        summary="Polymarket L2 credentials derived and cached. Use as X-Poly-* headers for trading, or retrieve later via GET /trading/credentials.",
        data={
            "api_key": api_key,
            "secret": secret,
            "passphrase": passphrase,
            "balance_allowance_updated": balance_update is not None,
        },
    )


@router.get("/credentials")
async def get_credentials(
    wallet_address: str = Depends(verify_auth_only),
):
    """Retrieve cached L2 trading credentials.

    Free — returns credentials previously derived via submit-credentials.
    Saves agents from re-deriving (and paying 0.01 USDT) each session.
    """
    creds = await balance_svc.get_l2_credentials(wallet_address)
    if not creds:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="NO_CREDENTIALS",
                message="No cached L2 credentials found. Call POST /trading/submit-credentials first.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary="Cached L2 credentials retrieved. Use as X-Poly-* headers for trading.",
        data=creds,
    )


# === Order Placement (prepare-submit pattern) ===


def _get_poly_creds_no_address(
    x_poly_api_key: str = Header(..., alias="X-Poly-Api-Key"),
    x_poly_secret: str = Header(..., alias="X-Poly-Secret"),
    x_poly_passphrase: str = Header(..., alias="X-Poly-Passphrase"),
) -> dict:
    """Extract Polymarket L2 credentials from headers (address derived server-side)."""
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
    import base64
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


@router.post("/refresh-balance")
async def refresh_balance(
    wallet_address: str = Depends(verify_auth_only),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Tell the Polymarket CLOB to refresh its cached balance/allowances.

    Call this after:
    - depositing USDC.e to Polymarket (wait 1-2 min for relay, then call)
    - setting up trading for the first time
    - any on-chain changes to your Safe

    Free endpoint — no payment required.
    """
    try:
        result = await clob_svc.update_balance_allowance(
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            eoa_address=wallet_address,
        )
    except Exception as e:
        logger.warning("balance-allowance/update failed for %s: %s", wallet_address, e)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="REFRESH_FAILED",
                message="Failed to refresh balance. Internal error, please retry.",
            ).model_dump(),
        )

    return SuccessResponse(
        summary="CLOB balance/allowance cache refreshed.",
        data=result,
    )


@router.post("/prepare-order")
async def prepare_order(
    req: PrepareOrderRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Build EIP-712 typed data for a Polymarket order.

    Agent signs with Account.sign_typed_data(domain, types, message),
    then submits signature + clob_order to POST /trading/submit-order.
    """
    # Input validation: fail fast before hitting CLOB
    if not (0.001 <= req.price <= 0.999):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_PRICE",
                message=f"Price must be between 0.001 and 0.999, got {req.price}.",
            ).model_dump(),
        )
    if req.size <= 0:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_SIZE",
                message=f"Size must be positive, got {req.size}.",
            ).model_dump(),
        )
    try:
        result = await clob_svc.build_order_typed_data(
            eoa_address=wallet_address,
            token_id=req.token_id,
            side=req.side,
            size=req.size,
            price=req.price,
        )
    except Exception as e:
        logger.exception("Failed to build order for %s (token=%s)", wallet_address, req.token_id)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="ORDER_BUILD_FAILED",
                message="Failed to build order. Internal error, please retry.",
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

    # Strip internal fields agent doesn't need
    simplified = {
        "typed_data": result["typed_data"],
        "clob_order": result["clob_order"],
        "side": result["side"],
        "price": result["price"],
        "size": result["size"],
        "cost_usdc": result["cost_usdc"],
    }
    if market:
        simplified["market"] = market

    return SuccessResponse(summary=summary, data=simplified)


@router.post("/submit-order")
async def submit_order(
    req: SubmitOrderRequest,
    wallet_address: str = Depends(verify_auth_and_payment),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Submit a signed order to Polymarket CLOB.

    Takes the EIP-712 signature and clob_order from prepare-order.
    Refunds balance if CLOB submission fails.
    """
    try:
        result = await clob_svc.post_signed_order(
            clob_order=req.clob_order.model_dump(),
            signature=req.signature,
            order_type=req.order_type,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            eoa_address=wallet_address,
        )
    except httpx.HTTPStatusError as e:
        # Refund the deducted balance on CLOB rejection
        await balance_svc.credit_deposit(wallet_address, settings.payment_amount_wei)
        payment_svc.invalidate_balance_cache(wallet_address)
        logger.warning("Polymarket rejected order for %s (refunded): %s", wallet_address[:10], e.response.text if hasattr(e, "response") else e)
        raise HTTPException(
            status_code=e.response.status_code if hasattr(e, "response") else 502,
            detail=ErrorResponse(
                error_code="ORDER_REJECTED",
                message="Polymarket rejected the order (balance refunded). Please check order parameters and retry.",
            ).model_dump(),
        )
    except Exception as e:
        # Refund the deducted balance on internal error
        await balance_svc.credit_deposit(wallet_address, settings.payment_amount_wei)
        payment_svc.invalidate_balance_cache(wallet_address)
        logger.exception("Failed to submit order for %s (refunded)", wallet_address[:10])
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="ORDER_ERROR",
                message="Failed to submit order (balance refunded). Internal error, please retry.",
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

    # Simplified response — only what the agent/user needs
    data: dict = {
        "order_id": order_id,
        "status": status,
        "success": success,
    }
    if result.get("takingAmount"):
        data["taking_amount"] = result["takingAmount"]
    if result.get("makingAmount"):
        data["making_amount"] = result["makingAmount"]
    if tx_hashes:
        data["tx_hash"] = tx_hashes[0]
        data["polygonscan_url"] = f"https://polygonscan.com/tx/{tx_hashes[0]}"
    if not success and result.get("errorMsg"):
        data["error"] = result["errorMsg"]

    return SuccessResponse(summary=summary, data=data)


# === Batch Order Placement ===


@router.post("/prepare-batch-order")
async def prepare_batch_order(
    req: PrepareBatchOrderRequest,
    wallet_address: str = Depends(verify_auth_only),
):
    """Build EIP-712 typed data for multiple orders at once.

    Agent signs each typed_data individually, then submits all to
    POST /trading/submit-batch-order.
    Max 15 orders per batch.
    """
    if not req.orders or len(req.orders) > 15:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_BATCH_SIZE",
                message="Batch must contain 1-15 orders.",
            ).model_dump(),
        )

    # Validate each order's price and size
    for i, o in enumerate(req.orders):
        if not (0.001 <= o.price <= 0.999):
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="INVALID_PRICE",
                    message=f"Order {i}: price must be between 0.001 and 0.999, got {o.price}.",
                ).model_dump(),
            )
        if o.size <= 0:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="INVALID_SIZE",
                    message=f"Order {i}: size must be positive, got {o.size}.",
                ).model_dump(),
            )

    orders_dicts = [
        {"token_id": o.token_id, "side": o.side, "size": o.size, "price": o.price}
        for o in req.orders
    ]

    results = await clob_svc.build_batch_order_typed_data(
        eoa_address=wallet_address,
        orders=orders_dicts,
    )

    prepared = []
    errors = []
    total_cost = 0.0

    for i, result in enumerate(results):
        if "error" in result:
            errors.append({"index": i, "token_id": req.orders[i].token_id, "error": result["error"]})
            continue

        market = result.get("market", {})
        item = {
            "index": i,
            "typed_data": result["typed_data"],
            "clob_order": result["clob_order"],
            "side": result["side"],
            "price": result["price"],
            "size": result["size"],
            "cost_usdc": result["cost_usdc"],
        }
        if market:
            item["market"] = market
        prepared.append(item)
        total_cost += result["cost_usdc"]

    ok_count = len(prepared)
    err_count = len(errors)
    summary = f"{ok_count} order(s) ready to sign (${total_cost:.2f} total)."
    if err_count:
        summary += f" {err_count} failed to prepare."

    data: dict = {"orders": prepared, "total_cost_usdc": round(total_cost, 6)}
    if errors:
        data["errors"] = errors

    return SuccessResponse(summary=summary, data=data)


@router.post("/submit-batch-order")
async def submit_batch_order(
    req: SubmitBatchOrderRequest,
    request: Request,
    wallet_address: str = Depends(verify_auth_only),
    creds: dict = Depends(_get_poly_creds_no_address),
):
    """Submit multiple signed orders to Polymarket CLOB.

    Cost: N x 0.01 USDT (one charge per order in the batch).
    Uses verify_auth_only + manual variable-amount deduction.
    """
    if not req.orders or len(req.orders) > 15:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_BATCH_SIZE",
                message="Batch must contain 1-15 orders.",
            ).model_dump(),
        )

    # Atomic check-and-deduct in a single SQL UPDATE with WHERE guard.
    # No separate balance check — prevents race condition with concurrent requests.
    n = len(req.orders)
    total_cost_wei = n * settings.payment_amount_wei
    consumed = await balance_svc.consume(
        wallet_address, total_cost_wei, request.url.path,
    )
    if not consumed:
        raise HTTPException(
            status_code=402,
            detail=ErrorResponse(
                error_code="INSUFFICIENT_BALANCE",
                message=(
                    f"Insufficient prepaid balance. Batch of {n} orders costs "
                    f"{n} x 0.01 = {n * 0.01:.2f} USDT. Deposit USDT to contract "
                    f"{settings.contract_address} on BSC (chain ID 56)."
                ),
            ).model_dump(),
        )
    payment_svc.invalidate_balance_cache(wallet_address)

    # Submit orders
    signed_items = [
        {
            "clob_order": o.clob_order.model_dump(),
            "signature": o.signature,
            "order_type": o.order_type,
        }
        for o in req.orders
    ]

    try:
        results = await clob_svc.post_signed_orders_batch(
            signed_orders=signed_items,
            api_key=creds["api_key"],
            secret=creds["secret"],
            passphrase=creds["passphrase"],
            eoa_address=wallet_address,
        )
    except Exception as e:
        # Refund the full batch cost on total failure
        await balance_svc.credit_deposit(wallet_address, total_cost_wei)
        payment_svc.invalidate_balance_cache(wallet_address)
        logger.exception("Failed to submit batch order for %s (refunded %d orders)", wallet_address[:10], n)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="BATCH_ORDER_ERROR",
                message="Failed to submit batch order (balance refunded). Internal error, please retry.",
            ).model_dump(),
        )

    # Build response
    order_results = []
    success_count = 0
    for i, r in enumerate(results):
        if isinstance(r, dict) and r.get("error"):
            order_results.append({"index": i, "success": False, "error": r["error"]})
        else:
            entry: dict = {"index": i, "success": True}
            if isinstance(r, dict):
                entry["order_id"] = r.get("orderID", r.get("id", ""))
                entry["status"] = r.get("status", "unknown")
                if r.get("takingAmount"):
                    entry["taking_amount"] = r["takingAmount"]
                if r.get("makingAmount"):
                    entry["making_amount"] = r["makingAmount"]
                tx_hashes = r.get("transactionsHashes", [])
                if tx_hashes:
                    entry["tx_hash"] = tx_hashes[0]
            success_count += 1
            order_results.append(entry)

    fail_count = n - success_count

    # Refund only failed orders (proportional, not full refund)
    if fail_count > 0:
        refund_wei = fail_count * settings.payment_amount_wei
        await balance_svc.credit_deposit(wallet_address, refund_wei)
        payment_svc.invalidate_balance_cache(wallet_address)

    actual_charged = success_count * 0.01
    summary = f"{success_count}/{n} orders submitted successfully."
    if fail_count:
        summary += f" {fail_count} failed (refunded {fail_count} x 0.01 USDT)."

    return SuccessResponse(
        summary=summary,
        data={"results": order_results, "total_charged_usdt": round(actual_charged, 2)},
    )


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
        logger.exception("Failed to cancel order %s for %s", order_id, wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="CANCEL_ERROR",
                message="Failed to cancel order. Internal error, please retry.",
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
        logger.exception("Failed to cancel all orders for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="CANCEL_ERROR",
                message="Failed to cancel orders. Internal error, please retry.",
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
        logger.exception("Failed to fetch open orders for %s", wallet_address)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error_code="UPSTREAM_ERROR",
                message="Failed to fetch open orders. Internal error, please retry.",
            ).model_dump(),
        )

    total = len(orders)
    if total == 0:
        summary = "No open orders on Polymarket."
    else:
        summary = f"{total} open order{'s' if total != 1 else ''} on Polymarket."

    # Simplify CLOB order objects
    simplified = []
    for o in orders:
        entry: dict = {
            "order_id": o.get("id", ""),
            "side": o.get("side", ""),
            "price": o.get("price", ""),
            "original_size": o.get("original_size", ""),
            "size_matched": o.get("size_matched", ""),
            "status": o.get("status", ""),
        }
        if o.get("asset_id"):
            entry["token_id"] = o["asset_id"]
        if o.get("created_at"):
            entry["created_at"] = o["created_at"]
        simplified.append(entry)

    return SuccessResponse(summary=summary, data=simplified)
