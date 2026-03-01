# Wallet & Payment Setup

## Create Wallet

```
POST /agent/create-wallet
```

No auth needed. Response:
```json
{
  "status": "ok",
  "summary": "Wallet created: 0xABC.... Fund with USDT + BNB on BSC to start using paid features.",
  "data": {
    "address": "0xABC...",
    "private_key": "0x123..."
  }
}
```

**After creating, tell the human:**
> Your wallet address is `0xABC...`. Please send USDT + a small amount of BNB (for gas, ~$0.02 worth) to this address on **BSC (BNB Smart Chain)**. Let me know when done.

Then **STOP and wait**. Do not proceed until the human confirms funding.

**Important**: Private keys must start with `0x`. If the human provides one without the prefix, add it.

## Payment Setup

Every paid API call costs **0.01 USDT**. Two modes:

### Prepaid (recommended) — deposit once, use many times

**Step 1** — Check current balance (free):
```
GET /payment/balance
Headers: auth headers (see auth-and-signing.md)
```

**Step 2** — If balance is 0, build deposit transaction (free):
```
POST /payment/prepare-deposit
Headers: auth headers
Body: {"amount_usdt": 1.0}
```
Response includes unsigned BSC transactions (approve + deposit).

**Step 3** — Sign and submit (see auth-and-signing.md for signing):
```
POST /payment/submit-tx
Headers: auth headers
Body: {"signed_txs": ["0xSIGNED_TX_1", "0xSIGNED_TX_2"], "chain": "bsc"}
```

**Step 4** — Verify balance:
```
GET /payment/balance
```
Should now show the deposited amount. Ready to use paid endpoints.

### Direct — pay per call

**Step 1** — Build pay transaction (free):
```
POST /payment/prepare-pay
Headers: auth headers
```

**Step 2** — Sign and submit:
```
POST /payment/submit-tx
Headers: auth headers
Body: {"signed_txs": ["0xSIGNED_TX"], "chain": "bsc"}
```

**Step 3** — Use the tx hash in the next paid API call:
```
GET /markets/search?query=bitcoin
Headers: auth headers + X-Tx-Hash: 0xTHE_TX_HASH + X-Payment-Mode: direct
```

## Polymarket Deposit

Fund the Polymarket trading account (USDT on BSC → USDC.e on Polygon):

**Step 1** — Build deposit transaction (free):
```
POST /deposit/prepare-transfer
Headers: auth headers
Body: {"amount_usdt": 10.0}
```

**Step 2** — **CONFIRM WITH THE HUMAN** before signing. Tell them:
> This will transfer 10 USDT from your BSC wallet to your Polymarket trading account. Proceed?

**Step 3** — Sign and submit:
```
POST /payment/submit-tx
Headers: auth headers
Body: {"signed_txs": ["0xSIGNED_APPROVE", "0xSIGNED_DEPOSIT"], "chain": "bsc"}
```

Funds arrive in the Polymarket account automatically (bridged from BSC to Polygon).
