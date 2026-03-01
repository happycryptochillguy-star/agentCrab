# agentCrab — AI Middleware for Polymarket

agentCrab turns any AI agent into a full-featured Polymarket assistant. Market search, deposits, orderbooks, positions, trading — all through simple HTTP requests. Every response includes a `summary` field you can relay directly to the human.

**Pricing**: 0.01 USDT per API call, paid on BSC (Binance Smart Chain).
**API Base URL**: `http://localhost:8000`

---

## ⚠ Agent Behavior Rules (READ FIRST)

**You are an AI agent acting on behalf of a human. Follow these rules strictly.**

**Core rule: Be reactive, not proactive.**
- NEVER call any API endpoint unless the human explicitly asks you to do something
- NEVER auto-query markets, positions, leaderboards, or any data on your own
- NEVER start the setup workflow automatically — wait for the human to ask
- After any setup step completes, STOP and wait for the human's next request
- Your role is to respond to requests, not to anticipate them

**Communication style**: Be concise. Use short, natural sentences. No technical jargon. Show results, not process. Never say things like "I'm writing code" or "Let me construct a request". The human should feel like they're talking to a Polymarket assistant, not watching a programmer work.

**Don'ts**:
- Don't call any API unless the human asked for it
- Don't narrate your internal process ("Now I'll sign the message...", "Let me construct the request...")
- Don't show raw code, raw JSON, or technical logs unless the human asks
- Don't repeat information the human already knows
- Don't add disclaimers, caveats, or unnecessary warnings
- Don't skip payment confirmation for on-chain transactions — every transaction needs a "yes"
- Don't list features or suggest next steps unless the human asks "what can you do?"

---

## Setup Guide (reference only — do NOT auto-execute)

These steps describe how each feature works. Only perform a step when the human explicitly asks for it.

### Wallet Setup

When the human wants to set up a wallet:

- If they already provided a private key (in their message, .env file, or earlier in conversation), use it. Tell them: "Using wallet 0xABC...123."
- If they ask you to create one:

```python
from eth_account import Account
acct = Account.create()
private_key = acct.key.hex()   # Save this — it's the master key
address = acct.address
```

Tell them the address and private key (must include `0x` prefix, e.g. `0xabc123...`), and that they'll need USDT + BNB on BSC before using paid features.

**Important**: Private keys must always start with `0x`. If the human provides a key without the prefix, add it: `0x` + key.

### agentCrab Payment Setup

When the human wants to set up payment (or when a paid API call fails due to no payment):

- Every agentCrab API call costs 0.01 USDT on BSC.
- **Direct (pay per call)**: Before each paid API call, call `POST /payment/prepare-pay` to get unsigned transaction(s), sign them, and submit via `POST /payment/submit-tx`. Use the tx hash in `X-Tx-Hash` header.
- **Prepaid (deposit once, use many)**: Call `POST /payment/prepare-deposit` with the deposit amount, sign the returned transaction(s), submit each via `POST /payment/submit-tx`. Check balance with `GET /payment/balance`.

### Polymarket Deposit

When the human wants to fund their Polymarket trading account:

1. Call `POST /deposit/prepare-transfer` with the amount. Server builds an unsigned BSC `depositErc20` transaction that deposits USDT directly to the Polymarket Safe (trading balance).
2. Confirm with the human before signing.
3. Sign the returned transaction(s) and submit via `POST /payment/submit-tx`.

### Enable Trading

When the human wants to place trades (one-time setup, only needed before the first trade):

See the "Enable Trading" section below for the full flow.

---

## Feature Discovery

`GET /agent/capabilities` returns a complete, machine-readable description of all endpoints, parameters, authentication, payment methods, error codes, and rate limits. **This endpoint is free and requires no authentication.** Only call it if you need to look up endpoint details not covered in this document.

---

## Technical Reference

### Authentication Headers

Every paid request requires these headers:

| Header | Description |
|--------|-------------|
| `X-Wallet-Address` | BSC wallet address |
| `X-Signature` | EIP-191 personal_sign of the message |
| `X-Message` | `agentcrab:{unix_timestamp}` |
| `X-Payment-Mode` | `direct` or `prepaid` |
| `X-Tx-Hash` | *(direct mode only)* BSC tx hash from `pay()` |

**How to sign**:
```python
import time
from eth_account import Account
from eth_account.messages import encode_defunct

account = Account.from_key(PRIVATE_KEY)
timestamp = int(time.time())
message = f"agentcrab:{timestamp}"
signature = account.sign_message(encode_defunct(text=message)).signature.hex()

headers = {
    "X-Wallet-Address": account.address,
    "X-Signature": f"0x{signature}",
    "X-Message": message,
    "X-Payment-Mode": "prepaid",  # or "direct"
}
```

### Transaction Pattern (sign locally, server broadcasts)

All on-chain operations follow the same 2-step pattern:

```python
def sign_and_submit(resp_data, chain="bsc"):
    """Sign all txs from a prepare endpoint, submit in one batch call."""
    signed = [account.sign_transaction(t["transaction"]).raw_transaction.hex()
              for t in resp_data["transactions"]]
    return httpx.post(f"{API}/payment/submit-tx",
        json={"signed_txs": signed, "chain": chain},
        headers=auth_headers())
```

**Prepaid deposit** (e.g. $1 = 100 calls):
```python
resp = httpx.post(f"{API}/payment/prepare-deposit",
    json={"amount_usdt": 1.0}, headers=auth_headers())
sign_and_submit(resp.json()["data"])
```

**Direct payment** (per call, 0.01 USDT):
```python
resp = httpx.post(f"{API}/payment/prepare-pay", headers=auth_headers())
result = sign_and_submit(resp.json()["data"])
tx_hash = result.json()["data"]["tx_hashes"][-1]
# Use tx_hash in X-Tx-Hash header for the next paid API call
```

---

## API Endpoints

### Free (no payment)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/agent/capabilities` | Full API discovery |
| GET | `/markets/tags` | Polymarket tag categories |
| GET | `/trading/setup` | L2 credential derivation guide |
| GET | `/trading/contracts` | Polygon contract addresses |
| GET | `/deposit/supported-assets` | Supported deposit chains/tokens |
| GET | `/payment/balance` | Check prepaid balance (auth required) |
| POST | `/payment/verify` | Verify payment tx (auth required) |
| POST | `/payment/prepare-deposit` | Build unsigned deposit tx(s) (auth required) |
| POST | `/payment/prepare-pay` | Build unsigned pay tx(s) (auth required) |
| POST | `/payment/submit-tx` | Broadcast signed tx(s) to BSC/Polygon — supports batch (auth required) |
| POST | `/trading/prepare-deploy-safe` | Check Safe deployment, get CreateProxy typed data (auth required) |
| POST | `/trading/prepare-enable` | Get SafeTx hash + CLOB typed data for trading setup (auth required) |
| POST | `/trading/prepare-order` | Build EIP-712 order typed data for signing (auth required) |

### Paid (0.01 USDT/call)

**Account Setup** (one-time, gasless on Polygon)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trading/submit-deploy-safe` | Deploy Safe via relayer — gasless |
| POST | `/trading/submit-approvals` | Submit token approvals via relayer — gasless |
| POST | `/trading/submit-credentials` | Submit EIP-712 signature, get L2 credentials |

**Deposits / Withdrawals**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/deposit/prepare-transfer` | Deposit USDT on BSC directly to Polymarket Safe (trading balance) |
| POST | `/deposit/create` | Get deposit addresses (EVM/Solana/BTC) |
| POST | `/deposit/withdraw` | Get withdrawal address for destination chain |

**Market Search**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/markets/search` | Search all categories (query, tag, limit, offset) |
| GET | `/markets/events/{event_id}` | Event details |
| GET | `/markets/events/slug/{slug}` | Event by slug |
| GET | `/markets/{market_id}` | Market details |

**Orderbook / Prices**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/orderbook/{token_id}` | Full orderbook |
| POST | `/orderbook/batch` | Batch orderbooks (1 charge) |
| GET | `/prices/{token_id}` | Price summary |
| POST | `/prices/batch` | Batch prices (1 charge) |

**Positions / Trades**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/positions` | Your positions + P&L |
| GET | `/positions/trades` | Your trade history |
| GET | `/positions/activity` | Your on-chain activity |

**Leaderboard / Other Traders**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/traders/leaderboard` | Top traders |
| GET | `/traders/{address}/positions` | Another trader's positions |
| GET | `/traders/{address}/trades` | Another trader's trades |

**Trading** (requires L2 credential headers)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trading/submit-order` | Submit signed order to Polymarket CLOB |
| DELETE | `/trading/order/{order_id}` | Cancel order |
| DELETE | `/trading/orders` | Cancel all orders |
| GET | `/trading/orders` | Open orders |

Trading endpoints require these additional headers: `X-Poly-Api-Key`, `X-Poly-Secret`, `X-Poly-Passphrase`.
These are derived once via the Enable Trading flow below.

### Enable Trading (one-time setup, fully gasless)

Before placing orders, the agent must enable trading. All Polygon operations are gasless — the server handles everything via Polymarket's relayer.

```python
from eth_account.messages import encode_defunct
from hexbytes import HexBytes

# 1. Deploy Safe wallet (skip if already deployed)
resp = httpx.post(f"{API}/trading/prepare-deploy-safe", headers=auth_headers())
data = resp.json()["data"]
if not data["already_deployed"]:
    td = data["typed_data"]
    sig = Account.sign_typed_data(
        PRIVATE_KEY, td["domain"], td["types"], td["message"]
    ).signature.hex()
    httpx.post(f"{API}/trading/submit-deploy-safe",
        json={"signature": f"0x{sig}"}, headers=auth_headers())

# 2. Get approval status + CLOB typed data
resp = httpx.post(f"{API}/trading/prepare-enable", headers=auth_headers())
data = resp.json()["data"]

# 3. Sign and submit approvals ONLY if needed (server checks on-chain)
if data["approvals_needed"]:
    approval_hash = data["approval_data"]["hash"]
    approval_sig = account.sign_message(
        encode_defunct(HexBytes(approval_hash))
    ).signature.hex()
    httpx.post(f"{API}/trading/submit-approvals",
        json={"signature": f"0x{approval_sig}", "approval_data": data["approval_data"]},
        headers=auth_headers())

# 4. Sign CLOB typed data and derive L2 credentials
clob_td = data["clob_typed_data"]
clob_sig = Account.sign_typed_data(
    PRIVATE_KEY, clob_td["domain"], clob_td["types"], clob_td["message"]
).signature.hex()
resp = httpx.post(f"{API}/trading/submit-credentials",
    json={"signature": f"0x{clob_sig}", "timestamp": clob_td["message"]["timestamp"]},
    headers=auth_headers())
creds = resp.json()["data"]
# Store creds["api_key"], creds["secret"], creds["passphrase"] — they don't expire
```

After this, include L2 credentials as headers in all trading requests:
```
X-Poly-Api-Key: <api_key>
X-Poly-Secret: <secret>
X-Poly-Passphrase: <passphrase>
```

### Placing Orders (prepare → sign → submit)

```python
# 1. Server builds the order (fetches tick size, fees, etc.)
resp = httpx.post(f"{API}/trading/prepare-order",
    json={"token_id": "...", "side": "BUY", "size": 5.0, "price": 0.65},
    headers=auth_headers())
data = resp.json()["data"]
# summary tells you: "Order ready: BUY 5.0 shares of "Yes" on "Will X happen?" @ $0.65 ($3.25 total)"

# 2. Sign the EIP-712 typed data
td = data["typed_data"]
sig = Account.sign_typed_data(
    PRIVATE_KEY, td["domain"], td["types"], td["message"]
).signature.hex()

# 3. Submit — server handles CLOB auth and submission
trade_headers = {**auth_headers(), "X-Poly-Api-Key": api_key, "X-Poly-Secret": secret, "X-Poly-Passphrase": passphrase}
resp = httpx.post(f"{API}/trading/submit-order",
    json={"signature": f"0x{sig}", "clob_order": data["clob_order"], "order_type": "GTC"},
    headers=trade_headers)
# summary tells you: "Order filled: bought 5 shares for $3.25 USDC."
```

Order types: `GTC` (limit), `FOK` (fill-or-kill / market), `FAK` (fill-and-kill), `GTD` (good-till-date).

---

## Example: Complete First-Time Flow

```python
"""
Complete example: wallet setup → payment → deposit → enable trading → trade
Dependencies: pip install httpx eth-account
"""
import time, httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from hexbytes import HexBytes

API = "http://localhost:8000"

# ── Step 1: Use existing key or create wallet ──
PRIVATE_KEY = "0xUSER_PRIVATE_KEY"  # from user input
account = Account.from_key(PRIVATE_KEY)

# ── Helpers ──
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

def sign_and_submit(data, chain="bsc"):
    """Sign all txs locally, submit in one batch call."""
    signed = [account.sign_transaction(t["transaction"]).raw_transaction.hex()
              for t in data["transactions"]]
    return httpx.post(f"{API}/payment/submit-tx",
        json={"signed_txs": signed, "chain": chain},
        headers=auth_headers())

# ── Step 2: Prepaid deposit to agentCrab (1 USDT = 100 API calls) ──
resp = httpx.post(f"{API}/payment/prepare-deposit",
    json={"amount_usdt": 1.0}, headers=auth_headers())
sign_and_submit(resp.json()["data"])

# ── Step 3: Deposit to Polymarket (direct to Safe via BSC contract) ──
resp = httpx.post(f"{API}/deposit/prepare-transfer",
    json={"amount_usdt": 10.0}, headers=auth_headers())
sign_and_submit(resp.json()["data"])

# ── Step 4: Deploy Safe wallet (gasless, one-time) ──
resp = httpx.post(f"{API}/trading/prepare-deploy-safe", headers=auth_headers())
data = resp.json()["data"]
if not data["already_deployed"]:
    td = data["typed_data"]
    sig = Account.sign_typed_data(PRIVATE_KEY, td["domain"], td["types"], td["message"]).signature.hex()
    httpx.post(f"{API}/trading/submit-deploy-safe",
        json={"signature": f"0x{sig}"}, headers=auth_headers())

# ── Step 5: Enable trading (gasless, one-time) ──
resp = httpx.post(f"{API}/trading/prepare-enable", headers=auth_headers())
data = resp.json()["data"]

# Sign approval hash (personal_sign) → submit to relayer (skip if already approved)
if data["approvals_needed"]:
    ah = data["approval_data"]["hash"]
    asig = account.sign_message(encode_defunct(HexBytes(ah))).signature.hex()
    httpx.post(f"{API}/trading/submit-approvals",
        json={"signature": f"0x{asig}", "approval_data": data["approval_data"]},
        headers=auth_headers())

# Sign CLOB typed data → derive L2 credentials
ct = data["clob_typed_data"]
csig = Account.sign_typed_data(PRIVATE_KEY, ct["domain"], ct["types"], ct["message"]).signature.hex()
resp = httpx.post(f"{API}/trading/submit-credentials",
    json={"signature": f"0x{csig}", "timestamp": ct["message"]["timestamp"]},
    headers=auth_headers())
creds = resp.json()["data"]
poly_headers = {
    "X-Poly-Api-Key": creds["api_key"],
    "X-Poly-Secret": creds["secret"],
    "X-Poly-Passphrase": creds["passphrase"],
}

# ── Step 6: Search markets and trade ──
resp = httpx.get(f"{API}/markets/search?query=bitcoin&limit=5",
    headers=auth_headers())
print(resp.json()["summary"])

# Place order (prepare → sign → submit)
resp = httpx.post(f"{API}/trading/prepare-order",
    json={"token_id": "...", "side": "BUY", "size": 5, "price": 0.65},
    headers=auth_headers())
order_data = resp.json()["data"]
td = order_data["typed_data"]
sig = Account.sign_typed_data(PRIVATE_KEY, td["domain"], td["types"], td["message"]).signature.hex()
resp = httpx.post(f"{API}/trading/submit-order",
    json={"signature": f"0x{sig}", "clob_order": order_data["clob_order"], "order_type": "GTC"},
    headers={**auth_headers(), **poly_headers})
print(resp.json()["summary"])
```

---

## Deployment (Self-Hosted)

```bash
cd Polymarket
pip install -r api/requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
