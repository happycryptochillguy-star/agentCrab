# agentcrab

Python SDK for [agentCrab](https://agentcrab.ai) — turn any AI agent into a Polymarket assistant with 3 lines of code.

## Install

```bash
pip install agentcrab
```

## Quick Start

```python
from agentcrab import AgentCrab

client = AgentCrab("https://api.agentcrab.ai/polymarket", "0xYOUR_PRIVATE_KEY")

# Search markets
markets = client.search("bitcoin")
for m in markets:
    print(m.title, m.outcomes)

# Check balance
balance = client.get_balance()
print(f"{balance.calls_remaining} API calls remaining")
```

## Trading

```python
# One-time setup (deploys Safe + approvals + L2 credentials)
setup = client.setup_trading()
print(f"Safe: {setup.safe_address}")

# Buy shares
result = client.buy(token_id="TOKEN_ID", size=5.0, price=0.65)
print(f"Order {result.status}: {result.order_id}")

# Sell shares
result = client.sell(token_id="TOKEN_ID", size=5.0, price=0.70)

# View positions
for pos in client.get_positions():
    print(f"{pos.outcome}: {pos.size} shares, PnL: {pos.pnl}")
```

## Full API

### Balance & Payment

| Method | Description | Cost |
|--------|-------------|------|
| `get_balance()` | Prepaid balance | Free |
| `get_wallet_balance()` | BSC wallet USDT + BNB | Free |
| `get_trading_status()` | Trading setup status | Free |
| `deposit(amount_usdt)` | Deposit to agentCrab | Free |
| `deposit_to_polymarket(amount_usdt)` | Deposit to Polymarket | Free |

### Market Data

| Method | Description | Cost |
|--------|-------------|------|
| `search(query, tag, category)` | Search events | 0.01 USDT |
| `browse(category, mood)` | Browse events | 0.01 USDT |
| `get_categories()` | List market categories | Free |
| `get_event(event_id)` | Get single event | 0.01 USDT |
| `get_event_by_slug(slug)` | Get event by slug | 0.01 USDT |
| `get_market(market_id)` | Get single market | 0.01 USDT |
| `get_orderbook(token_id)` | Get orderbook | 0.01 USDT |
| `get_orderbooks_batch(token_ids)` | Batch orderbooks (up to 20) | 0.01 USDT |
| `get_price(token_id)` | Get price | 0.01 USDT |
| `get_prices_batch(token_ids)` | Batch prices (up to 20) | 0.01 USDT |
| `find_tradeable(query, category, mood)` | Find liquid market + orderbook (1 search + N orderbook calls) | 0.01+ USDT |
| `search_history(query, category)` | Search closed events | 0.01 USDT |
| `sync_history()` | Trigger closed-event sync | Free |

### Positions & History

| Method | Description | Cost |
|--------|-------------|------|
| `get_positions()` | Your positions | 0.01 USDT |
| `get_trades(limit, offset)` | Your trades | 0.01 USDT |
| `get_activity(limit, offset)` | On-chain activity | 0.01 USDT |
| `get_trader_positions(address)` | Any trader's positions | 0.01 USDT |
| `get_trader_trades(address)` | Any trader's trades | 0.01 USDT |

### Leaderboard

| Method | Description | Cost |
|--------|-------------|------|
| `get_leaderboard(limit, offset)` | Global leaderboard | 0.01 USDT |
| `get_category_leaderboard(category)` | Category leaderboard | 0.01 USDT |
| `get_trader_category_profile(address)` | Trader category breakdown | 0.01 USDT |
| `get_category_stats(category)` | Category aggregate stats | 0.01 USDT |

### Trading (auto-setup on first trade)

| Method | Description | Cost |
|--------|-------------|------|
| `setup_trading()` | Deploy Safe + approvals + creds | 0.01-0.03 USDT |
| `set_credentials(key, secret, passphrase)` | Manual cred set | Free |
| `refresh_balance()` | Refresh CLOB balance cache | Free |
| `buy(token_id, size, price)` | Buy shares | 0.01 USDT |
| `sell(token_id, size, price)` | Sell shares | 0.01 USDT |
| `batch_order(orders)` | Batch orders (max 15) | N × 0.01 USDT |
| `cancel_order(order_id)` | Cancel order | 0.01 USDT |
| `cancel_all_orders()` | Cancel all | 0.01 USDT |
| `get_open_orders(market)` | Open orders | 0.01 USDT |

### Stop Loss / Take Profit

| Method | Description | Cost |
|--------|-------------|------|
| `set_stop_loss(token_id, trigger_price, size, exit_price)` | Set stop loss | 0.01 USDT |
| `set_take_profit(token_id, trigger_price, size, exit_price)` | Set take profit | 0.01 USDT |
| `get_triggers(status, token_id)` | List triggers | Free |
| `cancel_trigger(trigger_id)` | Cancel trigger | Free |
| `cancel_all_triggers(token_id)` | Cancel all triggers | Free |

### Wallet

| Method | Description |
|--------|-------------|
| `AgentCrab.create_wallet(api_url)` | Create new wallet (static) |

## Typed Responses

All methods return typed dataclasses with a `.raw` escape hatch:

```python
balance = client.get_balance()
print(balance.calls_remaining)   # typed field
print(balance.raw)               # full server response dict
```

## Error Handling

```python
from agentcrab import AgentCrabError, InsufficientBalance

try:
    result = client.buy(token_id, size=5.0, price=0.65)
    # buy()/sell() auto-call setup_trading() if needed — no manual setup required
except InsufficientBalance as e:
    print(f"Top up: {e.message}")
except AgentCrabError as e:
    print(f"Error [{e.error_code}]: {e.message}")
```

## Dependencies

Minimal — no `web3` required:

- `eth-account` — EIP-191, EIP-712, tx signing
- `httpx` — Sync HTTP
- `hexbytes` — SafeTx hash signing

## License

MIT
