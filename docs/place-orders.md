# Placing Orders

Orders follow the **prepare → sign → submit** pattern. Requires L2 credentials (see [Enable Trading](enable-trading.md)).

## Buy / Sell

**Step 1** — Prepare order (free):
```
POST /trading/prepare-order
Headers: auth headers
Body: {"token_id": "TOKEN_ID", "side": "BUY", "size": 5.0, "price": 0.65}
```

Response includes:
- `summary` — human-readable: "BUY 5 shares of 'Yes' on 'Will X happen?' @ $0.65 ($3.25 total)"
- `typed_data` — EIP-712 data to sign
- `clob_order` — order payload for submission

**Tell the human the summary and confirm before signing.**

**Step 2** — Sign (EIP-712):

```python
td = data["typed_data"]
sig = "0x" + Account.sign_typed_data(
    PRIVATE_KEY, td["domain"], td["types"], td["message"]
).signature.hex()
```

**Step 3** — Submit order (0.01 USDT):
```
POST /trading/submit-order
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
Body: {"signature": "0xSIG", "clob_order": <clob_order from step 1>, "order_type": "GTC"}
```

Response includes fill status, amounts, and polygonscan URL.

## Order Types

| Type | Behavior |
|------|----------|
| `GTC` | Limit order — stays open until filled or cancelled |
| `FOK` | Fill-or-kill — fill entirely at price or cancel |
| `FAK` | Fill-and-kill — fill what's available, cancel rest |
| `GTD` | Good-till-date — limit with expiration |

## Cancel Orders

Cancel single order (0.01 USDT):
```
DELETE /trading/order/{order_id}
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
```

Cancel all open orders (0.01 USDT):
```
DELETE /trading/orders
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
```

View open orders (0.01 USDT):
```
GET /trading/orders
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
```
