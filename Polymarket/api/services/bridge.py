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

# Polymarket Bridge API base URL
BRIDGE_API_URL = settings.bridge_api_url

# BSC USDT (18 decimals) and Polygon USDC.e (6 decimals)
BSC_USDT = "0x55d398326f99059fF775485246999027B3197955"
POLYGON_USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def _client_kwargs() -> dict:
    """Build httpx client kwargs with proxy if configured."""
    kwargs: dict = {"timeout": 30}
    if settings.polymarket_proxy:
        kwargs["proxy"] = settings.polymarket_proxy
    return kwargs


async def get_funxyz_deposit_quote(
    user_address: str, safe_address: str, to_amount_usdc: int
) -> dict:
    """Get a deposit quote from fun.xyz (Polymarket's relay provider).

    Calls POST /v1/checkout/quoteV2 with BSC USDT → Polygon USDC.e.
    Returns the full response including pre-built transactions (approve +
    depositErc20) ready for the agent to sign, plus fee breakdown.

    Args:
        user_address: EOA wallet address (sender on BSC)
        safe_address: Polymarket Safe address (recipient on Polygon)
        to_amount_usdc: Desired USDC.e output in base units (6 decimals)
    """
    async with httpx.AsyncClient(**_client_kwargs()) as client:
        resp = await client.post(
            f"{settings.fun_xyz_api_url}/v1/checkout/quoteV2",
            headers={
                "x-api-key": settings.fun_xyz_api_key,
                "Origin": "https://polymarket.com",
                "Referer": "https://polymarket.com/",
            },
            json={
                "actionParams": [],
                "fromChainId": "56",
                "fromTokenAddress": BSC_USDT,
                "recipientAddress": safe_address,
                "toAmountBaseUnit": hex(to_amount_usdc),
                "toChainId": "137",
                "toTokenAddress": POLYGON_USDC_E,
                "userAddress": user_address,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_deposit_address(polymarket_address: str) -> DepositCreateResponse:
    """Create deposit addresses for a Polymarket wallet.

    Calls Polymarket's POST /deposit endpoint. Returns EVM, Solana, and Bitcoin
    deposit addresses. The user sends supported tokens to the EVM address from
    any supported chain (BSC, Ethereum, Polygon, Arbitrum, Base, etc.) and
    Polymarket automatically bridges to USDC.e on Polygon.
    """
    async with httpx.AsyncClient(**_client_kwargs()) as client:
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
    async with httpx.AsyncClient(**_client_kwargs()) as client:
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
    async with httpx.AsyncClient(**_client_kwargs()) as client:
        resp = await client.get(f"{BRIDGE_API_URL}/supported-assets")
        resp.raise_for_status()
        return resp.json()
