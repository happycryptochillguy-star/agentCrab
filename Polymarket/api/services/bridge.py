"""Bridge service using Polymarket's native deposit/withdraw API.

Polymarket provides deposit addresses for EVM, Solana, and Bitcoin chains.
Users simply transfer supported tokens to the deposit address, and Polymarket
handles the bridging to USDC.e on Polygon automatically.
"""

import logging

import httpx

from api.config import settings
from api.models import (
    DepositAddresses,
    DepositCreateResponse,
    WithdrawCreateResponse,
)

logger = logging.getLogger("agentcrab.bridge")

# Polymarket Bridge API base URL (part of the CLOB API)
BRIDGE_API_URL = settings.clob_api_url


async def create_deposit_address(polymarket_address: str) -> DepositCreateResponse:
    """Create deposit addresses for a Polymarket wallet.

    Calls Polymarket's POST /deposit endpoint. Returns EVM, Solana, and Bitcoin
    deposit addresses. The user sends supported tokens to the EVM address from
    any supported chain (BSC, Ethereum, Polygon, Arbitrum, Base, etc.) and
    Polymarket automatically bridges to USDC.e on Polygon.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BRIDGE_API_URL}/deposit",
            json={"address": polymarket_address},
        )
        resp.raise_for_status()
        data = resp.json()

    addr = data.get("address", {})

    return DepositCreateResponse(
        polymarket_address=polymarket_address,
        deposit_addresses=DepositAddresses(
            evm=addr.get("evm"),
            svm=addr.get("svm"),
            btc=addr.get("btc"),
        ),
        note=data.get("note"),
    )


async def create_withdraw_address(
    polymarket_address: str,
    to_chain_id: str,
    to_token_address: str,
    recipient_address: str,
) -> WithdrawCreateResponse:
    """Create a withdrawal address for withdrawing from Polymarket.

    Calls Polymarket's POST /withdraw endpoint. User sends USDC.e on Polygon
    to the returned address, and Polymarket bridges to the destination chain/token.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BRIDGE_API_URL}/withdraw",
            json={
                "address": polymarket_address,
                "toChainId": to_chain_id,
                "toTokenAddress": to_token_address,
                "recipientAddr": recipient_address,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    addr = data.get("address", {})

    return WithdrawCreateResponse(
        deposit_addresses=DepositAddresses(
            evm=addr.get("evm"),
            svm=addr.get("svm"),
            btc=addr.get("btc"),
        ),
        note=data.get("note"),
    )


async def get_supported_assets() -> list[dict]:
    """Get supported chains and tokens for deposits/withdrawals.

    Calls Polymarket's GET /supported-assets endpoint.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BRIDGE_API_URL}/supported-assets")
        resp.raise_for_status()
        return resp.json()
