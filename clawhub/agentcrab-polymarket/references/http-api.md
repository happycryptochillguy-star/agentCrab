# HTTP API Reference

Use this if you cannot run Python. The SDK is preferred — see SKILL.md.

**Base URL**: `https://api.agentcrab.ai/polymarket`

## Authentication

Every request requires these headers:

| Header | Value |
|--------|-------|
| `X-Wallet-Address` | BSC wallet address |
| `X-Signature` | EIP-191 signature (0x-prefixed) |
| `X-Message` | `agentcrab:{unix_timestamp}` |
| `X-Payment-Mode` | `prepaid` or `direct` |

Sign with:
```python
from eth_account import Account
from eth_account.messages import encode_defunct
import time

account = Account.from_key(os.environ["AGENTCRAB_PRIVATE_KEY"])
ts = int(time.time())
msg = f"agentcrab:{ts}"
sig = "0x" + account.sign_message(encode_defunct(text=msg)).signature.hex()
```

Timestamp must be within 5 minutes of server time.

## Endpoints

### Free (auth only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agent/create-wallet` | Create new wallet (no auth needed) |
| GET | `/agent/capabilities` | Full API discovery |
| GET | `/payment/balance` | Check balance |
| GET | `/markets/categories` | List categories |
| GET | `/trading/credentials` | Retrieve cached L2 creds |
| GET | `/trading/triggers` | List triggers |
| DELETE | `/trading/triggers/{id}` | Cancel trigger |

### Paid (0.01 USDT each)

| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/markets/search?query=X` | — | Search markets |
| GET | `/markets/browse?mood=X` | — | Browse by mood |
| GET | `/markets/browse?category=X` | — | Browse by category |
| GET | `/orderbook/{token_id}` | — | Get orderbook |
| GET | `/prices/{token_id}` | — | Get price |
| GET | `/positions` | — | Your positions |
| GET | `/positions/trades` | — | Trade history |
| GET | `/positions/activity` | — | On-chain activity |

### Transaction Building (free, then paid on submit)

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/payment/prepare-deposit` | `{"amount_usdt": 1.0}` | Build agentCrab deposit tx |
| POST | `/payment/prepare-pay` | — | Build direct-pay tx |
| POST | `/payment/submit-tx` | `{"signed_txs": [...], "chain": "bsc"}` | Broadcast signed tx |
| POST | `/deposit/prepare-transfer` | `{"amount_usdt": 10.0}` | Build Polymarket deposit tx |

### Trading Setup (0.01 USDT on submit)

| Method | Path | Body |
|--------|------|------|
| POST | `/trading/prepare-deploy-safe` | — |
| POST | `/trading/submit-deploy-safe` | `{"signature": "0x..."}` |
| POST | `/trading/prepare-enable` | — |
| POST | `/trading/submit-approvals` | `{"signature": "0x...", "approval_data": {...}}` |
| POST | `/trading/submit-credentials` | `{"signature": "0x...", "timestamp": "..."}` |

### Orders (0.01 USDT on submit)

Trading endpoints require extra headers: `X-Poly-Api-Key`, `X-Poly-Secret`, `X-Poly-Passphrase`.

| Method | Path | Body |
|--------|------|------|
| POST | `/trading/prepare-order` | `{"token_id": "...", "side": "BUY", "size": 5.0, "price": 0.65}` |
| POST | `/trading/submit-order` | `{"signature": "0x...", "clob_order": {...}, "order_type": "GTC"}` |
| POST | `/trading/prepare-batch-order` | `{"orders": [...]}` |
| POST | `/trading/submit-batch-order` | `{"orders": [...]}` |
| DELETE | `/trading/order/{order_id}` | — |
| DELETE | `/trading/orders` | — |
| GET | `/trading/orders` | — |

### Triggers

| Method | Path | Body |
|--------|------|------|
| POST | `/trading/triggers/prepare` | `{"token_id": "...", "trigger_type": "stop_loss", ...}` |
| POST | `/trading/triggers/create` | `{"signature": "0x...", "clob_order": {...}, ...}` |

## Transaction Signing

Prepare endpoints return unsigned transactions. Pattern:

```python
# 1. Call prepare-* → get transactions array
# 2. Sign each:
signed_txs = []
for t in data["transactions"]:
    signed = account.sign_transaction(t["transaction"])
    signed_txs.append("0x" + signed.raw_transaction.hex())
# 3. Submit:
POST /payment/submit-tx  body: {"signed_txs": signed_txs, "chain": "bsc"}
```

## EIP-712 Signing (for trading)

```python
td = data["typed_data"]
sig = "0x" + Account.sign_typed_data(
    private_key, td["domain"], td["types"], td["message"]
).signature.hex()
```
