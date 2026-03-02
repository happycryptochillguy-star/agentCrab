"""EIP-191 authentication header building."""

import time

from eth_account import Account
from eth_account.messages import encode_defunct


def build_auth_headers(
    private_key: str,
    address: str,
    payment_mode: str = "prepaid",
) -> dict[str, str]:
    """Build authentication headers for API requests.

    Signs ``agentcrab:{unix_timestamp}`` with EIP-191 personal_sign.
    """
    ts = int(time.time())
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
