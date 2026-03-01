# Placing Orders

Orders follow the prepare → sign → submit pattern.

```python
# ── 1. Prepare order (free) ──
# Server builds EIP-712 typed data, fetches tick size and fees
resp = httpx.post(f"{API}/trading/prepare-order",
    json={"token_id": "...", "side": "BUY", "size": 5.0, "price": 0.65},
    headers=auth_headers())
data = resp.json()["data"]
# data["summary"] = "Order ready: BUY 5 shares of "Yes" on "Will X?" @ $0.65 ($3.25 total)"

# ── 2. Sign EIP-712 typed data ──
td = data["typed_data"]
sig = Account.sign_typed_data(
    PRIVATE_KEY, td["domain"], td["types"], td["message"]
).signature.hex()

# ── 3. Submit order (paid, 0.01 USDT) ──
trade_headers = {
    **auth_headers(),
    "X-Poly-Api-Key": api_key,
    "X-Poly-Secret": secret,
    "X-Poly-Passphrase": passphrase,
}
resp = httpx.post(f"{API}/trading/submit-order",
    json={"signature": f"0x{sig}", "clob_order": data["clob_order"], "order_type": "GTC"},
    headers=trade_headers)
# resp.json()["summary"] = "Order filled: bought 5 shares for $3.25 USDC."
```

## Order Types

| Type | Behavior |
|------|----------|
| `GTC` | Limit order — stays open until filled or cancelled |
| `FOK` | Fill-or-kill — fill entirely at price or cancel |
| `FAK` | Fill-and-kill — fill what's available, cancel rest |
| `GTD` | Good-till-date — limit with expiration |

## Cancel Orders

```python
# Cancel single order
httpx.delete(f"{API}/trading/order/{order_id}", headers=trade_headers)

# Cancel all open orders
httpx.delete(f"{API}/trading/orders", headers=trade_headers)

# View open orders
httpx.get(f"{API}/trading/orders", headers=trade_headers)
```
