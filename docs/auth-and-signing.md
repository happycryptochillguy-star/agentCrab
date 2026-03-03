# Authentication & Signing

## Auth Headers

Every request (free or paid) requires these headers:

| Header | Value | Example |
|--------|-------|---------|
| `X-Wallet-Address` | Your BSC wallet address | `0xABC...123` |
| `X-Signature` | EIP-191 signature (0x-prefixed) | `0x1a2b3c...` |
| `X-Message` | `agentcrab:{unix_timestamp}` | `agentcrab:1709136000` |
| `X-Payment-Mode` | `prepaid` or `direct` | `prepaid` |

Direct mode also requires:

| Header | Value |
|--------|-------|
| `X-Tx-Hash` | BSC tx hash from `prepare-pay` + `submit-tx` |

## How to Sign

The signature proves you own the wallet. Use your **code execution tool** for this step only:

```
1. Build message string: "agentcrab:{current_unix_timestamp}"
2. Sign it with EIP-191 personal_sign using your private key
3. The signature is a hex string starting with 0x
```

Minimal signing code (use inline, do NOT write a standalone script):

```python
from eth_account import Account
from eth_account.messages import encode_defunct
import time

account = Account.from_key("0xYOUR_PRIVATE_KEY")
ts = int(time.time())
msg = f"agentcrab:{ts}"
sig = "0x" + account.sign_message(encode_defunct(text=msg)).signature.hex()

# Now use these as headers:
# X-Wallet-Address: account.address
# X-Signature: sig
# X-Message: msg
# X-Payment-Mode: prepaid
```

**Important**: Timestamp must be within 5 minutes of server time. Re-sign for each request.

## Transaction Signing

Some endpoints (`prepare-deposit`, `prepare-transfer`, etc.) return unsigned transactions. Pattern:

```
1. Call prepare-* endpoint → response contains "transactions" array
2. For each transaction, sign it locally:
   signed = account.sign_transaction(tx["transaction"])
   raw_hex = signed.raw_transaction.hex()
3. Submit all signed txs:
   POST /payment/submit-tx
   Body: {"signed_txs": ["0xabc...", "0xdef..."], "chain": "bsc"}
```

Minimal signing code:

```python
# tx_data = response from prepare-* endpoint
signed_txs = []
for t in tx_data["transactions"]:
    signed = account.sign_transaction(t["transaction"])
    signed_txs.append("0x" + signed.raw_transaction.hex())

# Then make HTTP call:
# POST /payment/submit-tx
# Body: {"signed_txs": signed_txs, "chain": "bsc"}
```

## EIP-712 Typed Data Signing

Trading operations (Safe deploy, approvals, orders) use EIP-712. Pattern:

```
1. Call prepare-* endpoint → response contains "typed_data"
2. Sign with sign_typed_data:
   td = typed_data
   sig = "0x" + Account.sign_typed_data(
       PRIVATE_KEY, td["domain"], td["types"], td["message"]
   ).signature.hex()
3. Submit signature to the corresponding submit-* endpoint
```

## Personal Sign (for Safe approvals)

```
1. prepare-enable returns "approval_data" with a "hash" field
2. Sign the hash bytes:
   from hexbytes import HexBytes
   sig = "0x" + account.sign_message(
       encode_defunct(HexBytes(hash_value))
   ).signature.hex()
3. POST /trading/submit-approvals with the signature
```
