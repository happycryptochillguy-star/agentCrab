import asyncio
import json
import logging
import re
import threading
import time

from eth_abi import encode as abi_encode
from eth_account.messages import encode_defunct
from web3 import Web3

from api.config import settings
from api.services import balance as balance_svc

# Thread lock for web3 RPC calls — web3.py's HTTPProvider uses requests.Session
# which is NOT thread-safe. All to_thread() calls sharing global singletons
# must serialize through this lock.
_w3_lock = threading.Lock()

_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

logger = logging.getLogger("agentcrab.payment")

# === Signature Replay Prevention ===
# Persisted in SQLite (balance.py used_signatures table).
# Survives restarts and works across multiple workers.
_SIG_CLEANUP_INTERVAL = 300  # seconds
_sig_last_cleanup = 0.0

# ABI fragments we need
PAYMENT_ABI = json.loads("""[
    {"anonymous":false,"inputs":[{"indexed":true,"name":"user","type":"address"},{"indexed":false,"name":"amount","type":"uint256"}],"name":"Deposited","type":"event"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"user","type":"address"},{"indexed":false,"name":"amount","type":"uint256"}],"name":"DirectPayment","type":"event"},
    {"inputs":[{"name":"user","type":"address"}],"name":"getBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"user","type":"address"}],"name":"getDirectPaymentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"amount","type":"uint256"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"pay","outputs":[],"stateMutability":"nonpayable","type":"function"}
]""")

USDT_ABI = json.loads("""[
    {"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]""")

_w3: Web3 | None = None
_polygon_w3: Web3 | None = None
_contract = None
_usdt_contract = None

BSC_CHAIN_ID = 56
POLYGON_CHAIN_ID = 137

# Polymarket Polygon contract addresses
POLYGON_CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
POLYGON_CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
POLYGON_NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
POLYGON_NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# ABI for Polygon approvals
ERC20_APPROVE_ABI = json.loads('[{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]')
ERC1155_APPROVE_ABI = json.loads('[{"inputs":[{"name":"operator","type":"address"},{"name":"approved","type":"bool"}],"name":"setApprovalForAll","outputs":[],"stateMutability":"nonpayable","type":"function"}]')



def _no_proxy_provider(rpc_url: str) -> Web3.HTTPProvider:
    """Create an HTTPProvider that bypasses system proxy (HTTPS_PROXY env var).
    Blockchain RPCs (BSC, Polygon) are not geo-blocked and should connect directly."""
    return Web3.HTTPProvider(rpc_url, request_kwargs={"proxies": {"http": "", "https": ""}})


def get_w3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(_no_proxy_provider(settings.bsc_rpc_url))
    return _w3


def get_polygon_w3() -> Web3:
    global _polygon_w3
    if _polygon_w3 is None:
        _polygon_w3 = Web3(_no_proxy_provider(settings.polygon_rpc_url))
    return _polygon_w3


def get_contract():
    global _contract
    if _contract is None:
        w3 = get_w3()
        _contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.contract_address),
            abi=PAYMENT_ABI,
        )
    return _contract


def get_usdt_contract():
    global _usdt_contract
    if _usdt_contract is None:
        w3 = get_w3()
        _usdt_contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.usdt_address),
            abi=USDT_ABI,
        )
    return _usdt_contract


def is_valid_address(address: str) -> bool:
    """Check if a string is a valid Ethereum address."""
    return bool(_ETH_ADDRESS_RE.match(address))


async def verify_signature(wallet_address: str, message: str, signature: str) -> bool:
    """Verify EIP-191 personal_sign. Message format: 'agentcrab:{unix_timestamp}'.

    Includes replay prevention: each signature can only be used once.
    Replay state persisted in SQLite (survives restarts, works across workers).
    """
    global _sig_last_cleanup
    try:
        if not is_valid_address(wallet_address):
            return False
        # Check timestamp freshness
        parts = message.split(":")
        if len(parts) != 2 or parts[0] != "agentcrab":
            return False

        ts = int(parts[1])
        now = time.time()
        if abs(now - ts) > settings.signature_max_age_seconds:
            return False

        # Recover signer (CPU-only, no RPC)
        w3 = get_w3()
        msg = encode_defunct(text=message)
        recovered = w3.eth.account.recover_message(msg, signature=signature)
        if recovered.lower() != wallet_address.lower():
            return False

        # Replay check: atomically claim this signature in SQLite.
        # TOCTOU-safe (single INSERT with UNIQUE constraint).
        # Persists across restarts. Works across multiple workers.
        expires_at = ts + settings.signature_max_age_seconds
        claimed = await balance_svc.try_claim_signature(signature, expires_at)
        if not claimed:
            logger.warning("Rejected replayed signature from %s", wallet_address[:10])
            return False

        # Periodic cleanup of expired signatures
        if now - _sig_last_cleanup > _SIG_CLEANUP_INTERVAL:
            _sig_last_cleanup = now
            await balance_svc.cleanup_expired_signatures()

        return True
    except Exception as e:
        logger.warning("Signature verification failed: %s", e)
        return False


def _verify_direct_payment_sync(tx_hash: str, wallet_address: str) -> bool:
    """Sync part of direct payment verification (RPC calls).
    Checks that DirectPayment event exists, is from the correct wallet,
    and the amount is >= the required payment amount."""
    w3 = get_w3()
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    if receipt is None or receipt["status"] != 1:
        return False

    contract = get_contract()
    logs = contract.events.DirectPayment().process_receipt(receipt)
    for log in logs:
        if (
            log["args"]["user"].lower() == wallet_address.lower()
            and log["args"]["amount"] >= settings.payment_amount_wei
        ):
            return True
    return False


async def verify_direct_payment(tx_hash: str, wallet_address: str) -> bool:
    """Verify a DirectPayment event in a BSC transaction receipt. Rejects replayed tx hashes.

    Uses atomic tx hash claiming (try_claim_tx_hash) to prevent TOCTOU double-spend:
    1. Atomically claim the tx hash (INSERT with UNIQUE constraint)
    2. If claimed, verify on-chain
    3. If verification fails, release the claim
    """
    try:
        # Atomically claim tx hash — prevents concurrent double-spend
        claimed = await balance_svc.try_claim_tx_hash(tx_hash, wallet_address)
        if not claimed:
            logger.warning("Rejected replayed tx hash: %s", tx_hash)
            return False

        result = await asyncio.to_thread(
            _locked, _verify_direct_payment_sync, tx_hash, wallet_address
        )
        if result is True:
            return True

        # Verification failed — release the claim so user can retry with correct tx
        # (This is safe: the tx was invalid, so no double-spend risk)
        logger.info("Releasing claimed tx hash %s (verification failed)", tx_hash[:10])
        db = await balance_svc.get_db()
        async with balance_svc._write_lock:
            await db.execute(
                "DELETE FROM used_tx_hashes WHERE tx_hash = ?", (tx_hash.lower(),)
            )
            await db.commit()
        return False
    except Exception as e:
        # Release the claim so user can retry — verification never completed
        logger.warning("Direct payment verification failed (releasing claim): %s", e)
        try:
            db = await balance_svc.get_db()
            async with balance_svc._write_lock:
                await db.execute(
                    "DELETE FROM used_tx_hashes WHERE tx_hash = ?", (tx_hash.lower(),)
                )
                await db.commit()
        except Exception:
            pass  # Best effort — don't mask the original error
        return False


def _get_on_chain_balance(wallet_address: str) -> int:
    """Sync RPC call to get on-chain balance."""
    contract = get_contract()
    return contract.functions.getBalance(
        Web3.to_checksum_address(wallet_address)
    ).call()


async def sync_balance(wallet_address: str):
    """Sync on-chain deposit balance to off-chain DB for a single wallet.

    Uses atomic MAX(total_deposited, on_chain) to prevent TOCTOU double-credit:
    concurrent calls for the same wallet are safe because MAX is idempotent.
    """
    try:
        on_chain = await asyncio.to_thread(_locked, _get_on_chain_balance, wallet_address)
        if on_chain <= 0:
            return

        addr = wallet_address.lower()
        db = await balance_svc.get_db()
        async with balance_svc._write_lock:
            cursor = await db.execute(
                "SELECT total_deposited FROM balances WHERE wallet_address = ?",
                (addr,),
            )
            row = await cursor.fetchone()
            local_deposited = row[0] if row else 0

            if on_chain > local_deposited:
                logger.info(
                    "Balance sync: %s on-chain=%s local=%s crediting=%s",
                    addr[:10], on_chain, local_deposited, on_chain - local_deposited,
                )
                await db.execute("""
                    INSERT INTO balances (wallet_address, total_deposited, total_consumed)
                    VALUES (?, ?, 0)
                    ON CONFLICT(wallet_address)
                    DO UPDATE SET total_deposited = MAX(total_deposited, ?)
                """, (addr, on_chain, on_chain))
                await db.commit()
    except Exception as e:
        logger.warning("Balance sync failed for %s: %s", wallet_address[:10], e)


# === Balance Cache (avoid BSC RPC on every paid request) ===

_balance_cache: dict[str, tuple[int, float]] = {}  # addr -> (remaining_wei, timestamp)
_BALANCE_CACHE_TTL = 30  # seconds
_balance_locks: dict[str, asyncio.Lock] = {}  # per-wallet lock to prevent double-credit
_MAX_BALANCE_LOCKS = 500  # evict stale locks to prevent unbounded growth


def _get_balance_lock(addr: str) -> asyncio.Lock:
    """Get or create a per-wallet lock for balance operations."""
    if addr not in _balance_locks:
        # Evict oldest entries if we have too many
        if len(_balance_locks) >= _MAX_BALANCE_LOCKS:
            # Remove half the entries (arbitrary eviction — all Locks are equivalent)
            to_remove = list(_balance_locks.keys())[: _MAX_BALANCE_LOCKS // 2]
            for k in to_remove:
                _balance_locks.pop(k, None)
        _balance_locks[addr] = asyncio.Lock()
    return _balance_locks[addr]


async def check_prepaid_balance(wallet_address: str) -> int:
    """Get remaining prepaid balance, with 30s cache to reduce BSC RPC calls.

    Cache is invalidated on consume() (deduction) to ensure correctness.
    On-chain sync only happens when cache is stale.
    Per-wallet lock prevents concurrent syncs from double-crediting deposits.
    """
    addr = wallet_address.lower()
    now = time.time()

    cached = _balance_cache.get(addr)
    if cached and (now - cached[1]) < _BALANCE_CACHE_TTL:
        return cached[0]

    async with _get_balance_lock(addr):
        # Re-check cache inside lock (another coroutine may have just refreshed)
        cached = _balance_cache.get(addr)
        if cached and (now - cached[1]) < _BALANCE_CACHE_TTL:
            return cached[0]

        await sync_balance(wallet_address)
        _, _, remaining = await balance_svc.get_remaining(wallet_address)
        _balance_cache[addr] = (remaining, time.time())
        return remaining


def invalidate_balance_cache(wallet_address: str):
    """Invalidate cached balance after a deduction."""
    _balance_cache.pop(wallet_address.lower(), None)


# === Transaction Builder (server-side) ===


def build_deposit_txs(wallet_address: str, amount_wei: int) -> list[dict]:
    """Build unsigned approve + deposit transactions for the agent to sign.

    Returns a list of transaction dicts ready for eth_account.sign_transaction().
    Skips approve if allowance is already sufficient.
    """
    w3 = get_w3()
    wallet = Web3.to_checksum_address(wallet_address)
    contract_addr = Web3.to_checksum_address(settings.contract_address)
    usdt = get_usdt_contract()
    contract = get_contract()
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    txs = []

    # Check if approve is needed
    current_allowance = usdt.functions.allowance(wallet, contract_addr).call()
    if current_allowance < amount_wei:
        approve_tx = usdt.functions.approve(
            contract_addr, amount_wei
        ).build_transaction({
            "from": wallet,
            "nonce": nonce,
            "gas": 60000,
            "gasPrice": gas_price,
            "chainId": BSC_CHAIN_ID,
        })
        txs.append({"step": "approve", "description": "Approve USDT spending", "transaction": approve_tx})
        nonce += 1

    deposit_tx = contract.functions.deposit(
        amount_wei
    ).build_transaction({
        "from": wallet,
        "nonce": nonce,
        "gas": 120000,
        "gasPrice": gas_price,
        "chainId": BSC_CHAIN_ID,
    })
    txs.append({"step": "deposit", "description": "Deposit to agentCrab", "transaction": deposit_tx})

    return txs


def build_pay_tx(wallet_address: str) -> list[dict]:
    """Build unsigned approve + pay() transactions for direct per-call payment."""
    w3 = get_w3()
    wallet = Web3.to_checksum_address(wallet_address)
    contract_addr = Web3.to_checksum_address(settings.contract_address)
    usdt = get_usdt_contract()
    contract = get_contract()
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price
    amount = settings.payment_amount_wei

    txs = []

    current_allowance = usdt.functions.allowance(wallet, contract_addr).call()
    if current_allowance < amount:
        # Approve 100x to avoid repeating
        approve_tx = usdt.functions.approve(
            contract_addr, amount * 100
        ).build_transaction({
            "from": wallet,
            "nonce": nonce,
            "gas": 60000,
            "gasPrice": gas_price,
            "chainId": BSC_CHAIN_ID,
        })
        txs.append({"step": "approve", "description": "Approve USDT spending", "transaction": approve_tx})
        nonce += 1

    pay_tx = contract.functions.pay().build_transaction({
        "from": wallet,
        "nonce": nonce,
        "gas": 120000,
        "gasPrice": gas_price,
        "chainId": BSC_CHAIN_ID,
    })
    txs.append({"step": "pay", "description": "Pay 0.01 USDT", "transaction": pay_tx})

    return txs


def build_usdt_transfer_tx(wallet_address: str, to_address: str, amount_wei: int) -> list[dict]:
    """Build an unsigned USDT transfer transaction on BSC."""
    w3 = get_w3()
    wallet = Web3.to_checksum_address(wallet_address)
    to_addr = Web3.to_checksum_address(to_address)
    usdt = get_usdt_contract()
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    transfer_tx = usdt.functions.transfer(
        to_addr, amount_wei
    ).build_transaction({
        "from": wallet,
        "nonce": nonce,
        "gas": 60000,
        "gasPrice": gas_price,
        "chainId": BSC_CHAIN_ID,
    })

    return [{"step": "transfer", "description": f"Transfer USDT to {to_address[:10]}...", "transaction": transfer_tx}]


def build_polygon_approval_txs(wallet_address: str) -> list[dict]:
    """Build unsigned Polygon transactions for Polymarket trading approvals.

    Includes USDC.e approve + CTF setApprovalForAll on all exchange contracts.
    """
    w3 = get_polygon_w3()
    wallet = Web3.to_checksum_address(wallet_address)
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price
    usdc_addr = Web3.to_checksum_address(settings.polygon_usdc_address)

    txs = []
    max_uint256 = 2**256 - 1

    # USDC.e approve on CTF Exchange
    usdc = w3.eth.contract(address=usdc_addr, abi=ERC20_APPROVE_ABI)
    for spender, name in [
        (POLYGON_CTF_EXCHANGE, "CTF Exchange"),
        (POLYGON_NEG_RISK_CTF_EXCHANGE, "Neg Risk CTF Exchange"),
    ]:
        tx = usdc.functions.approve(
            Web3.to_checksum_address(spender), max_uint256
        ).build_transaction({
            "from": wallet, "nonce": nonce,
            "gas": 60000, "gasPrice": gas_price,
            "chainId": POLYGON_CHAIN_ID,
        })
        txs.append({"step": f"approve_usdc_{name.lower().replace(' ', '_')}",
                     "description": f"Approve USDC.e on {name}",
                     "transaction": tx})
        nonce += 1

    # CTF setApprovalForAll on exchange contracts
    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(POLYGON_CTF), abi=ERC1155_APPROVE_ABI
    )
    for spender, name in [
        (POLYGON_CTF_EXCHANGE, "CTF Exchange"),
        (POLYGON_NEG_RISK_CTF_EXCHANGE, "Neg Risk CTF Exchange"),
        (POLYGON_NEG_RISK_ADAPTER, "Neg Risk Adapter"),
    ]:
        tx = ctf.functions.setApprovalForAll(
            Web3.to_checksum_address(spender), True
        ).build_transaction({
            "from": wallet, "nonce": nonce,
            "gas": 60000, "gasPrice": gas_price,
            "chainId": POLYGON_CHAIN_ID,
        })
        txs.append({"step": f"approve_ctf_{name.lower().replace(' ', '_')}",
                     "description": f"Approve CTF on {name}",
                     "transaction": tx})
        nonce += 1

    return txs


# === Safe (Polymarket proxy wallet) ===

# Polymarket SafeProxyFactory on Polygon
SAFE_PROXY_FACTORY = "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b"
SAFE_INIT_CODE_HASH = bytes.fromhex(
    "2bce2127ff07fb632d16c8347c4ebf501f4841168bed00d9e6ef715ddb6fcecf"
)


def derive_safe_address(eoa_address: str) -> str:
    """Derive the Polymarket Safe proxy wallet address for an EOA via CREATE2.

    Polymarket deploys a Gnosis Safe for each user. The address is deterministic:
      addr = CREATE2(factory, salt, init_code_hash)
    where salt = keccak256(abi.encode(["address"], [eoa]))

    Uses eth_abi.encode for proper ABI encoding (left-pads address to 32 bytes),
    NOT solidity_keccak which uses abi.encodePacked (20 bytes, no padding).
    """
    eoa = Web3.to_checksum_address(eoa_address)
    # salt = keccak256(abi.encode(["address"], [eoa]))  — ABI-padded to 32 bytes
    salt = Web3.keccak(abi_encode(["address"], [eoa]))
    # CREATE2: keccak256(0xff ++ factory ++ salt ++ init_code_hash)[12:]
    factory_bytes = bytes.fromhex(SAFE_PROXY_FACTORY[2:])
    raw = b"\xff" + factory_bytes + salt + SAFE_INIT_CODE_HASH
    addr_bytes = Web3.keccak(raw)[12:]
    return Web3.to_checksum_address(addr_bytes)


def _get_polygon_usdc_balance_sync(address: str) -> int:
    """Get USDC.e balance on Polygon (sync RPC call)."""
    w3 = get_polygon_w3()
    usdc_addr = Web3.to_checksum_address(settings.polygon_usdc_address)
    usdc = w3.eth.contract(address=usdc_addr, abi=USDT_ABI)  # same ERC20 ABI
    return usdc.functions.balanceOf(Web3.to_checksum_address(address)).call()


def get_polygon_usdc_balance(address: str) -> int:
    """Get USDC.e balance on Polygon (sync). Use get_polygon_usdc_balance_async for non-blocking."""
    return _get_polygon_usdc_balance_sync(address)


async def get_polygon_usdc_balance_async(address: str) -> int:
    """Get USDC.e balance on Polygon without blocking the event loop."""
    return await asyncio.to_thread(_locked, _get_polygon_usdc_balance_sync, address)


def build_polygon_usdc_transfer_tx(
    wallet_address: str, to_address: str, amount_wei: int
) -> list[dict]:
    """Build unsigned USDC.e transfer tx on Polygon (EOA → Safe)."""
    w3 = get_polygon_w3()
    wallet = Web3.to_checksum_address(wallet_address)
    to_addr = Web3.to_checksum_address(to_address)
    usdc_addr = Web3.to_checksum_address(settings.polygon_usdc_address)
    usdc = w3.eth.contract(address=usdc_addr, abi=USDT_ABI)

    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    transfer_tx = usdc.functions.transfer(
        to_addr, amount_wei
    ).build_transaction({
        "from": wallet,
        "nonce": nonce,
        "gas": 60000,
        "gasPrice": gas_price,
        "chainId": POLYGON_CHAIN_ID,
    })

    return [{
        "step": "transfer_usdc_e",
        "description": f"Transfer USDC.e to Safe {to_address[:10]}...",
        "transaction": transfer_tx,
    }]


# === Transaction Target Whitelist ===
# Only allow broadcasting transactions to known contracts.
# Prevents abuse of our RPC endpoint as a free relay.

# BSC deposit contract (Polymarket via fun.xyz)
BSC_DEPOSIT_CONTRACT = "0x4cD00E387622C35bDDB9b4c962C136462338BC31"

_BSC_WHITELIST: set[str] | None = None
_POLYGON_WHITELIST: set[str] = {
    w.lower() for w in [
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
        POLYGON_CTF,
        POLYGON_CTF_EXCHANGE,
        POLYGON_NEG_RISK_CTF_EXCHANGE,
        POLYGON_NEG_RISK_ADAPTER,
        "0xA238CBeb142c10Ef7Ad8442C6D1f9E89e07e7761",  # MultiSend
        "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b",  # SafeProxyFactory
    ]
}


def _get_bsc_whitelist() -> set[str]:
    """Lazily build BSC whitelist (needs settings loaded)."""
    global _BSC_WHITELIST
    if _BSC_WHITELIST is None:
        _BSC_WHITELIST = {
            w.lower() for w in [
                settings.contract_address,  # agentCrab payment contract
                settings.usdt_address,       # BSC USDT
                BSC_DEPOSIT_CONTRACT,        # Polymarket deposit via fun.xyz
            ] if w
        }
    return _BSC_WHITELIST


def extract_to_from_raw_tx(raw_hex: str) -> str | None:
    """Extract the 'to' address from a signed raw transaction.

    Supports legacy, EIP-2930 (type 1), and EIP-1559 (type 2) transactions.
    """
    import rlp
    try:
        raw = bytes.fromhex(raw_hex.removeprefix("0x"))
        if raw[0] <= 0x7f:
            # EIP-2718 typed transaction
            payload = rlp.decode(raw[1:])
            if raw[0] == 0x01:
                to_bytes = payload[4]  # EIP-2930
            elif raw[0] == 0x02:
                to_bytes = payload[5]  # EIP-1559
            else:
                return None
        else:
            # Legacy transaction
            payload = rlp.decode(raw)
            to_bytes = payload[3]

        if not to_bytes or len(to_bytes) != 20:
            return None
        return "0x" + to_bytes.hex()
    except Exception:
        return None


def validate_tx_target(raw_hex: str, chain: str) -> bool:
    """Check if a raw transaction targets a whitelisted contract."""
    to_addr = extract_to_from_raw_tx(raw_hex)
    if to_addr is None:
        return False
    to_lower = to_addr.lower()
    if chain == "polygon":
        return to_lower in _POLYGON_WHITELIST
    return to_lower in _get_bsc_whitelist()


def _broadcast_signed_tx_sync(signed_raw_tx: str, chain: str = "bsc") -> str:
    """Broadcast a signed transaction (sync). Returns the tx hash hex.
    WARNING: Blocks up to 60s waiting for receipt. Always call via to_thread.
    """
    w3 = get_polygon_w3() if chain == "polygon" else get_w3()
    tx_hash = w3.eth.send_raw_transaction(bytes.fromhex(
        signed_raw_tx.removeprefix("0x")
    ))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt["status"] != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex()


def _broadcast_signed_txs_sync(signed_raw_txs: list[str], chain: str = "bsc") -> list[str]:
    """Broadcast multiple signed transactions in order (sync).
    WARNING: Blocks. Always call via to_thread.
    """
    hashes = []
    for i, raw_tx in enumerate(signed_raw_txs):
        try:
            tx_hash = _broadcast_signed_tx_sync(raw_tx, chain=chain)
            hashes.append(tx_hash)
            logger.info("Batch tx %d/%d confirmed: %s", i + 1, len(signed_raw_txs), tx_hash)
        except Exception as e:
            raise RuntimeError(
                f"Transaction {i + 1}/{len(signed_raw_txs)} failed: {e}. "
                f"Completed: {hashes}"
            )
    return hashes


async def broadcast_signed_tx(signed_raw_tx: str, chain: str = "bsc") -> str:
    """Broadcast a signed transaction without blocking the event loop."""
    return await asyncio.to_thread(_locked, _broadcast_signed_tx_sync, signed_raw_tx, chain)


async def broadcast_signed_txs(signed_raw_txs: list[str], chain: str = "bsc") -> list[str]:
    """Broadcast multiple signed transactions without blocking the event loop."""
    return await asyncio.to_thread(_locked, _broadcast_signed_txs_sync, signed_raw_txs, chain)


# === Async wrappers for tx builders (they make sync RPC calls) ===


def _locked(fn, *args, **kwargs):
    """Run a synchronous function holding the web3 thread lock."""
    with _w3_lock:
        return fn(*args, **kwargs)


async def build_deposit_txs_async(wallet_address: str, amount_wei: int) -> list[dict]:
    """Non-blocking wrapper for build_deposit_txs."""
    return await asyncio.to_thread(_locked, build_deposit_txs, wallet_address, amount_wei)


async def build_pay_tx_async(wallet_address: str) -> list[dict]:
    """Non-blocking wrapper for build_pay_tx."""
    return await asyncio.to_thread(_locked, build_pay_tx, wallet_address)


async def build_usdt_transfer_tx_async(wallet_address: str, to_address: str, amount_wei: int) -> list[dict]:
    """Non-blocking wrapper for build_usdt_transfer_tx."""
    return await asyncio.to_thread(_locked, build_usdt_transfer_tx, wallet_address, to_address, amount_wei)


async def build_polygon_approval_txs_async(wallet_address: str) -> list[dict]:
    """Non-blocking wrapper for build_polygon_approval_txs."""
    return await asyncio.to_thread(_locked, build_polygon_approval_txs, wallet_address)


async def build_polygon_usdc_transfer_tx_async(
    wallet_address: str, to_address: str, amount_wei: int,
) -> list[dict]:
    """Non-blocking wrapper for build_polygon_usdc_transfer_tx."""
    return await asyncio.to_thread(_locked, build_polygon_usdc_transfer_tx, wallet_address, to_address, amount_wei)
