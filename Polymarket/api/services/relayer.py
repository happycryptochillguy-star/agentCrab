"""Polymarket Builder-Relayer integration for gasless Polygon operations.

Handles Safe deployment and token approvals via Polymarket's relayer.
Users only sign EIP-712 messages — relayer pays Polygon gas.

Two transaction types:
- SAFE-CREATE: Deploy Safe wallet. Agent signs with sign_typed_data().
- SAFE: Execute Safe transaction (approvals). Agent signs with
  sign_message(encode_defunct(hash)), server modifies v (+4) and packs.
"""

import asyncio
import base64
import hashlib
import hmac as hmac_mod
import json
import logging
import time
from functools import partial

from eth_abi import encode as abi_encode
from eth_abi.packed import encode_packed
from eth_utils import to_checksum_address
from web3 import Web3

from api.config import settings
from api.services.http_pool import get_proxy_client
from api.services.payment import derive_safe_address, SAFE_PROXY_FACTORY

logger = logging.getLogger("agentcrab.relayer")

# Constants
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MULTISEND_ADDRESS = "0xA238CBeb142c10Ef7Ad8442C6D1f9E89e07e7761"
POLYGON_CHAIN_ID = 137

# Polymarket contract addresses (Polygon)
POLYGON_USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
POLYGON_CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
POLYGON_CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
POLYGON_NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
POLYGON_NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# Function selectors
APPROVE_SELECTOR = bytes.fromhex("095ea7b3")  # approve(address,uint256)
SET_APPROVAL_SELECTOR = bytes.fromhex("a22cb465")  # setApprovalForAll(address,bool)
MULTISEND_SELECTOR = bytes.fromhex("8d80ff0a")  # multiSend(bytes)

MAX_UINT256 = 2**256 - 1


# ── Builder HMAC Authentication ──


def _build_hmac_signature(
    secret: str, timestamp: str, method: str, path: str, body: str = None,
) -> str:
    """Build HMAC-SHA256 signature for Polymarket Builder auth."""
    key = base64.urlsafe_b64decode(secret)
    message = f"{timestamp}{method}{path}"
    if body:
        message += body
    h = hmac_mod.new(key, message.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode()


def _builder_headers(method: str, path: str, body: str = None) -> dict:
    """Build authentication headers for Polymarket relayer."""
    ts = str(int(time.time()))
    sig = _build_hmac_signature(
        settings.poly_builder_secret, ts, method, path, body,
    )
    return {
        "POLY_BUILDER_API_KEY": settings.poly_builder_api_key,
        "POLY_BUILDER_TIMESTAMP": ts,
        "POLY_BUILDER_PASSPHRASE": settings.poly_builder_passphrase,
        "POLY_BUILDER_SIGNATURE": sig,
    }


# ── Relayer HTTP Client ──


async def _relayer_get(path: str, params: dict = None) -> dict:
    """GET request to relayer (public endpoints, no auth)."""
    url = f"{settings.relayer_url}{path}"
    client = get_proxy_client()
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def _relayer_post(path: str, body: dict) -> dict:
    """POST request to relayer with Builder auth."""
    body_str = json.dumps(body)
    headers = _builder_headers("POST", path, body_str)
    headers["Content-Type"] = "application/json"
    url = f"{settings.relayer_url}{path}"
    client = get_proxy_client()
    resp = await client.post(url, content=body_str, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ── Relayer Queries ──


async def is_safe_deployed(eoa_address: str) -> bool:
    """Check if a Safe is deployed for an EOA."""
    safe = derive_safe_address(eoa_address)
    data = await _relayer_get("/deployed", {"address": safe})
    return data.get("deployed", False)


async def get_safe_nonce(eoa_address: str) -> int:
    """Get the current Safe nonce from relayer."""
    data = await _relayer_get("/nonce", {"address": eoa_address, "type": "SAFE"})
    return int(data.get("nonce", 0))


async def get_transaction(tx_id: str) -> dict:
    """Get transaction status from relayer."""
    return await _relayer_get("/transaction", {"id": tx_id})


async def poll_transaction(
    tx_id: str, max_polls: int = 30, interval: float = 2.0,
) -> dict:
    """Poll relayer until transaction reaches a terminal state."""
    for _ in range(max_polls):
        data = await get_transaction(tx_id)
        # Relayer returns a list of transactions
        tx = data[0] if isinstance(data, list) else data
        state = tx.get("state", "")
        if state in ("STATE_MINED", "STATE_CONFIRMED"):
            return tx
        if state == "STATE_FAILED":
            raise RuntimeError(f"Relayer transaction failed: {tx}")
        await asyncio.sleep(interval)
    raise TimeoutError(f"Transaction {tx_id} did not confirm after {max_polls} polls")


# ── EIP-712 Hash Computation (for SafeTx) ──


def _keccak(data: bytes) -> bytes:
    return Web3.keccak(data)


def _safe_domain_separator(safe_address: str, chain_id: int = POLYGON_CHAIN_ID) -> bytes:
    """Compute EIP-712 domain separator for Gnosis Safe.

    Safe uses: EIP712Domain(uint256 chainId, address verifyingContract)
    """
    type_hash = _keccak(
        b"EIP712Domain(uint256 chainId,address verifyingContract)"
    )
    return _keccak(
        type_hash
        + abi_encode(
            ["uint256", "address"],
            [chain_id, to_checksum_address(safe_address)],
        )
    )


def _safe_tx_struct_hash(
    to: str, value: int, data: bytes, operation: int,
    safe_tx_gas: int, base_gas: int, gas_price: int,
    gas_token: str, refund_receiver: str, nonce: int,
) -> bytes:
    """Compute SafeTx EIP-712 struct hash."""
    type_hash = _keccak(
        b"SafeTx(address to,uint256 value,bytes data,uint8 operation,"
        b"uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,"
        b"address gasToken,address refundReceiver,uint256 nonce)"
    )
    data_hash = _keccak(data) if data else _keccak(b"")
    return _keccak(
        type_hash
        + abi_encode(
            [
                "address", "uint256", "bytes32", "uint8",
                "uint256", "uint256", "uint256",
                "address", "address", "uint256",
            ],
            [
                to_checksum_address(to), value, data_hash, operation,
                safe_tx_gas, base_gas, gas_price,
                to_checksum_address(gas_token),
                to_checksum_address(refund_receiver),
                nonce,
            ],
        )
    )


def compute_safe_tx_hash(
    safe_address: str, to: str, value: int, data: bytes,
    operation: int, nonce: int,
) -> str:
    """Compute the final hash for Safe transaction signing.

    Returns hex hash. Agent signs with:
        Account.sign_message(encode_defunct(HexBytes(hash)))
    """
    domain_sep = _safe_domain_separator(safe_address)
    struct_hash = _safe_tx_struct_hash(
        to=to, value=value, data=data, operation=operation,
        safe_tx_gas=0, base_gas=0, gas_price=0,
        gas_token=ZERO_ADDRESS, refund_receiver=ZERO_ADDRESS,
        nonce=nonce,
    )
    signable = b"\x19\x01" + domain_sep + struct_hash
    return "0x" + _keccak(signable).hex()


# ── Approval CallData & MultiSend Encoding ──


def _encode_approve(spender: str) -> bytes:
    return APPROVE_SELECTOR + abi_encode(
        ["address", "uint256"], [to_checksum_address(spender), MAX_UINT256],
    )


def _encode_set_approval_for_all(operator: str) -> bytes:
    return SET_APPROVAL_SELECTOR + abi_encode(
        ["address", "bool"], [to_checksum_address(operator), True],
    )


def _check_approval_status_sync(safe_address: str) -> dict:
    """Check which token approvals are already set on-chain for a Safe (sync).

    Queries Polygon for USDC.e allowance() and CTF isApprovedForAll().
    Returns {"all_approved": bool, "missing": [...], "approved": [...]}.
    WARNING: Makes 7 sync RPC calls. Always call via check_approval_status (async).
    """
    from api.services.payment import get_polygon_w3

    w3 = get_polygon_w3()
    safe = to_checksum_address(safe_address)

    erc20_abi = [{"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
    erc1155_abi = [{"inputs":[{"name":"account","type":"address"},{"name":"operator","type":"address"}],"name":"isApprovedForAll","outputs":[{"name":"","type":"bool"}],"stateMutability":"view","type":"function"}]

    usdc = w3.eth.contract(address=to_checksum_address(POLYGON_USDC), abi=erc20_abi)
    ctf = w3.eth.contract(address=to_checksum_address(POLYGON_CTF), abi=erc1155_abi)

    # 4 USDC.e allowance checks
    erc20_checks = [
        (POLYGON_CTF, "Approve USDC.e on CTF"),
        (POLYGON_NEG_RISK_ADAPTER, "Approve USDC.e on Neg Risk Adapter"),
        (POLYGON_CTF_EXCHANGE, "Approve USDC.e on CTF Exchange"),
        (POLYGON_NEG_RISK_CTF_EXCHANGE, "Approve USDC.e on Neg Risk CTF Exchange"),
    ]
    # 3 CTF setApprovalForAll checks
    erc1155_checks = [
        (POLYGON_CTF_EXCHANGE, "Approve CTF on CTF Exchange"),
        (POLYGON_NEG_RISK_CTF_EXCHANGE, "Approve CTF on Neg Risk CTF Exchange"),
        (POLYGON_NEG_RISK_ADAPTER, "Approve CTF on Neg Risk Adapter"),
    ]

    approved = []
    missing = []

    for spender, desc in erc20_checks:
        try:
            allowance = usdc.functions.allowance(safe, to_checksum_address(spender)).call()
            if allowance > 0:
                approved.append(desc)
            else:
                missing.append(desc)
        except Exception:
            missing.append(desc)

    for operator, desc in erc1155_checks:
        try:
            is_approved = ctf.functions.isApprovedForAll(safe, to_checksum_address(operator)).call()
            if is_approved:
                approved.append(desc)
            else:
                missing.append(desc)
        except Exception:
            missing.append(desc)

    return {
        "all_approved": len(missing) == 0,
        "approved": approved,
        "missing": missing,
    }


async def check_approval_status(safe_address: str) -> dict:
    """Check approval status without blocking the event loop."""
    return await asyncio.to_thread(_check_approval_status_sync, safe_address)


def _build_approval_calls(only_missing: list[str] | None = None) -> list[dict]:
    """Build approval calls needed for Polymarket trading.

    If only_missing is provided, only include calls whose desc is in that list.
    """
    all_calls = [
        # USDC.e approve (4 spenders)
        {"to": POLYGON_USDC, "data": _encode_approve(POLYGON_CTF),
         "desc": "Approve USDC.e on CTF"},
        {"to": POLYGON_USDC, "data": _encode_approve(POLYGON_NEG_RISK_ADAPTER),
         "desc": "Approve USDC.e on Neg Risk Adapter"},
        {"to": POLYGON_USDC, "data": _encode_approve(POLYGON_CTF_EXCHANGE),
         "desc": "Approve USDC.e on CTF Exchange"},
        {"to": POLYGON_USDC, "data": _encode_approve(POLYGON_NEG_RISK_CTF_EXCHANGE),
         "desc": "Approve USDC.e on Neg Risk CTF Exchange"},
        # CTF setApprovalForAll (3 operators)
        {"to": POLYGON_CTF, "data": _encode_set_approval_for_all(POLYGON_CTF_EXCHANGE),
         "desc": "Approve CTF on CTF Exchange"},
        {"to": POLYGON_CTF, "data": _encode_set_approval_for_all(POLYGON_NEG_RISK_CTF_EXCHANGE),
         "desc": "Approve CTF on Neg Risk CTF Exchange"},
        {"to": POLYGON_CTF, "data": _encode_set_approval_for_all(POLYGON_NEG_RISK_ADAPTER),
         "desc": "Approve CTF on Neg Risk Adapter"},
    ]
    if only_missing is not None:
        return [c for c in all_calls if c["desc"] in only_missing]
    return all_calls


def _encode_multisend(calls: list[dict]) -> bytes:
    """Encode multiple calls into a MultiSend transaction."""
    packed_txns = []
    for call in calls:
        data_bytes = call["data"]
        packed = encode_packed(
            ["uint8", "address", "uint256", "uint256", "bytes"],
            [0, to_checksum_address(call["to"]), 0, len(data_bytes), data_bytes],
        )
        packed_txns.append(packed)

    concatenated = b"".join(packed_txns)
    multisend_data = abi_encode(["bytes"], [concatenated])
    return MULTISEND_SELECTOR + multisend_data


# ── Signature Processing ──


def pack_safe_signature(signature_hex: str) -> str:
    """Pack a signature with v+4 for Safe eth_sign type.

    Safe contracts expect v=31/32 for eth_sign signatures (instead of 27/28).
    This tells the Safe that the hash was prefixed with
    '\\x19Ethereum Signed Message:\\n32' before signing.
    """
    sig_bytes = bytes.fromhex(signature_hex.removeprefix("0x"))
    if len(sig_bytes) != 65:
        raise ValueError(f"Invalid signature length: {len(sig_bytes)}")

    r = int.from_bytes(sig_bytes[0:32], "big")
    s = int.from_bytes(sig_bytes[32:64], "big")
    v = sig_bytes[64]

    if v in (0, 1):
        v += 31
    elif v in (27, 28):
        v += 4
    else:
        raise ValueError(f"Invalid signature v value: {v}")

    packed = encode_packed(["uint256", "uint256", "uint8"], [r, s, v])
    return "0x" + packed.hex()


# ── High-Level Operations ──


def build_create_proxy_typed_data() -> dict:
    """Build EIP-712 typed data for Safe deployment (SAFE-CREATE).

    Agent signs with Account.sign_typed_data(domain, types, message).
    """
    return {
        "domain": {
            "name": "Polymarket Contract Proxy Factory",
            "verifyingContract": SAFE_PROXY_FACTORY,
            "chainId": POLYGON_CHAIN_ID,
        },
        "types": {
            "CreateProxy": [
                {"name": "paymentToken", "type": "address"},
                {"name": "payment", "type": "uint256"},
                {"name": "paymentReceiver", "type": "address"},
            ],
        },
        "primaryType": "CreateProxy",
        "message": {
            "paymentToken": ZERO_ADDRESS,
            "payment": 0,
            "paymentReceiver": ZERO_ADDRESS,
        },
    }


async def deploy_safe(eoa_address: str, signature: str) -> dict:
    """Submit SAFE-CREATE to relayer. Returns relayer response."""
    safe_address = derive_safe_address(eoa_address)
    request = {
        "type": "SAFE-CREATE",
        "from": to_checksum_address(eoa_address),
        "to": to_checksum_address(SAFE_PROXY_FACTORY),
        "proxyWallet": to_checksum_address(safe_address),
        "data": "0x",
        "signature": signature,
        "signatureParams": {
            "paymentToken": ZERO_ADDRESS,
            "payment": "0",
            "paymentReceiver": ZERO_ADDRESS,
        },
    }
    return await _relayer_post("/submit", request)


async def build_approval_data(eoa_address: str, only_missing: list[str] | None = None) -> dict:
    """Build the SafeTx hash for approval transactions.

    If only_missing is provided, only includes those specific approvals.
    Returns hash + metadata. Agent signs the hash with:
        Account.sign_message(encode_defunct(HexBytes(hash)))
    """
    safe_address = derive_safe_address(eoa_address)
    nonce = await get_safe_nonce(eoa_address)

    calls = _build_approval_calls(only_missing=only_missing)
    if not calls:
        return None
    multisend_data = _encode_multisend(calls)

    tx_hash = compute_safe_tx_hash(
        safe_address=safe_address,
        to=MULTISEND_ADDRESS,
        value=0,
        data=multisend_data,
        operation=1,  # DelegateCall for MultiSend
        nonce=nonce,
    )

    return {
        "hash": tx_hash,
        "safe_address": safe_address,
        "nonce": nonce,
        "to": MULTISEND_ADDRESS,
        "data": "0x" + multisend_data.hex(),
        "operation": 1,
        "approvals": [c["desc"] for c in calls],
    }


async def submit_approvals(eoa_address: str, signature: str, approval_data: dict) -> dict:
    """Submit Safe approval transaction to relayer.

    Takes the personal_sign signature, applies v+4, and submits.
    """
    packed_sig = pack_safe_signature(signature)
    safe_address = derive_safe_address(eoa_address)

    request = {
        "type": "SAFE",
        "from": to_checksum_address(eoa_address),
        "to": approval_data["to"],
        "proxyWallet": to_checksum_address(safe_address),
        "data": approval_data["data"],
        "value": "0",
        "signature": packed_sig,
        "signatureParams": {
            "gasPrice": "0",
            "operation": str(approval_data["operation"]),
            "safeTxnGas": "0",
            "baseGas": "0",
            "gasToken": ZERO_ADDRESS,
            "refundReceiver": ZERO_ADDRESS,
        },
        "nonce": str(approval_data["nonce"]),
    }
    return await _relayer_post("/submit", request)
