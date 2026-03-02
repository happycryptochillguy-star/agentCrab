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
# markets[0].volume = 738665116.0   ← numeric, easy to compare/sort
# markets[0].outcomes = [
#   {"outcome": "Yes", "price": 0.65, "token_id": "71321...", "condition_id": "0xabc..."},
#   {"outcome": "No",  "price": 0.35, "token_id": "81922...", "condition_id": "0xabc..."}
# ]
token_id = markets[0].outcomes[0]["token_id"]  # pick the outcome you want
```

## Quick Start: Find & Trade

```python
# find_tradeable() does the heavy lifting — finds a liquid market in one call
market, outcome, orderbook = client.find_tradeable("bitcoin")
# market.title = "Bitcoin above $200k?"
# outcome = {"outcome": "Yes", "price": 0.65, "token_id": "71321..."}
# orderbook.best_bid = "0.64", orderbook.best_ask = "0.66"

client.setup_trading()
result = client.buy(outcome["token_id"], size=5.0, price=float(orderbook.best_ask))
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
# price.midpoint, price.last_trade_price are most reliable
# price.best_bid/best_ask may be None for some markets

# 4. Setup trading (once per session — credentials are in-memory only)
from agentcrab import SetupRequired
try:
    result = client.buy(yes_token, size=5.0, price=0.65)
except SetupRequired:
    client.setup_trading()  # deploys Safe + approvals + L2 creds
    result = client.buy(yes_token, size=5.0, price=0.65)
# result.order_id, result.status, result.success
```

**Note:** `setup_trading()` stores L2 credentials in memory. Call it once per session. On repeat sessions it only re-derives credentials (Safe + approvals are already on-chain), costing 0.01 USDT.

## All Methods

### Balance & Payment

```python
client.get_balance() → Balance
#   .calls_remaining (int), .remaining_wei (str)

client.deposit(amount_usdt=1.0) → DepositResult
#   .tx_hashes (list[str]), .summary (str)

client.deposit_to_polymarket(amount_usdt=5.0) → DepositResult
#   Deposits USDT to Polymarket trading balance (BSC → Polygon)
#   Note: funds may take 1-2 minutes to appear in CLOB trading balance.
#   Wait before placing orders after depositing.
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
#   .event_id, .title, .slug, .volume (float), .end_date, .tags, .image
#   .condition_id (str, for use with get_market)
#   .outcomes = [{"outcome": "Yes", "price": 0.65, "token_id": "...", "condition_id": "..."}, ...]
```

### Find Tradeable Market (convenience)

```python
market, outcome, orderbook = client.find_tradeable("bitcoin")
market, outcome, orderbook = client.find_tradeable(mood="trending")
market, outcome, orderbook = client.find_tradeable("nba", category="sports", price_range=(0.2, 0.8))
# Searches markets, picks the highest-volume outcome with an active orderbook.
# Returns (Market, outcome_dict, Orderbook) ready for trading.
# Raises AgentCrabError if no tradeable market found.
# Cost: 1 search/browse call + 1 orderbook call per candidate checked.
```

### Orderbook & Price (0.01 USDT each)

```python
client.get_orderbook("token_id") → Orderbook
#   .bids (desc), .asks (asc), .best_bid, .best_ask, .spread, .midpoint

client.get_price("token_id") → Price
#   .midpoint, .last_trade_price  ← most reliable
#   .best_bid, .best_ask          ← may be None for some markets
#   .spread
```

### Trading (0.01 USDT each, requires setup_trading)

```python
client.setup_trading() → SetupResult          # once per session
#   .safe_address, .api_key, .secret, .passphrase

client.buy(token_id, size=5.0, price=0.65) → OrderResult
client.sell(token_id, size=5.0, price=0.70) → OrderResult
#   .order_id, .status, .success, .taking_amount, .making_amount, .tx_hash
#   Min order: 5 shares. Price must be 0.01–0.99.

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
    # e.message has details (min 5 shares, price must be 0.01-0.99, etc.)
except AgentCrabError as e:
    # e.error_code, e.message
```

All return types have `.raw` dict with the full server response if you need more fields.
