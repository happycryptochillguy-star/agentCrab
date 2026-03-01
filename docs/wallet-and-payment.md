# Wallet & Payment Setup

## Create Wallet

**Option A — API call (recommended, works for all agents):**
```
POST /agent/create-wallet
```
No auth needed. Returns:
```json
{"address": "0x...", "private_key": "0x..."}
```
Save the private key securely — it controls both BSC (payment) and Polygon (trading) wallets.

**Option B — Local Python (if your agent can execute code):**
```python
from eth_account import Account
acct = Account.create()
private_key = acct.key.hex()   # 0x-prefixed
address = acct.address
```

After creating a wallet, tell the human: "Your wallet address is `0xABC...`. You need to send USDT + a small amount of BNB (for gas) to this address on BSC before using paid features."

**Important**: Private keys must always start with `0x`. If the human provides a key without the prefix, add it.

## Payment Setup

Every agentCrab API call costs 0.01 USDT on BSC. Two modes:

### Prepaid (deposit once, use many — recommended)

```python
# 1. Build unsigned deposit tx(s)
resp = httpx.post(f"{API}/payment/prepare-deposit",
    json={"amount_usdt": 1.0},  # 1 USDT = 100 calls
    headers=auth_headers())

# 2. Sign and submit
sign_and_submit(resp.json()["data"])

# 3. Check balance anytime
resp = httpx.get(f"{API}/payment/balance", headers=auth_headers())
```

### Direct (pay per call)

```python
# 1. Build unsigned pay tx
resp = httpx.post(f"{API}/payment/prepare-pay", headers=auth_headers())

# 2. Sign and submit
result = sign_and_submit(resp.json()["data"])
tx_hash = result.json()["data"]["tx_hashes"][-1]

# 3. Use tx_hash in X-Tx-Hash header for the next paid API call
```

## Polymarket Deposit

Fund the Polymarket trading account (USDT on BSC → USDC.e on Polygon):

```python
# 1. Build unsigned deposit tx
resp = httpx.post(f"{API}/deposit/prepare-transfer",
    json={"amount_usdt": 10.0},
    headers=auth_headers())

# 2. CONFIRM WITH THE HUMAN before signing
# 3. Sign and submit
sign_and_submit(resp.json()["data"])
```
