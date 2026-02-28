import asyncio
import json
import logging
import time

from eth_account.messages import encode_defunct
from web3 import Web3

from api.config import settings
from api.services import balance as balance_svc

logger = logging.getLogger("agentway.payment")

# ABI fragments we need
PAYMENT_ABI = json.loads("""[
    {"anonymous":false,"inputs":[{"indexed":true,"name":"user","type":"address"},{"indexed":false,"name":"amount","type":"uint256"}],"name":"Deposited","type":"event"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"user","type":"address"},{"indexed":false,"name":"amount","type":"uint256"}],"name":"DirectPayment","type":"event"},
    {"inputs":[{"name":"user","type":"address"}],"name":"getBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"user","type":"address"}],"name":"getDirectPaymentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]""")

_w3: Web3 | None = None
_contract = None


def get_w3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(settings.bsc_rpc_url))
    return _w3


def get_contract():
    global _contract
    if _contract is None:
        w3 = get_w3()
        _contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.contract_address),
            abi=PAYMENT_ABI,
        )
    return _contract


def verify_signature(wallet_address: str, message: str, signature: str) -> bool:
    """Verify EIP-191 personal_sign. Message format: 'agentway:{unix_timestamp}'."""
    try:
        # Check timestamp freshness
        parts = message.split(":")
        if len(parts) != 2 or parts[0] != "agentway":
            return False

        ts = int(parts[1])
        if abs(time.time() - ts) > settings.signature_max_age_seconds:
            return False

        # Recover signer
        w3 = get_w3()
        msg = encode_defunct(text=message)
        recovered = w3.eth.account.recover_message(msg, signature=signature)
        return recovered.lower() == wallet_address.lower()
    except Exception as e:
        logger.warning("Signature verification failed: %s", e)
        return False


async def verify_direct_payment(tx_hash: str, wallet_address: str) -> bool:
    """Verify a DirectPayment event in a BSC transaction receipt."""
    try:
        w3 = get_w3()
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt is None or receipt["status"] != 1:
            return False

        contract = get_contract()
        logs = contract.events.DirectPayment().process_receipt(receipt)
        for log in logs:
            if log["args"]["user"].lower() == wallet_address.lower():
                return True
        return False
    except Exception as e:
        logger.warning("Direct payment verification failed: %s", e)
        return False


async def check_prepaid_balance(wallet_address: str) -> int:
    """Get remaining prepaid balance from off-chain DB (in wei)."""
    _, _, remaining = await balance_svc.get_remaining(wallet_address)
    return remaining


# === Background Deposit Scanner ===

_last_scanned_block: int = 0


async def scan_deposits():
    """Poll for Deposited events and credit to off-chain balance."""
    global _last_scanned_block

    try:
        w3 = get_w3()
        contract = get_contract()

        current_block = w3.eth.block_number
        if _last_scanned_block == 0:
            # Start scanning from ~1000 blocks back on first run
            _last_scanned_block = max(current_block - 1000, 0)

        if current_block <= _last_scanned_block:
            return

        # Scan in chunks to avoid RPC limits
        chunk_size = 500
        from_block = _last_scanned_block + 1
        to_block = min(from_block + chunk_size - 1, current_block)

        events = contract.events.Deposited().get_logs(
            fromBlock=from_block, toBlock=to_block
        )

        for event in events:
            user = event["args"]["user"]
            amount = event["args"]["amount"]
            logger.info("Deposit detected: %s deposited %s wei", user, amount)
            await balance_svc.credit_deposit(user, amount)

        _last_scanned_block = to_block

    except Exception as e:
        logger.error("Deposit scanner error: %s", e)


async def deposit_scanner_loop():
    """Background loop that polls for deposits."""
    while True:
        await scan_deposits()
        await asyncio.sleep(settings.scanner_interval_seconds)
