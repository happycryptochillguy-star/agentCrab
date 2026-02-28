# agentWay — AI Middleware for Polymarket

agentWay is an API middleware built for AI agents. It provides structured, easy-to-parse access to Polymarket football/soccer prediction markets. Every response includes a `summary` field — a natural language sentence you can relay directly to the human you're assisting.

**Pricing**: 0.01 USDT per API call, paid on BSC (Binance Smart Chain).

---

## ⚠ Agent Behavior Rules (READ FIRST)

**You are an AI agent acting on behalf of a human. You MUST follow these rules:**

1. **Explain first** — Before doing anything, tell the human what agentWay offers:
   - Service: Football/soccer prediction market data from Polymarket (odds, volumes, market info)
   - Pricing: 0.01 USDT per API call (~$0.01), paid on BSC chain
   - Payment options: pay-per-call (direct) or prepaid deposit (bulk)

2. **Ask for consent** — After explaining, explicitly ask the human: *"Would you like me to proceed? This will cost 0.01 USDT per query on BSC. I'll need to use your wallet to approve and send a transaction."* **Do NOT proceed until the human says yes.**

3. **Confirm wallet** — Before any on-chain transaction, show the human:
   - Which wallet address will be used
   - How much USDT will be spent or deposited
   - Ask: *"Shall I go ahead with this transaction?"*

4. **Never pay silently** — Every transaction that spends money requires explicit human approval. This includes `approve()`, `pay()`, and `deposit()` calls.

5. **Report results clearly** — After a successful API call, relay the `summary` field directly to the human. Include key data points (odds, volumes) in a readable format.

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

## Complete Python Examples

> **Dependencies**: `pip install web3 httpx`
>
> Each script below is **self-contained** — copy-paste and run directly. No assembly required.

### Script A — Direct Payment (Single API Call)

Use this when you want to pay-per-call. Each call costs 0.01 USDT on BSC.

```python
"""
agentWay — Direct Payment Example
Pay 0.01 USDT per call, then query football markets.
Dependencies: pip install web3 httpx
"""

import time
import httpx
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

# ── Configuration ────────────────────────────────────────────────
PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE"          # BSC wallet private key
API_BASE_URL = "http://localhost:8000"            # agentWay API base URL

# Constants (do not change)
BSC_RPC = "https://bsc-dataseed.binance.org/"
CONTRACT_ADDRESS = "0x497579f445eA3707D0fE84C6bd2408620D384a4C"
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
PAYMENT_AMOUNT = 10**16  # 0.01 USDT (18 decimals)
CHAIN_ID = 56

# Minimal ABIs
ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PAYMENT_ABI = [
    {
        "inputs": [],
        "name": "pay",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ── Setup ────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(BSC_RPC))
account = Account.from_key(PRIVATE_KEY)
wallet_address = account.address
print(f"Wallet: {wallet_address}")

usdt = w3.eth.contract(address=Web3.to_checksum_address(USDT_ADDRESS), abi=ERC20_ABI)
contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=PAYMENT_ABI)

# ── Step 1: Approve USDT (skip if already approved) ─────────────
allowance = usdt.functions.allowance(wallet_address, CONTRACT_ADDRESS).call()
if allowance < PAYMENT_AMOUNT:
    print("Approving USDT spend...")
    tx = usdt.functions.approve(CONTRACT_ADDRESS, PAYMENT_AMOUNT * 100).build_transaction({
        "from": wallet_address,
        "nonce": w3.eth.get_transaction_count(wallet_address),
        "gas": 60000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Approved. tx: {tx_hash.hex()}")

# ── Step 2: Call pay() on the contract ───────────────────────────
print("Calling pay() — 0.01 USDT...")
tx = contract.functions.pay().build_transaction({
    "from": wallet_address,
    "nonce": w3.eth.get_transaction_count(wallet_address),
    "gas": 100000,
    "gasPrice": w3.eth.gas_price,
    "chainId": CHAIN_ID,
})
signed = account.sign_transaction(tx)
pay_tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(pay_tx_hash)
print(f"Payment confirmed. tx: {pay_tx_hash.hex()}")

# ── Step 3: Sign auth message ────────────────────────────────────
timestamp = int(time.time())
message = f"agentway:{timestamp}"
msg_hash = encode_defunct(text=message)
signature = account.sign_message(msg_hash).signature.hex()

# ── Step 4: Call the API ─────────────────────────────────────────
print("Calling /football/markets ...")
resp = httpx.get(
    f"{API_BASE_URL}/football/markets",
    params={"limit": 5},
    headers={
        "X-Wallet-Address": wallet_address,
        "X-Signature": f"0x{signature}",
        "X-Message": message,
        "X-Payment-Mode": "direct",
        "X-Tx-Hash": pay_tx_hash.hex(),
    },
)
data = resp.json()
print(f"\nStatus: {data.get('status')}")
print(f"Summary: {data.get('summary')}")
```

### Script B — Prepaid Deposit (Bulk Usage)

Deposit once, then make many API calls without paying each time.

```python
"""
agentWay — Prepaid Deposit Example
Deposit 1 USDT (= 100 API calls), then query football markets.
Dependencies: pip install web3 httpx
"""

import time
import httpx
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

# ── Configuration ────────────────────────────────────────────────
PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE"          # BSC wallet private key
API_BASE_URL = "http://localhost:8000"            # agentWay API base URL
DEPOSIT_AMOUNT = 10**18                           # 1 USDT = 100 API calls

# Constants (do not change)
BSC_RPC = "https://bsc-dataseed.binance.org/"
CONTRACT_ADDRESS = "0x497579f445eA3707D0fE84C6bd2408620D384a4C"
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
CHAIN_ID = 56

# Minimal ABIs
ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PAYMENT_ABI = [
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ── Setup ────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(BSC_RPC))
account = Account.from_key(PRIVATE_KEY)
wallet_address = account.address
print(f"Wallet: {wallet_address}")

usdt = w3.eth.contract(address=Web3.to_checksum_address(USDT_ADDRESS), abi=ERC20_ABI)
contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=PAYMENT_ABI)

# ── Step 1: Approve USDT ────────────────────────────────────────
allowance = usdt.functions.allowance(wallet_address, CONTRACT_ADDRESS).call()
if allowance < DEPOSIT_AMOUNT:
    print(f"Approving {DEPOSIT_AMOUNT / 10**18} USDT...")
    tx = usdt.functions.approve(CONTRACT_ADDRESS, DEPOSIT_AMOUNT).build_transaction({
        "from": wallet_address,
        "nonce": w3.eth.get_transaction_count(wallet_address),
        "gas": 60000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Approved. tx: {tx_hash.hex()}")

# ── Step 2: Call deposit() on the contract ───────────────────────
print(f"Depositing {DEPOSIT_AMOUNT / 10**18} USDT...")
tx = contract.functions.deposit(DEPOSIT_AMOUNT).build_transaction({
    "from": wallet_address,
    "nonce": w3.eth.get_transaction_count(wallet_address),
    "gas": 100000,
    "gasPrice": w3.eth.gas_price,
    "chainId": CHAIN_ID,
})
signed = account.sign_transaction(tx)
deposit_tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(deposit_tx_hash)
print(f"Deposit confirmed. tx: {deposit_tx_hash.hex()}")

# ── Step 3: Wait for the background scanner ─────────────────────
print("Waiting 20s for the deposit scanner to pick up the deposit...")
time.sleep(20)

# ── Step 4: Sign auth message ────────────────────────────────────
timestamp = int(time.time())
message = f"agentway:{timestamp}"
msg_hash = encode_defunct(text=message)
signature = account.sign_message(msg_hash).signature.hex()

# ── Step 5: Call the API (prepaid mode) ──────────────────────────
print("Calling /football/markets ...")
resp = httpx.get(
    f"{API_BASE_URL}/football/markets",
    params={"limit": 5},
    headers={
        "X-Wallet-Address": wallet_address,
        "X-Signature": f"0x{signature}",
        "X-Message": message,
        "X-Payment-Mode": "prepaid",
    },
)
data = resp.json()
print(f"\nStatus: {data.get('status')}")
print(f"Summary: {data.get('summary')}")

# NOTE: After this initial deposit, you only need Script C below
# for subsequent API calls — no more on-chain transactions needed
# until your balance runs out.
```

### Script C — Subsequent Calls (Prepaid, No Payment Needed)

After depositing (Script B), use this minimal script for every subsequent API call. No on-chain transaction required.

```python
"""
agentWay — Subsequent API Call (prepaid mode)
Use this after you've already deposited USDT via Script B.
Dependencies: pip install web3 httpx
"""

import time
import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

# ── Configuration ────────────────────────────────────────────────
PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE"          # BSC wallet private key
API_BASE_URL = "http://localhost:8000"            # agentWay API base URL

# ── Sign and call ────────────────────────────────────────────────
account = Account.from_key(PRIVATE_KEY)
wallet_address = account.address

timestamp = int(time.time())
message = f"agentway:{timestamp}"
signature = account.sign_message(encode_defunct(text=message)).signature.hex()

resp = httpx.get(
    f"{API_BASE_URL}/football/markets",
    params={"limit": 10, "league": "premier_league"},
    headers={
        "X-Wallet-Address": wallet_address,
        "X-Signature": f"0x{signature}",
        "X-Message": message,
        "X-Payment-Mode": "prepaid",
    },
)
data = resp.json()
print(f"Status: {data.get('status')}")
print(f"Summary: {data.get('summary')}")
```

---

## Browser / JavaScript Examples

> **Security tip**: You don't need to use your main wallet. Create a fresh wallet,
> transfer just 0.1–1 USDT + a tiny amount of BNB for gas, and use that.
> If the wallet is ever compromised, your loss is minimal.
> You can create a new disposable wallet for every session.

> **Dependency**: [ethers.js v6](https://docs.ethers.org/v6/) — load via CDN or npm:
> ```html
> <script src="https://cdnjs.cloudflare.com/ajax/libs/ethers/6.13.4/ethers.min.js"></script>
> ```
> Or: `npm install ethers`

### Step 1: Connect Wallet (choose one)

Before running any script below, create a `signer` using **one** of these two options. All subsequent scripts use `signer` identically regardless of which option you chose.

**Option A — MetaMask (browser wallet)**

```javascript
// Requires MetaMask or any injected EIP-1193 wallet
const provider = new ethers.BrowserProvider(window.ethereum);
await provider.send("eth_requestAccounts", []);

// Switch to BSC if needed
await window.ethereum.request({
  method: "wallet_switchEthereumChain",
  params: [{ chainId: "0x38" }],  // 56 in hex
});

const signer = await provider.getSigner();
console.log("Wallet:", await signer.getAddress());
```

**Option B — Private Key (paste directly)**

```javascript
const PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE";
const BSC_RPC = "https://bsc-dataseed.binance.org/";

const provider = new ethers.JsonRpcProvider(BSC_RPC);
const signer = new ethers.Wallet(PRIVATE_KEY, provider);
console.log("Wallet:", signer.address);
```

---

### Script D — Direct Payment (Browser)

Use this when you want to pay-per-call. Each call costs 0.01 USDT on BSC. Uses `signer` from Step 1.

```javascript
/**
 * agentWay — Direct Payment (Browser)
 * Pay 0.01 USDT per call, then query football markets.
 * Prerequisite: run Step 1 above to create `signer`.
 */

// ── Constants ───────────────────────────────────────────────────
const API_BASE_URL = "http://localhost:8000";
const CONTRACT_ADDRESS = "0x497579f445eA3707D0fE84C6bd2408620D384a4C";
const USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955";
const PAYMENT_AMOUNT = ethers.parseUnits("0.01", 18);  // 0.01 USDT

// ── Minimal ABIs ────────────────────────────────────────────────
const ERC20_ABI = [
  "function approve(address spender, uint256 amount) returns (bool)",
  "function allowance(address owner, address spender) view returns (uint256)",
];

const PAYMENT_ABI = [
  "function pay()",
];

// ── Setup contracts ─────────────────────────────────────────────
const walletAddress = await signer.getAddress();
const usdt = new ethers.Contract(USDT_ADDRESS, ERC20_ABI, signer);
const contract = new ethers.Contract(CONTRACT_ADDRESS, PAYMENT_ABI, signer);

// ── Step 1: Approve USDT (skip if already approved) ─────────────
const allowance = await usdt.allowance(walletAddress, CONTRACT_ADDRESS);
if (allowance < PAYMENT_AMOUNT) {
  console.log("Approving USDT spend...");
  const approveTx = await usdt.approve(CONTRACT_ADDRESS, PAYMENT_AMOUNT * 100n);
  await approveTx.wait();
  console.log("Approved. tx:", approveTx.hash);
}

// ── Step 2: Call pay() on the contract ──────────────────────────
console.log("Calling pay() — 0.01 USDT...");
const payTx = await contract.pay();
const receipt = await payTx.wait();
console.log("Payment confirmed. tx:", payTx.hash);

// ── Step 3: Sign auth message ───────────────────────────────────
const timestamp = Math.floor(Date.now() / 1000);
const message = `agentway:${timestamp}`;
const signature = await signer.signMessage(message);

// ── Step 4: Call the API ────────────────────────────────────────
console.log("Calling /football/markets ...");
const resp = await fetch(
  `${API_BASE_URL}/football/markets?limit=5`,
  {
    headers: {
      "X-Wallet-Address": walletAddress,
      "X-Signature": signature,
      "X-Message": message,
      "X-Payment-Mode": "direct",
      "X-Tx-Hash": payTx.hash,
    },
  }
);
const data = await resp.json();
console.log("Status:", data.status);
console.log("Summary:", data.summary);
```

### Script E — Prepaid Deposit (Browser)

Deposit once, then make many API calls without paying each time. Uses `signer` from Step 1.

```javascript
/**
 * agentWay — Prepaid Deposit (Browser)
 * Deposit 1 USDT (= 100 API calls), then query football markets.
 * Prerequisite: run Step 1 above to create `signer`.
 */

// ── Constants ───────────────────────────────────────────────────
const API_BASE_URL = "http://localhost:8000";
const CONTRACT_ADDRESS = "0x497579f445eA3707D0fE84C6bd2408620D384a4C";
const USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955";
const DEPOSIT_AMOUNT = ethers.parseUnits("1", 18);  // 1 USDT = 100 calls

// ── Minimal ABIs ────────────────────────────────────────────────
const ERC20_ABI = [
  "function approve(address spender, uint256 amount) returns (bool)",
  "function allowance(address owner, address spender) view returns (uint256)",
];

const PAYMENT_ABI = [
  "function deposit(uint256 amount)",
];

// ── Setup contracts ─────────────────────────────────────────────
const walletAddress = await signer.getAddress();
const usdt = new ethers.Contract(USDT_ADDRESS, ERC20_ABI, signer);
const contract = new ethers.Contract(CONTRACT_ADDRESS, PAYMENT_ABI, signer);

// ── Step 1: Approve USDT ────────────────────────────────────────
const allowance = await usdt.allowance(walletAddress, CONTRACT_ADDRESS);
if (allowance < DEPOSIT_AMOUNT) {
  console.log(`Approving ${ethers.formatUnits(DEPOSIT_AMOUNT, 18)} USDT...`);
  const approveTx = await usdt.approve(CONTRACT_ADDRESS, DEPOSIT_AMOUNT);
  await approveTx.wait();
  console.log("Approved. tx:", approveTx.hash);
}

// ── Step 2: Call deposit() on the contract ──────────────────────
console.log(`Depositing ${ethers.formatUnits(DEPOSIT_AMOUNT, 18)} USDT...`);
const depositTx = await contract.deposit(DEPOSIT_AMOUNT);
await depositTx.wait();
console.log("Deposit confirmed. tx:", depositTx.hash);

// ── Step 3: Wait for the background scanner ─────────────────────
console.log("Waiting 20s for the deposit scanner...");
await new Promise(resolve => setTimeout(resolve, 20000));

// ── Step 4: Sign auth message ───────────────────────────────────
const timestamp = Math.floor(Date.now() / 1000);
const message = `agentway:${timestamp}`;
const signature = await signer.signMessage(message);

// ── Step 5: Call the API (prepaid mode) ─────────────────────────
console.log("Calling /football/markets ...");
const resp = await fetch(
  `${API_BASE_URL}/football/markets?limit=5`,
  {
    headers: {
      "X-Wallet-Address": walletAddress,
      "X-Signature": signature,
      "X-Message": message,
      "X-Payment-Mode": "prepaid",
    },
  }
);
const data = await resp.json();
console.log("Status:", data.status);
console.log("Summary:", data.summary);

// NOTE: After this initial deposit, you only need Script F below
// for subsequent API calls — no more on-chain transactions needed
// until your balance runs out.
```

### Script F — Subsequent Calls (Browser)

After depositing (Script E), use this minimal script for every subsequent API call. No on-chain transaction required. Uses `signer` from Step 1.

```javascript
/**
 * agentWay — Subsequent API Call (Browser, prepaid mode)
 * Use this after you've already deposited USDT via Script E.
 * Prerequisite: run Step 1 above to create `signer`.
 */

const API_BASE_URL = "http://localhost:8000";
const walletAddress = await signer.getAddress();

// ── Sign and call ───────────────────────────────────────────────
const timestamp = Math.floor(Date.now() / 1000);
const message = `agentway:${timestamp}`;
const signature = await signer.signMessage(message);

const resp = await fetch(
  `${API_BASE_URL}/football/markets?limit=10&league=premier_league`,
  {
    headers: {
      "X-Wallet-Address": walletAddress,
      "X-Signature": signature,
      "X-Message": message,
      "X-Payment-Mode": "prepaid",
    },
  }
);
const data = await resp.json();
console.log("Status:", data.status);
console.log("Summary:", data.summary);
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
git clone https://github.com/happycryptochillguy-star/agentCrab.git
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
