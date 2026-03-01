"""CLOB API client — L0 (public) for orderbook/prices, L2 (authenticated) for trading."""

import base64
import hashlib
import hmac
import json as _json
import logging
import math
import random
import time
from datetime import datetime, timezone

import httpx
from eth_utils import to_checksum_address

from api.config import settings
from api.services.payment import derive_safe_address
from api.models import (
    Orderbook,
    OrderbookLevel,
    PriceSummary,
    OrderRequest,
    OrderResponse,
)

logger = logging.getLogger("agentcrab.clob")


# === L0 Public Endpoints ===


async def get_orderbook(token_id: str) -> Orderbook:
    """Get the full orderbook for a token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.clob_api_url}/book",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()

    bids = [OrderbookLevel(price=str(b["price"]), size=str(b["size"])) for b in data.get("bids", [])]
    asks = [OrderbookLevel(price=str(a["price"]), size=str(a["size"])) for a in data.get("asks", [])]

    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    midpoint = None
    spread = None
    if best_bid and best_ask:
        bb = float(best_bid)
        ba = float(best_ask)
        midpoint = str(round((bb + ba) / 2, 4))
        spread = str(round(ba - bb, 4))

    return Orderbook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        midpoint=midpoint,
    )


async def get_orderbooks_batch(token_ids: list[str]) -> list[Orderbook]:
    """Batch fetch orderbooks for multiple tokens."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.clob_api_url}/books",
            json=[{"token_id": tid} for tid in token_ids],
        )
        resp.raise_for_status()
        results = resp.json()

    orderbooks = []
    for i, data in enumerate(results):
        token_id = token_ids[i] if i < len(token_ids) else data.get("asset_id", "")
        bids = [OrderbookLevel(price=str(b["price"]), size=str(b["size"])) for b in data.get("bids", [])]
        asks = [OrderbookLevel(price=str(a["price"]), size=str(a["size"])) for a in data.get("asks", [])]

        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        midpoint = None
        spread = None
        if best_bid and best_ask:
            bb = float(best_bid)
            ba = float(best_ask)
            midpoint = str(round((bb + ba) / 2, 4))
            spread = str(round(ba - bb, 4))

        orderbooks.append(
            Orderbook(
                token_id=token_id,
                bids=bids,
                asks=asks,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
                midpoint=midpoint,
            )
        )
    return orderbooks


async def get_price(token_id: str) -> PriceSummary:
    """Get price summary for a token (best bid, ask, midpoint, spread, last trade)."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Fetch multiple price metrics in parallel
        price_resp, midpoint_resp, spread_resp, last_trade_resp = await _fetch_price_data(
            client, token_id
        )

    best_bid = None
    best_ask = None
    if price_resp:
        best_bid = str(price_resp.get("bid", "")) or None
        best_ask = str(price_resp.get("ask", "")) or None

    return PriceSummary(
        token_id=token_id,
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=str(midpoint_resp.get("mid", "")) if midpoint_resp else None,
        spread=str(spread_resp.get("spread", "")) if spread_resp else None,
        last_trade_price=str(last_trade_resp.get("price", "")) if last_trade_resp else None,
    )


async def _fetch_price_data(client: httpx.AsyncClient, token_id: str):
    """Fetch all price metrics from CLOB. Returns (price, midpoint, spread, last_trade)."""
    import asyncio

    async def _get(endpoint: str, params: dict) -> dict | None:
        try:
            resp = await client.get(f"{settings.clob_api_url}{endpoint}", params=params)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    results = await asyncio.gather(
        _get("/price", {"token_id": token_id, "side": "buy"}),
        _get("/midpoint", {"token_id": token_id}),
        _get("/spread", {"token_id": token_id}),
        _get("/last-trade-price", {"token_id": token_id}),
    )
    return results


async def get_prices_batch(token_ids: list[str]) -> list[PriceSummary]:
    """Batch fetch price summaries."""
    import asyncio
    return await asyncio.gather(*[get_price(tid) for tid in token_ids])


# === L2 Authenticated Endpoints (Trading) ===


# Contract addresses (Polygon)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Rounding config by tick size: (price_decimals, size_decimals, amount_decimals)
ROUNDING_CONFIG = {
    "0.1": (1, 2, 3),
    "0.01": (2, 2, 4),
    "0.001": (3, 2, 5),
    "0.0001": (4, 2, 6),
}


def _clob_client_kwargs() -> dict:
    kwargs: dict = {"timeout": 15}
    if settings.polymarket_proxy:
        kwargs["proxy"] = settings.polymarket_proxy
    return kwargs


def _build_l2_headers(
    api_key: str,
    secret: str,
    passphrase: str,
    eoa_address: str,
    method: str,
    path: str,
    body: str = "",
) -> dict[str, str]:
    """Build HMAC-SHA256 authentication headers for CLOB L2 endpoints.

    Matches py-clob-client SDK exactly:
    - Key: base64url-decoded secret
    - Signature: base64url-encoded HMAC-SHA256 digest
    - POLY_ADDRESS: EOA address (not Safe)
    """
    timestamp = str(int(time.time()))
    message = timestamp + method + path
    if body:
        message += body
    h = hmac.new(
        base64.urlsafe_b64decode(secret),
        message.encode("utf-8"),
        hashlib.sha256,
    )
    sig = base64.urlsafe_b64encode(h.digest()).decode("utf-8")

    return {
        "POLY_ADDRESS": eoa_address,
        "POLY_SIGNATURE": sig,
        "POLY_TIMESTAMP": timestamp,
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
    }


async def place_order(
    order: OrderRequest,
    api_key: str,
    secret: str,
    passphrase: str,
    poly_address: str,
) -> OrderResponse:
    """Place an order on Polymarket CLOB using L2 credentials."""
    import json

    body = json.dumps({
        "tokenID": order.token_id,
        "side": order.side.upper(),
        "size": str(order.size),
        "price": str(order.price),
        "type": order.order_type,
        "expiration": order.expiration or "0",
    })

    headers = _build_l2_headers(api_key, secret, passphrase, poly_address, "POST", "/order", body)
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.clob_api_url}/order",
            headers=headers,
            content=body,
        )
        resp.raise_for_status()
        data = resp.json()

    return OrderResponse(
        order_id=data.get("orderID", data.get("id", "")),
        status=data.get("status", "LIVE"),
        token_id=order.token_id,
        side=order.side,
        size=str(order.size),
        price=str(order.price),
        order_type=order.order_type,
    )


async def cancel_order(
    order_id: str,
    api_key: str,
    secret: str,
    passphrase: str,
    poly_address: str,
) -> dict:
    """Cancel a single order."""
    import json
    body = json.dumps({"orderID": order_id})

    headers = _build_l2_headers(api_key, secret, passphrase, poly_address, "DELETE", "/order", body)
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            "DELETE",
            f"{settings.clob_api_url}/order",
            headers=headers,
            content=body,
        )
        resp.raise_for_status()
        return resp.json()


async def cancel_all_orders(
    api_key: str,
    secret: str,
    passphrase: str,
    poly_address: str,
) -> dict:
    """Cancel all open orders."""
    headers = _build_l2_headers(api_key, secret, passphrase, poly_address, "DELETE", "/cancel-all")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            "DELETE",
            f"{settings.clob_api_url}/cancel-all",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def get_open_orders(
    api_key: str,
    secret: str,
    passphrase: str,
    poly_address: str,
    market: str | None = None,
) -> list[dict]:
    """Get open orders for the authenticated user."""
    path = "/data/orders"
    params = {}
    if market:
        params["market"] = market

    headers = _build_l2_headers(api_key, secret, passphrase, poly_address, "GET", path)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.clob_api_url}{path}",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    # CLOB returns paginated {data, next_cursor, limit, count}
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


async def derive_api_credentials(
    wallet_address: str,
    signature: str,
    timestamp: str,
    nonce: int = 0,
) -> dict:
    """Create or derive Polymarket CLOB API credentials.

    Tries POST /auth/api-key (create) first, falls back to
    GET /auth/derive-api-key (derive) — matching the SDK behavior.
    Returns {"apiKey": ..., "secret": ..., "passphrase": ...}.
    """
    headers = {
        "POLY_ADDRESS": wallet_address,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": timestamp,
        "POLY_NONCE": str(nonce),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # Try create first (for wallets that haven't created keys yet)
        resp = await client.post(
            f"{settings.clob_api_url}/auth/api-key",
            headers=headers,
        )
        if resp.status_code == 200:
            return resp.json()

        # Fall back to derive (for wallets that already have keys)
        logger.info("Create API key returned %s, falling back to derive", resp.status_code)
        resp = await client.get(
            f"{settings.clob_api_url}/auth/derive-api-key",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


# === Order Building (prepare-order / submit-order) ===


def _generate_salt() -> int:
    """Generate random salt for order uniqueness (matches SDK)."""
    now = datetime.now(tz=timezone.utc).timestamp()
    return round(now * random.random())


def _round_down(val: float, decimals: int) -> float:
    """Truncate (floor) a float to N decimal places."""
    factor = 10 ** decimals
    return math.floor(val * factor) / factor


def _to_token_decimals(x: float) -> int:
    """Convert human-readable amount to 6-decimal integer."""
    return int(round(x * 10**6))


async def get_tick_size(token_id: str) -> str:
    """Get the tick size for a market from CLOB."""
    async with httpx.AsyncClient(**_clob_client_kwargs()) as client:
        resp = await client.get(
            f"{settings.clob_api_url}/tick-size",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("minimum_tick_size", "0.01")


async def get_neg_risk(token_id: str) -> bool:
    """Check if a token belongs to a neg-risk market."""
    async with httpx.AsyncClient(**_clob_client_kwargs()) as client:
        resp = await client.get(
            f"{settings.clob_api_url}/neg-risk",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("neg_risk", False)


async def get_fee_rate_bps(token_id: str) -> int:
    """Get the fee rate in basis points for a market."""
    async with httpx.AsyncClient(**_clob_client_kwargs()) as client:
        resp = await client.get(
            f"{settings.clob_api_url}/fee-rate",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()
    return int(float(data.get("base_fee", 0)))


async def get_market_context(token_id: str) -> dict:
    """Look up market question and outcome for a token_id via Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.gamma_api_url}/markets",
                params={"clob_token_ids": token_id},
            )
            if resp.status_code != 200 or not resp.json():
                return {}
            m = resp.json()[0]
            question = m.get("question", "")
            outcome = ""
            token_ids_raw = m.get("clobTokenIds", "")
            outcomes_raw = m.get("outcomes", "")
            if token_ids_raw and outcomes_raw:
                ids = [t.strip().strip('"') for t in token_ids_raw.strip("[]").split(",")]
                outcomes = [o.strip().strip('"') for o in outcomes_raw.strip("[]").split(",")]
                for i, tid in enumerate(ids):
                    if tid == token_id and i < len(outcomes):
                        outcome = outcomes[i]
                        break
            return {"question": question, "outcome": outcome}
    except Exception:
        return {}


async def build_order_typed_data(
    eoa_address: str,
    token_id: str,
    side: str,
    size: float,
    price: float,
) -> dict:
    """Build EIP-712 typed data for a Polymarket order.

    Returns typed_data (for agent to sign) + order metadata (for submit).
    The agent signs with Account.sign_typed_data(domain, types, message).
    """
    # Fetch market params from CLOB + market context from Gamma (parallel)
    import asyncio
    tick_size_t, neg_risk_t, fee_rate_t, context_t = await asyncio.gather(
        get_tick_size(token_id),
        get_neg_risk(token_id),
        get_fee_rate_bps(token_id),
        get_market_context(token_id),
    )
    tick_size, neg_risk, fee_rate_bps, market_ctx = tick_size_t, neg_risk_t, fee_rate_t, context_t

    # Determine exchange address
    exchange = NEG_RISK_CTF_EXCHANGE if neg_risk else CTF_EXCHANGE

    # Calculate amounts
    price_dec, size_dec, _ = ROUNDING_CONFIG.get(tick_size, (2, 2, 4))
    rounded_price = round(price, price_dec)
    rounded_size = _round_down(size, size_dec)

    side_int = 0 if side.upper() == "BUY" else 1

    if side_int == 0:  # BUY: pay USDC.e, receive tokens
        taker_amount = _to_token_decimals(rounded_size)
        maker_amount = _to_token_decimals(rounded_size * rounded_price)
    else:  # SELL: give tokens, receive USDC.e
        maker_amount = _to_token_decimals(rounded_size)
        taker_amount = _to_token_decimals(rounded_size * rounded_price)

    safe_address = derive_safe_address(eoa_address)
    salt = _generate_salt()

    # Build order message (values as ints for EIP-712 signing)
    order_message = {
        "salt": salt,
        "maker": to_checksum_address(safe_address),
        "signer": to_checksum_address(eoa_address),
        "taker": ZERO_ADDRESS,
        "tokenId": int(token_id),
        "makerAmount": maker_amount,
        "takerAmount": taker_amount,
        "expiration": 0,
        "nonce": 0,
        "feeRateBps": fee_rate_bps,
        "side": side_int,
        "signatureType": 2,  # POLY_GNOSIS_SAFE
    }

    typed_data = {
        "domain": {
            "name": "Polymarket CTF Exchange",
            "version": "1",
            "chainId": 137,
            "verifyingContract": to_checksum_address(exchange),
        },
        "types": {
            "Order": [
                {"name": "salt", "type": "uint256"},
                {"name": "maker", "type": "address"},
                {"name": "signer", "type": "address"},
                {"name": "taker", "type": "address"},
                {"name": "tokenId", "type": "uint256"},
                {"name": "makerAmount", "type": "uint256"},
                {"name": "takerAmount", "type": "uint256"},
                {"name": "expiration", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "feeRateBps", "type": "uint256"},
                {"name": "side", "type": "uint8"},
                {"name": "signatureType", "type": "uint8"},
            ],
        },
        "primaryType": "Order",
        "message": order_message,
    }

    # Build the CLOB submission body — field types must match SDK exactly:
    # salt=int, signatureType=int, everything else=str
    clob_order = {
        "salt": salt,
        "maker": to_checksum_address(safe_address),
        "signer": to_checksum_address(eoa_address),
        "taker": ZERO_ADDRESS,
        "tokenId": token_id,
        "makerAmount": str(maker_amount),
        "takerAmount": str(taker_amount),
        "expiration": "0",
        "nonce": "0",
        "feeRateBps": str(fee_rate_bps),
        "side": "BUY" if side_int == 0 else "SELL",
        "signatureType": 2,
    }

    side_str = "BUY" if side_int == 0 else "SELL"
    cost_usdc = round(rounded_size * rounded_price, 6)

    return {
        "typed_data": typed_data,
        "clob_order": clob_order,
        "exchange_address": to_checksum_address(exchange),
        "neg_risk": neg_risk,
        "tick_size": tick_size,
        "price": rounded_price,
        "size": rounded_size,
        "cost_usdc": cost_usdc,
        "side": side_str,
        "market": market_ctx,
    }


async def post_signed_order(
    clob_order: dict,
    signature: str,
    order_type: str,
    api_key: str,
    secret: str,
    passphrase: str,
    eoa_address: str,
) -> dict:
    """Post a signed order to the Polymarket CLOB.

    The clob_order comes from build_order_typed_data's clob_order field.
    Signature is the EIP-712 signature from the agent.
    """
    clob_order["signature"] = signature

    body_dict = {
        "order": clob_order,
        "owner": api_key,
        "orderType": order_type,
    }
    # Compact JSON with no spaces — must match SDK for HMAC to verify
    body = _json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False)

    headers = _build_l2_headers(
        api_key, secret, passphrase, eoa_address, "POST", "/order", body,
    )
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(**_clob_client_kwargs()) as client:
        resp = await client.post(
            f"{settings.clob_api_url}/order",
            headers=headers,
            content=body,
        )
        resp.raise_for_status()
        return resp.json()
