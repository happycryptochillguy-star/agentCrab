---
name: agentcrab-polymarket
description: Trade on Polymarket prediction markets — search, buy, sell, manage positions, stop loss, leaderboards. Gasless, no MATIC needed.
metadata:
  openclaw:
    requires:
      env:
        - AGENTCRAB_PRIVATE_KEY
    primaryEnv: AGENTCRAB_PRIVATE_KEY
    emoji: "🦀"
---

# AgentCrab — Polymarket Trading

Turn yourself into a full Polymarket prediction market assistant. Search markets, place trades, manage positions, set stop-losses — all through a Python SDK. No web3, no gas fees, no blockchain knowledge needed.

**Pricing**: 0.01 USDT per API call on BSC. **All Polygon operations are gasless.**

## Setup

```bash
pip install -U agentcrab
```

```python
from agentcrab import AgentCrab
import os

client = AgentCrab("https://api.agentcrab.ai/polymarket", os.environ["AGENTCRAB_PRIVATE_KEY"])
```

If the user has no wallet yet:
```python
wallet = AgentCrab.create_wallet("https://api.agentcrab.ai/polymarket")
# Tell user: "Your wallet is {wallet['address']}. Send USDT + BNB (gas, ~$0.02) to this address on BSC."
# STOP and wait for user to confirm funding.
```

## Rules

1. **Be reactive.** Only call the API when the user asks. Stop after each step and report results.
2. **Check wallet first.** No key → ask user. No balance → tell user to deposit.
3. **Tell costs upfront.** Before any paid call: "This costs 0.01 USDT."
4. **Confirm trades.** Always show order summary and ask user to confirm before executing.
5. **NEVER hardcode private keys.** Always use `os.environ["AGENTCRAB_PRIVATE_KEY"]`.

## Core Concept: token_id

`search()` / `browse()` → returns `Market` objects → each has `.outcomes` list → each outcome has a `token_id`.

Use `token_id` for: `get_orderbook()`, `get_price()`, `buy()`, `sell()`, `set_stop_loss()`, `set_take_profit()`.

## What the User Says → What You Do

| User says | You do |
|-----------|--------|
| "What's on Polymarket?" | `client.browse(mood="interesting")` |
| "Trending markets" | `client.browse(mood="trending")` |
| "Controversial bets" | `client.browse(mood="controversial")` |
| "NBA markets" | `client.browse(category="sports.nba")` |
| "Search bitcoin" | `client.search("bitcoin")` |
| "Buy Yes on this" | `client.buy(token_id, size, price)` |
| "Set stop loss at 0.30" | `client.set_stop_loss(token_id, 0.30, size, 0.29)` |
| "My positions" | `client.get_positions()` |
| "Who's best at crypto?" | `client.get_category_leaderboard("crypto")` |

## Categories

Dot-separated paths: `sports`, `sports.nba`, `sports.soccer.epl`, `politics`, `politics.trump`, `crypto`, `crypto.bitcoin`, `crypto.memecoins`, `pop_culture.tweets`, `tech.ai`.

## Moods

`trending` (highest volume), `interesting` (curated mix), `controversial` (near 50/50), `new` (recently created), `closing_soon` (ending within 7 days).

## Quick Start: Find & Trade

```python
# One-call market finder — picks highest-volume liquid market
market, outcome, orderbook = client.find_tradeable("bitcoin")
# market.title = "Bitcoin above $200k?"
# outcome = {"outcome": "Yes", "price": 0.65, "token_id": "71321..."}

# buy() auto-calls setup_trading() if needed — no manual setup
result = client.buy(outcome["token_id"], size=5.0, price=float(orderbook.best_ask))
```

## Typical Flow

```python
# 1. Check balance
bal = client.get_balance()
# bal.calls_remaining = 145      ← API calls left
# bal.trading_balance_usdc = 3.5 ← USDC on Polymarket
if bal.calls_remaining == 0:
    client.deposit(1.0)  # deposit 1 USDT = 100 calls

# 2. Find a market
markets = client.search("bitcoin")
market = markets[0]
yes_token = market.outcomes[0]["token_id"]

# 3. Check price
price = client.get_price(yes_token)
# price.midpoint, price.last_trade_price

# 4. Buy (setup_trading auto-called on first trade)
result = client.buy(yes_token, size=5.0, price=0.65)
# result.order_id, result.status, result.success
```

## All Methods

### Balance & Payment

```python
client.get_balance() → Balance
#   .calls_remaining, .remaining_usdt, .trading_balance_usdc, .safe_address

client.deposit(amount_usdt=1.0) → DepositResult       # deposit to agentCrab (API calls)
client.deposit_to_polymarket(amount_usdt=5.0)          # deposit to Polymarket (trading)
client.refresh_balance()                                # refresh CLOB cache after deposit
```

### Search & Browse (0.01 USDT each)

```python
client.search("bitcoin") → list[Market]
client.search("Trump", category="crypto") → list[Market]
client.browse(category="sports.nba") → list[Market]
client.browse(mood="trending") → list[Market]
client.get_categories() → list[dict]      # free
client.get_event("event_id") → Market
client.get_market("market_id") → dict

# Market fields: .event_id, .title, .slug, .volume, .end_date, .tags, .image
# .outcomes = [{"outcome": "Yes", "price": 0.65, "token_id": "..."}, ...]
# market.find_outcome("Warriors") → specific outcome by name
```

### Find Tradeable (convenience)

```python
market, outcome, orderbook = client.find_tradeable("bitcoin")
market, outcome, orderbook = client.find_tradeable(mood="trending")
market, outcome, orderbook = client.find_tradeable("nba", category="sports", price_range=(0.2, 0.8))
# Picks highest-volume outcome with active orderbook.
```

### Orderbook & Price (0.01 USDT each)

```python
client.get_orderbook("token_id") → Orderbook
#   .bids, .asks, .best_bid, .best_ask, .spread, .midpoint

client.get_price("token_id") → Price
#   .midpoint, .last_trade_price, .best_bid, .best_ask, .spread
```

### Trading (0.01 USDT each)

```python
client.setup_trading()                                   # once per session (auto-called by buy/sell)
client.buy(token_id, size=5.0, price=0.65) → OrderResult
client.sell(token_id, size=5.0, price=0.70) → OrderResult
#   .order_id, .status, .success
#   Price: 0.001–0.999. Auto-calls setup_trading() if needed.

client.cancel_order("order_id") → dict
client.cancel_all_orders() → dict
client.get_open_orders() → list[dict]
```

### Batch Orders (N × 0.01 USDT)

```python
result = client.batch_order([
    {"token_id": "...", "side": "BUY", "size": 5.0, "price": 0.65},
    {"token_id": "...", "side": "SELL", "size": 3.0, "price": 0.70},
])
```

### Stop Loss / Take Profit (0.01 USDT each)

```python
client.set_stop_loss(token_id, trigger_price=0.30, size=5.0, exit_price=0.29)
client.set_take_profit(token_id, trigger_price=0.80, size=5.0, exit_price=0.79)
# Optional: exit_side="BUY" (for short), expires_in_hours=24

client.get_triggers() → list[Trigger]
client.cancel_trigger("trigger_id")
client.cancel_all_triggers()
```

| Position | Type | Fires when |
|----------|------|-----------|
| Long (sell to exit) | stop_loss | price <= trigger_price |
| Long (sell to exit) | take_profit | price >= trigger_price |
| Short (buy to exit) | stop_loss | price >= trigger_price |
| Short (buy to exit) | take_profit | price <= trigger_price |

### Positions & Activity (0.01 USDT each)

```python
client.get_positions() → list[Position]
#   .token_id, .outcome, .size, .question, .avg_price, .current_price, .pnl

client.get_trades() → list[Trade]
client.get_activity(limit=50, offset=0) → list[Activity]
```

### Other Traders (0.01 USDT each)

```python
client.get_trader_positions("0xAddress") → list[Position]
client.get_trader_trades("0xAddress") → list[Trade]
```

### Leaderboard (0.01 USDT each)

```python
client.get_leaderboard() → list[dict]
client.get_category_leaderboard("crypto", sort_by="pnl", limit=20) → dict
client.get_trader_category_profile("0xAddress", category="sports") → dict
client.get_category_stats("crypto") → dict
```

### Historical Events (0.01 USDT each)

```python
client.search_history(query="bitcoin", category="crypto", limit=20) → list[HistoricalEvent]
client.sync_history() → dict   # free, throttled to 1/hour
```

### $CRAB Token & Points (free)

```python
client.get_points() → Points
#   .deposit_points, .usage_points, .total_points, .total_deposited_usdt, .total_consumed_usdt

client.get_points_leaderboard(limit=20) → dict     # no auth needed
client.get_token_info() → dict                      # no auth needed
```

Points accumulate automatically: 1 USDT deposited = 100 points, 1 API call = 1 point. Retroactive from day 1.

## Error Handling

```python
from agentcrab import AgentCrabError, InsufficientBalance, OrderError

try:
    result = client.buy(token_id, size=5.0, price=0.65)
except InsufficientBalance:
    # Tell user: "Balance is 0, deposit USDT first."
except OrderError as e:
    # e.message has details (min size, price range, etc.)
except AgentCrabError as e:
    # e.error_code, e.message
```

`buy()` / `sell()` auto-call `setup_trading()` — no need to catch `SetupRequired`.
