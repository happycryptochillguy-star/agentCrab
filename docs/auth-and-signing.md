# Authentication & Signing

## Auth Headers

Every paid request requires these 4 headers (5 for direct mode):

| Header | Value |
|--------|-------|
| `X-Wallet-Address` | Your BSC wallet address |
| `X-Signature` | `0x` + hex signature |
| `X-Message` | `agentcrab:{unix_timestamp}` |
| `X-Payment-Mode` | `prepaid` or `direct` |
| `X-Tx-Hash` | *(direct only)* tx hash from `pay()` |

## Signing Code

```python
import time
from eth_account import Account
from eth_account.messages import encode_defunct

account = Account.from_key(PRIVATE_KEY)

def auth_headers(payment_mode="prepaid"):
    ts = int(time.time())
    msg = f"agentcrab:{ts}"
    sig = account.sign_message(encode_defunct(text=msg)).signature.hex()
    return {
        "X-Wallet-Address": account.address,
        "X-Signature": f"0x{sig}",
        "X-Message": msg,
        "X-Payment-Mode": payment_mode,
    }
```

## Transaction Pattern

All on-chain operations (payment, deposit, etc.) follow the same pattern:
1. Call a `prepare-*` endpoint → server returns unsigned transaction(s)
2. Sign locally → submit via `POST /payment/submit-tx`

```python
import httpx
API = "http://localhost:8000/polymarket"  # or "https://api.agentcrab.ai/polymarket"

def sign_and_submit(resp_data, chain="bsc"):
    """Sign all txs from a prepare endpoint, submit in one batch call."""
    signed = [account.sign_transaction(t["transaction"]).raw_transaction.hex()
              for t in resp_data["transactions"]]
    return httpx.post(f"{API}/payment/submit-tx",
        json={"signed_txs": signed, "chain": chain},
        headers=auth_headers())
```
