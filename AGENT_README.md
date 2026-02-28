# agentWay — AI Middleware for Polymarket

agentWay is an API middleware built for AI agents. It provides structured, easy-to-parse access to Polymarket football/soccer prediction markets. Every response includes a `summary` field — a natural language sentence you can relay directly to the human you're assisting.

**Pricing**: 0.01 USDT per API call, paid on BSC (Binance Smart Chain).

---

## Available Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/football/markets` | GET | Get active football/soccer events with odds, volumes, and market data |
| `/payment/balance` | GET | Check your prepaid balance and remaining API calls |
| `/payment/verify` | POST | Verify a direct payment transaction |
| `/health` | GET | Check if the API is running (free, no auth) |

**Base URL**: `http://localhost:8000` (self-hosted — see deployment instructions below)

---

## Quick Start for Agents

### Step 1: Prerequisites

You need:
- A BSC (Binance Smart Chain) wallet with a private key
- USDT on BSC (token: `0x55d398326f99059fF775485246999027B3197955`, 18 decimals)
- The ability to sign messages (EIP-191 personal_sign) and send BSC transactions

### Step 2: Choose Payment Mode

| Mode | How it works | Best for |
|------|-------------|----------|
| **Direct (per-call)** | Call `pay()` on the smart contract before each API call, pass tx hash in header | Occasional usage |
| **Prepaid** | Deposit USDT once via `deposit()`, balance is tracked off-chain | Frequent usage |

### Step 3: Pay

**Smart Contract Address (BSC)**: `0x497579f445eA3707D0fE84C6bd2408620D384a4C`
**Chain**: BSC (Chain ID: 56)
**USDT Address**: `0x55d398326f99059fF775485246999027B3197955`

#### Mode A — Direct Payment (per-call)

1. Approve the contract to spend 0.01 USDT (10^16 wei):
```
USDT.approve(CONTRACT_ADDRESS, 10000000000000000)
```

2. Call `pay()` on the contract:
```
AgentWayPayment.pay()
```

3. Use the transaction hash in your API call (see Step 4).

#### Mode B — Prepaid Deposit

1. Approve the contract to spend your desired deposit amount:
```
USDT.approve(CONTRACT_ADDRESS, AMOUNT_IN_WEI)
```

2. Call `deposit(amount)`:
```
AgentWayPayment.deposit(AMOUNT_IN_WEI)
```

3. Wait ~15 seconds for the background scanner to detect your deposit. Then call the API with `X-Payment-Mode: prepaid`.

#### Contract ABI (minimal)

```json
[
  {
    "inputs": [],
    "name": "pay",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"name": "amount", "type": "uint256"}],
    "name": "deposit",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"name": "user", "type": "address"}],
    "name": "getBalance",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [{"name": "user", "type": "address"}],
    "name": "getDirectPaymentCount",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  }
]
```

### Step 4: Call the API

Every request (except `/health`) requires these headers:

| Header | Description |
|--------|-------------|
| `X-Wallet-Address` | Your BSC wallet address (e.g., `0xABC...`) |
| `X-Signature` | EIP-191 personal_sign signature of the message |
| `X-Message` | The signed message, format: `agentway:{unix_timestamp}` |
| `X-Payment-Mode` | `direct` or `prepaid` |
| `X-Tx-Hash` | *(direct mode only)* The BSC transaction hash from calling `pay()` |

**Authentication**: Sign the message `agentway:{unix_timestamp}` using EIP-191 personal_sign with your wallet's private key. The timestamp must be within 5 minutes of server time.

#### Example: Get Football Markets (Direct Mode)

```bash
curl -X GET "http://localhost:8000/football/markets?limit=5" \
  -H "X-Wallet-Address: 0xYourWalletAddress" \
  -H "X-Signature: 0xYourSignature..." \
  -H "X-Message: agentway:1709136000" \
  -H "X-Payment-Mode: direct" \
  -H "X-Tx-Hash: 0xYourTxHash..."
```

#### Example: Get Football Markets (Prepaid Mode)

```bash
curl -X GET "http://localhost:8000/football/markets?league=premier_league&limit=10" \
  -H "X-Wallet-Address: 0xYourWalletAddress" \
  -H "X-Signature: 0xYourSignature..." \
  -H "X-Message: agentway:1709136000" \
  -H "X-Payment-Mode: prepaid"
```

---

## API Reference

### GET /football/markets

Fetch active football/soccer prediction markets from Polymarket.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | string | null | Filter by league: `premier_league`, `la_liga`, `ucl`, `champions_league`, `serie_a`, `bundesliga`, `ligue_1`, `mls`, `world_cup`, `europa_league` |
| `limit` | int | 20 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Example Response:**

```json
{
  "status": "ok",
  "summary": "Found 3 active football events on Polymarket. Top event: \"Arsenal vs Chelsea - Premier League\" with $45,000 in volume.",
  "data": [
    {
      "event_id": "12345",
      "title": "Arsenal vs Chelsea - Premier League",
      "slug": "arsenal-vs-chelsea-premier-league",
      "markets": [
        {
          "question": "Will Arsenal win against Chelsea?",
          "market_slug": "will-arsenal-win-against-chelsea",
          "outcomes": [
            {"outcome": "Yes", "price": 0.65, "token_id": "abc123..."},
            {"outcome": "No", "price": 0.35, "token_id": "def456..."}
          ],
          "volume": 45000.0,
          "liquidity": 12000.0,
          "end_date": "2026-03-15T20:00:00Z",
          "active": true
        }
      ],
      "volume": 45000.0,
      "start_date": "2026-03-15T17:30:00Z",
      "end_date": "2026-03-15T20:00:00Z"
    }
  ]
}
```

**Field Descriptions:**
- `summary`: Natural language summary you can relay directly to the human
- `event_id`: Polymarket event identifier
- `title`: Human-readable event title
- `markets[].question`: The prediction question
- `markets[].outcomes[].price`: Current probability (0.0 to 1.0). E.g., 0.65 = 65% chance
- `markets[].outcomes[].token_id`: Polymarket CLOB token ID for trading
- `markets[].volume`: Total trading volume in USD
- `markets[].liquidity`: Current liquidity in USD

### GET /payment/balance

Check your prepaid balance.

**Headers**: `X-Wallet-Address`, `X-Signature`, `X-Message` (no payment headers needed)

**Example Response:**

```json
{
  "status": "ok",
  "summary": "Wallet 0xABC123... has 50 API calls remaining (0.5000 USDT).",
  "data": {
    "wallet_address": "0xabc123...",
    "total_deposited_wei": "1000000000000000000",
    "total_consumed_wei": "500000000000000000",
    "remaining_wei": "500000000000000000",
    "calls_remaining": 50
  }
}
```

### POST /payment/verify

Verify a direct payment transaction.

**Query Parameter**: `tx_hash` (required) — the BSC transaction hash

**Headers**: `X-Wallet-Address`, `X-Signature`, `X-Message`

**Example Response:**

```json
{
  "status": "ok",
  "summary": "Transaction 0xabc123... verified. DirectPayment from 0xdef456... confirmed.",
  "data": {
    "tx_hash": "0xabc123...",
    "verified": true,
    "wallet_address": "0xdef456...",
    "message": "Payment verified successfully."
  }
}
```

### GET /health

No authentication required. Check API status.

```json
{
  "status": "ok",
  "summary": "agentWay Polymarket API is running.",
  "data": {
    "contract_address": "0x...",
    "payment_amount": "0.01 USDT per call",
    "chain": "BSC (Chain ID: 56)"
  }
}
```

---

## Error Codes

All errors follow this format:

```json
{
  "status": "error",
  "error_code": "ERROR_CODE",
  "message": "Human-readable description of what went wrong and what to do next."
}
```

| Error Code | HTTP Status | Meaning | What to Do |
|------------|-------------|---------|------------|
| `INVALID_SIGNATURE` | 401 | Signature verification failed | Re-sign `agentway:{current_unix_timestamp}` with your wallet key |
| `MISSING_TX_HASH` | 400 | Direct mode but no tx hash provided | Add `X-Tx-Hash` header with the `pay()` transaction hash |
| `PAYMENT_NOT_VERIFIED` | 402 | Cannot find DirectPayment event in tx | Verify you called `pay()` on the correct contract and tx is confirmed |
| `INSUFFICIENT_BALANCE` | 402 | Prepaid balance too low | Deposit more USDT via `deposit()` on the contract |
| `BALANCE_DEDUCTION_FAILED` | 402 | Off-chain balance deduction failed | Retry the request |
| `INVALID_PAYMENT_MODE` | 400 | Unknown payment mode | Use `direct` or `prepaid` in `X-Payment-Mode` header |
| `UPSTREAM_ERROR` | 502 | Polymarket API failed | Retry after a few seconds |

---

## Pricing

- **0.01 USDT per API call** (10^16 wei, since BSC USDT has 18 decimals)
- Paid via smart contract on BSC (Chain ID: 56)
- USDT token: `0x55d398326f99059fF775485246999027B3197955`

---

## Deployment (Self-Hosted)

```bash
# Clone the repo
git clone https://github.com/user/agentWay.git
cd agentWay/Polymarket

# Set up environment
cp .env.example .env
# Edit .env: set PRIVATE_KEY, CONTRACT_ADDRESS, BSC_RPC_URL

# Install Python dependencies
pip install -r api/requirements.txt

# Run the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Deploy the smart contract (requires Foundry)
cd contracts
forge script script/Deploy.s.sol:DeployScript --rpc-url $BSC_RPC_URL --broadcast --verify -vvvv
# Copy the proxy address to .env as CONTRACT_ADDRESS
```
