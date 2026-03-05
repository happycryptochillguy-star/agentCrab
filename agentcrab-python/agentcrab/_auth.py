"""EIP-191 authentication header building."""

import os
import time

from eth_account import Account
from eth_account.messages import encode_defunct

# Monotonic counter to avoid signature collisions within the same second.
# When the server supports nonce-based messages (v0.4+), this is not needed.
_last_ts: int = 0


def build_auth_headers(
    private_key: str,
    address: str,
    payment_mode: str = "prepaid",
) -> dict[str, str]:
    """Build authentication headers for API requests.

    Signs ``agentcrab:{unix_timestamp}`` with EIP-191 personal_sign.
    Waits if the timestamp hasn't advanced to avoid signature replay rejection.
    """
    global _last_ts
    ts = int(time.time())
    if ts <= _last_ts:
        # Wait for the next second to guarantee a unique signature
        time.sleep(_last_ts - ts + 1)
        ts = int(time.time())
    _last_ts = ts

    message = f"agentcrab:{ts}"
    sig = Account.sign_message(
        encode_defunct(text=message),
        private_key=private_key,
    )
    headers = {
        "X-Wallet-Address": address,
        "X-Signature": "0x" + sig.signature.hex(),
        "X-Message": message,
        "X-Payment-Mode": payment_mode,
    }
    return headers


def build_l2_headers(api_key: str, secret: str, passphrase: str) -> dict[str, str]:
    """Build Polymarket L2 credential headers."""
    return {
        "X-Poly-Api-Key": api_key,
        "X-Poly-Secret": secret,
        "X-Poly-Passphrase": passphrase,
    }
