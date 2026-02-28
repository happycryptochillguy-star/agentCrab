"""CLOB API client — L0 (public) for orderbook/prices, L2 (authenticated) for trading."""

import hashlib
import hmac
import logging
import time

import httpx

from api.config import settings
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


def _build_l2_headers(
    api_key: str,
    secret: str,
    passphrase: str,
    method: str,
    path: str,
    body: str = "",
) -> dict[str, str]:
    """Build HMAC-SHA256 authentication headers for CLOB L2 endpoints."""
    timestamp = str(int(time.time()))
    message = timestamp + method.upper() + path + body
    signature = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "POLY_ADDRESS": "",  # Will be set per-request
        "POLY_SIGNATURE": signature,
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

    headers = _build_l2_headers(api_key, secret, passphrase, "POST", "/order", body)
    headers["POLY_ADDRESS"] = poly_address
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

    headers = _build_l2_headers(api_key, secret, passphrase, "DELETE", "/order", body)
    headers["POLY_ADDRESS"] = poly_address
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
    headers = _build_l2_headers(api_key, secret, passphrase, "DELETE", "/cancel-all")
    headers["POLY_ADDRESS"] = poly_address

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

    headers = _build_l2_headers(api_key, secret, passphrase, "GET", path)
    headers["POLY_ADDRESS"] = poly_address

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.clob_api_url}{path}",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        return resp.json()
