# Placing Orders

Orders follow the **prepare → sign → submit** pattern. Requires L2 credentials (see [Enable Trading](enable-trading.md)).

## Buy / Sell

**Step 1** — Prepare order (free):
```
POST /trading/prepare-order
Headers: auth headers
Body: {"token_id": "TOKEN_ID", "side": "BUY", "size": 5.0, "price": 0.65, "order_type": "GTC"}
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
If CLOB returns a logical failure (success: false), balance is auto-refunded.

## Order Types

| Type | Behavior |
|------|----------|
| `GTC` | Limit order — stays open until filled or cancelled |
| `FOK` | Fill-or-kill — fill entirely at price or cancel |
| `FAK` | Fill-and-kill — fill what's available, cancel rest |
| `GTD` | Good-till-date — limit with expiration |

## Batch Orders (up to 15)

**Step 1** — Prepare batch (free):
```
POST /trading/prepare-batch-order
Headers: auth headers
Body: {"orders": [{"token_id": "T1", "side": "BUY", "size": 5.0, "price": 0.65}, ...]}
```

Response includes an array of `typed_data` + `clob_order` for each order.

**Step 2** — Sign each typed_data individually (same as single orders).

**Step 3** — Submit batch (N × 0.01 USDT):
```
POST /trading/submit-batch-order
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
Body: {"orders": [{"signature": "0xSIG1", "clob_order": ..., "order_type": "GTC"}, ...]}
```

## Stop Loss / Take Profit Triggers

Triggers let you set automatic exit orders. Server monitors prices every 30s.

**Step 1** — Prepare trigger (free):
```
POST /trading/triggers/prepare
Headers: auth headers
Body: {
    "token_id": "TOKEN_ID",
    "trigger_type": "stop_loss",    // or "take_profit"
    "trigger_price": 0.40,          // price at which to trigger
    "exit_side": "SELL",            // BUY or SELL
    "size": 5.0,
    "exit_price": 0.38              // price for the exit order
}
```

**Step 2** — Sign the EIP-712 typed_data.

**Step 3** — Create trigger (0.01 USDT):
```
POST /trading/triggers/create
Headers: auth headers + X-Poly-Api-Key + X-Poly-Secret + X-Poly-Passphrase
Body: {"signature": "0xSIG", "clob_order": ..., "token_id": "...", "trigger_type": "stop_loss", "trigger_price": 0.40, "exit_side": "SELL"}
```

**Manage triggers:**
```
GET    /trading/triggers                        — List your triggers (free)
GET    /trading/triggers/{trigger_id}           — Single trigger details (free)
DELETE /trading/triggers/{trigger_id}           — Cancel a trigger (free)
DELETE /trading/triggers?token_id=TOKEN_ID      — Cancel all triggers (free)
```

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
