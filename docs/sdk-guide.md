# Python SDK Guide

## Install & Init

```python
pip install agentcrab
from agentcrab import AgentCrab

# With existing key:
client = AgentCrab("https://api.agentcrab.ai/polymarket", "0xPRIVATE_KEY")

# Create new wallet (no key needed):
wallet = AgentCrab.create_wallet("https://api.agentcrab.ai/polymarket")
# → {"address": "0x...", "private_key": "0x..."}
# Tell human to send USDT + BNB (gas) to this address on BSC.
```

## Key Concept: token_id

`search()` / `browse()` → returns `Market` objects → each has `.outcomes` list → each outcome has `token_id`.

Use `token_id` for: `get_orderbook()`, `get_price()`, `buy()`, `sell()`, `set_stop_loss()`, `set_take_profit()`.

```python
markets = client.search("bitcoin")
# markets[0].title = "Bitcoin above $200k by June?"
# markets[0].outcomes = [
#   {"outcome": "Yes", "price": 0.65, "token_id": "71321..."},
#   {"outcome": "No",  "price": 0.35, "token_id": "81922..."}
# ]
token_id = markets[0].outcomes[0]["token_id"]  # pick the outcome you want
```

## Typical Flow

```python
# 1. Check balance
bal = client.get_balance()
if bal.calls_remaining == 0:
    client.deposit(1.0)  # deposit 1 USDT (= 100 calls)

# 2. Find a market
markets = client.search("bitcoin")
market = markets[0]
yes_token = market.outcomes[0]["token_id"]

# 3. Check price
price = client.get_price(yes_token)
# price.best_bid, price.best_ask, price.midpoint

# 4. Setup trading (one-time)
from agentcrab import SetupRequired
try:
    result = client.buy(yes_token, size=5.0, price=0.65)
except SetupRequired:
    client.setup_trading()  # deploys Safe + approvals + L2 creds
    result = client.buy(yes_token, size=5.0, price=0.65)
# result.order_id, result.status, result.success
```

## All Methods

### Balance & Payment

```python
client.get_balance() → Balance
#   .calls_remaining (int), .remaining_wei (str)

client.deposit(amount_usdt=1.0) → DepositResult
#   .tx_hashes (list[str]), .summary (str)

client.deposit_to_polymarket(amount_usdt=5.0) → DepositResult
#   Deposits USDT to Polymarket trading balance (BSC → Polygon)
```

### Search & Browse (0.01 USDT each)

```python
client.search("bitcoin") → list[Market]
client.search("Trump", category="crypto") → list[Market]
client.browse(category="sports.nba") → list[Market]
client.browse(mood="trending") → list[Market]
client.get_event("event_id") → Market
client.get_market("market_id") → dict

# Market fields:
#   .event_id, .title, .slug, .volume, .end_date, .tags, .image
#   .outcomes = [{"outcome": "Yes", "price": 0.65, "token_id": "..."}, ...]
```

### Orderbook & Price (0.01 USDT each)

```python
client.get_orderbook("token_id") → Orderbook
#   .bids, .asks, .best_bid, .best_ask, .spread, .midpoint

client.get_price("token_id") → Price
#   .best_bid, .best_ask, .midpoint, .spread, .last_trade_price
```

### Trading (0.01 USDT each, requires setup_trading)

```python
client.setup_trading() → SetupResult          # one-time
#   .safe_address, .api_key, .secret, .passphrase

client.buy(token_id, size=5.0, price=0.65) → OrderResult
client.sell(token_id, size=5.0, price=0.70) → OrderResult
#   .order_id, .status, .success, .taking_amount, .making_amount, .tx_hash

client.cancel_order("order_id") → dict
client.cancel_all_orders() → dict
client.get_open_orders() → list[dict]
```

### Batch Orders (N x 0.01 USDT)

```python
result = client.batch_order([
    {"token_id": "...", "side": "BUY", "size": 5.0, "price": 0.65},
    {"token_id": "...", "side": "SELL", "size": 3.0, "price": 0.70},
])
# result.success_count, result.fail_count, result.results
```

### Stop Loss / Take Profit (0.01 USDT each)

```python
client.set_stop_loss(token_id, trigger_price=0.30, size=5.0, exit_price=0.29)
client.set_take_profit(token_id, trigger_price=0.80, size=5.0, exit_price=0.79)
# → TriggerResult: .trigger_id, .status

client.get_triggers() → list[Trigger]
#   .trigger_id, .token_id, .trigger_type, .trigger_price, .status

client.cancel_trigger("trigger_id") → dict
client.cancel_all_triggers() → dict
```

Trigger logic:

| Position | Type | Fires when |
|----------|------|-----------|
| Long (sell to exit) | stop_loss | price <= trigger_price |
| Long (sell to exit) | take_profit | price >= trigger_price |
| Short (buy to exit) | stop_loss | price >= trigger_price |
| Short (buy to exit) | take_profit | price <= trigger_price |

### Positions & History (0.01 USDT each)

```python
client.get_positions() → list[Position]
#   .token_id, .outcome, .size, .question, .avg_price, .current_price, .pnl

client.get_trades() → list[Trade]
#   .side, .size, .price, .outcome, .timestamp

client.get_leaderboard() → list[dict]
```

## Error Handling

```python
from agentcrab import AgentCrabError, InsufficientBalance, SetupRequired, OrderError

try:
    result = client.buy(token_id, size=5.0, price=0.65)
except SetupRequired:
    client.setup_trading()
    result = client.buy(token_id, size=5.0, price=0.65)
except InsufficientBalance:
    # Tell human: "Balance is 0, need to deposit USDT first"
except OrderError as e:
    # e.message has details (min size $1, invalid price, etc.)
except AgentCrabError as e:
    # e.error_code, e.message
```

All return types have `.raw` dict with the full server response if you need more fields.
