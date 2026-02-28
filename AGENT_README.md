# agentCrab — AI Middleware for Polymarket

agentCrab turns any AI agent into a full-featured Polymarket assistant. Market search, deposits, orderbooks, positions, trading — all through simple HTTP requests. Every response includes a `summary` field you can relay directly to the human.

**Pricing**: 0.01 USDT per API call, paid on BSC (Binance Smart Chain).
**API Base URL**: `http://localhost:8000`

---

## ⚠ Agent Behavior Rules (READ FIRST)

**You are an AI agent acting on behalf of a human. Follow these rules strictly.**

**Communication style**: Be concise. Use short, natural sentences. No technical jargon. Don't explain what you're doing behind the scenes — just do it and show results. Never say things like "I'm writing code" or "Let me construct a request". The human should feel like they're talking to a Polymarket assistant, not watching a programmer work.

**Don'ts**:
- Don't narrate your internal process ("Now I'll sign the message...", "Let me construct the request...")
- Don't show raw code, raw JSON, or technical logs unless the human asks
- Don't repeat information the human already knows
- Don't add disclaimers, caveats, or unnecessary warnings
- Don't skip payment confirmation for on-chain transactions — every transaction needs a "yes"

---

## Complete Workflow (follow in order)

### Step 1 — Wallet Setup

The human needs a BSC wallet. This is used for both paying agentCrab fees and holding funds.

**Check for existing wallet**:
- If the human already provided a private key (in their message, .env file, or earlier in conversation), use it. Tell them: "Using wallet 0xABC...123."
- If no key available, ask:

> "Do you have a BSC wallet private key? If yes, paste it here. If not, I'll create a new one for you."

**If the human says they don't have one**, create a new wallet:

```python
from eth_account import Account
acct = Account.create()
private_key = acct.key.hex()   # Save this — it's the master key
address = acct.address
```

Then tell the human:
> "I created a new wallet for you:
> Address: 0xABC...123
> Private key: 0x... (save this somewhere safe!)
> You'll need to transfer some USDT + a tiny bit of BNB (for gas) to this address before we can proceed."

**Wait for the human to confirm they have USDT + BNB on this wallet before continuing.**

### Step 2 — agentCrab Payment Setup

Every agentCrab API call costs 0.01 USDT on BSC. Ask the human:

> "Each API query costs $0.01 USDT on BSC. Two options:
> (A) Pay per query — $0.01 each time
> (B) Prepaid — deposit once, use many times (e.g. $1 = 100 queries)
> Which do you prefer?"

Wait for their answer. Then:

- **If Direct (A)**: No setup needed now. You'll call `pay()` before each API call.
- **If Prepaid (B)**:
  1. Check existing balance: `GET /payment/balance`
  2. If balance > 0, tell them: "You already have X calls remaining."
  3. If balance = 0, ask how much to deposit (suggest $1 = 100 calls). Get confirmation.
  4. On "yes": execute `approve()` + `deposit()` on the BSC contract (see Payment Reference below), wait ~15s for the scanner.
  5. Confirm: "Deposit complete. You now have X calls available."

### Step 3 — Polymarket Deposit (Fund Trading Account)

Now ask about funding their Polymarket trading account:

> "Do you want to deposit funds to Polymarket for trading? If yes, how much USDT?"

If they say no, skip to Step 4. If they say yes:

1. The human's Polymarket wallet address = the same wallet address (Polymarket uses the same EVM address on Polygon).
2. Call `POST /deposit/create` with their address to get a deposit address.
3. Tell the human: "Send [amount] USDT to deposit address 0x... OK?"
4. On "yes": sign a standard USDT transfer from their wallet to the deposit address.
5. Tell them: "Transfer sent! Polymarket will bridge the funds to your account automatically. This may take a few minutes."

### Step 4 — Ready to Use

Now the human is fully set up. Ask what they want to do:

> "You're all set! What would you like to do?
> - Search prediction markets (politics, sports, crypto, etc.)
> - Check odds on a specific event
> - View the leaderboard
> - Place a trade
> - Check your positions/P&L"

### Subsequent Interactions

Skip Steps 1-3. Go directly to whatever the human asks. For prepaid users, no payment confirmation is needed — balance is deducted automatically.

---

## Feature Discovery

Call `GET /agent/capabilities` to get a complete, machine-readable description of all endpoints, parameters, authentication, payment methods, error codes, and rate limits. **This endpoint is free and requires no authentication.**

Always call this endpoint first when starting a new session.

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

### Payment Contract (BSC)

**Address**: `0x497579f445eA3707D0fE84C6bd2408620D384a4C`
**Chain**: BSC (Chain ID: 56)
**USDT**: `0x55d398326f99059fF775485246999027B3197955` (18 decimals)

```json
[
  {"inputs": [], "name": "pay", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
  {"inputs": [{"name": "amount", "type": "uint256"}], "name": "deposit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
  {"inputs": [{"name": "user", "type": "address"}], "name": "getBalance", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}
]
```

**Direct payment (per call)**:
```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/"))
PAYMENT_AMOUNT = 10**16  # 0.01 USDT

# 1. Approve (one-time, approve more to avoid repeating)
usdt.functions.approve(CONTRACT, PAYMENT_AMOUNT * 100).build_transaction(...)
# 2. Pay
contract.functions.pay().build_transaction(...)
# 3. Use tx hash in X-Tx-Hash header
```

**Prepaid deposit**:
```python
DEPOSIT_AMOUNT = 10**18  # 1 USDT = 100 calls

# 1. Approve
usdt.functions.approve(CONTRACT, DEPOSIT_AMOUNT).build_transaction(...)
# 2. Deposit
contract.functions.deposit(DEPOSIT_AMOUNT).build_transaction(...)
# 3. Wait ~15s, then use X-Payment-Mode: prepaid
```

---

## API Endpoints

### Free (no payment)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/agent/capabilities` | Full API discovery (call this first!) |
| GET | `/markets/tags` | Polymarket tag categories |
| GET | `/trading/setup` | L2 credential derivation guide |
| GET | `/trading/contracts` | Polygon contract addresses |
| GET | `/deposit/supported-assets` | Supported deposit chains/tokens |
| GET | `/payment/balance` | Check prepaid balance (auth required) |
| POST | `/payment/verify` | Verify payment tx (auth required) |

### Paid (0.01 USDT/call)

**Deposits / Withdrawals**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/deposit/create` | Get deposit addresses (EVM/Solana/BTC) |
| POST | `/deposit/withdraw` | Get withdrawal address for destination chain |

**Market Search**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/markets/search` | Search all categories (query, tag, limit, offset) |
| GET | `/markets/events/{event_id}` | Event details |
| GET | `/markets/events/slug/{slug}` | Event by slug |
| GET | `/markets/{market_id}` | Market details |
| GET | `/football/markets` | Football markets (league, limit, offset) |

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
| GET | `/positions` | Your positions + P&L (needs X-Poly-Address) |
| GET | `/positions/trades` | Your trade history |
| GET | `/positions/activity` | Your on-chain activity |

**Leaderboard / Other Traders**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/traders/leaderboard` | Top traders |
| GET | `/traders/{address}/positions` | Another trader's positions |
| GET | `/traders/{address}/trades` | Another trader's trades |

**Trading** (requires Polymarket L2 headers)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trading/order` | Place order (limit/market) |
| DELETE | `/trading/order/{order_id}` | Cancel order |
| DELETE | `/trading/orders` | Cancel all orders |
| GET | `/trading/orders` | Open orders |

Trading requires additional headers: `X-Poly-Api-Key`, `X-Poly-Secret`, `X-Poly-Passphrase`, `X-Poly-Address`.
These are derived once locally — see `GET /trading/setup` for instructions.

---

## Example: Complete First-Time Flow

```python
"""
Complete example: wallet setup → agentCrab payment → Polymarket deposit → search markets
Dependencies: pip install web3 httpx eth-account
"""
import time, httpx
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

API = "http://localhost:8000"
BSC_RPC = "https://bsc-dataseed.binance.org/"
CONTRACT = "0x497579f445eA3707D0fE84C6bd2408620D384a4C"
USDT = "0x55d398326f99059fF775485246999027B3197955"

# ── Step 1: Use existing key or create wallet ──
PRIVATE_KEY = "0xUSER_PRIVATE_KEY"  # from user input
account = Account.from_key(PRIVATE_KEY)
w3 = Web3(Web3.HTTPProvider(BSC_RPC))

# ── Step 2: Prepaid deposit to agentCrab (1 USDT = 100 API calls) ──
USDT_ABI = [{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]
PAY_ABI = [{"inputs":[{"name":"amount","type":"uint256"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"}]

usdt_contract = w3.eth.contract(address=Web3.to_checksum_address(USDT), abi=USDT_ABI)
pay_contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT), abi=PAY_ABI)

deposit_amount = 10**18  # 1 USDT
# approve + deposit (sign and send both transactions)

# ── Step 3: Build auth headers (reuse for all API calls) ──
def auth_headers():
    ts = int(time.time())
    msg = f"agentcrab:{ts}"
    sig = account.sign_message(encode_defunct(text=msg)).signature.hex()
    return {
        "X-Wallet-Address": account.address,
        "X-Signature": f"0x{sig}",
        "X-Message": msg,
        "X-Payment-Mode": "prepaid",
    }

# ── Step 4: Deposit to Polymarket ──
resp = httpx.post(f"{API}/deposit/create",
    json={"polymarket_address": account.address},
    headers=auth_headers())
evm_deposit_addr = resp.json()["data"]["deposit_addresses"]["evm"]
# Send USDT to evm_deposit_addr (standard ERC-20 transfer)

# ── Step 5: Search markets ──
resp = httpx.get(f"{API}/markets/search?query=premier+league&limit=5",
    headers=auth_headers())
print(resp.json()["summary"])
```

---

## Deployment (Self-Hosted)

```bash
git clone https://github.com/happycryptochillguy-star/agentCrab.git
cd agentWay/Polymarket
pip install -r api/requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
