# Enable Trading (one-time setup)

Before placing orders, complete this one-time setup. All Polygon operations are **gasless** — no MATIC needed.

## Step 1: Deploy Safe wallet

```
POST /trading/prepare-deploy-safe
Headers: auth headers
```

Response `data.already_deployed`:
- `true` → skip to Step 2
- `false` → response includes `typed_data`. Sign it (EIP-712):

```python
td = data["typed_data"]
sig = "0x" + Account.sign_typed_data(
    PRIVATE_KEY, td["domain"], td["types"], td["message"]
).signature.hex()
```

Submit (0.01 USDT):
```
POST /trading/submit-deploy-safe
Headers: auth headers
Body: {"signature": "0xSIG"}
```

## Step 2: Get approval + credential data

```
POST /trading/prepare-enable
Headers: auth headers
```

Response includes:
- `approvals_needed` — whether token approvals are required
- `approval_data` — SafeTx hash to sign (if approvals needed)
- `clob_typed_data` — EIP-712 data for L2 credentials

## Step 3: Submit token approvals (if needed)

Only if `approvals_needed` is `true`. Sign the SafeTx hash (personal_sign):

```python
from hexbytes import HexBytes
ah = data["approval_data"]["hash"]
sig = "0x" + account.sign_message(encode_defunct(HexBytes(ah))).signature.hex()
```

Submit (0.01 USDT):
```
POST /trading/submit-approvals
Headers: auth headers
Body: {"signature": "0xSIG", "approval_data": <approval_data from step 2>}
```

## Step 4: Derive L2 credentials

Sign the CLOB typed data (EIP-712):

```python
ct = data["clob_typed_data"]
sig = "0x" + Account.sign_typed_data(
    PRIVATE_KEY, ct["domain"], ct["types"], ct["message"]
).signature.hex()
```

Submit (0.01 USDT):
```
POST /trading/submit-credentials
Headers: auth headers
Body: {"signature": "0xSIG", "timestamp": "<from clob_typed_data.message.timestamp>"}
```

Response includes L2 credentials:
```json
{"api_key": "...", "secret": "...", "passphrase": "..."}
```

**Save these — they don't expire.** Include them as headers in all trading requests:

| Header | Value |
|--------|-------|
| `X-Poly-Api-Key` | api_key |
| `X-Poly-Secret` | secret |
| `X-Poly-Passphrase` | passphrase |
