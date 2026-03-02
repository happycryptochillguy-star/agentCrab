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
| `deposit(amount_usdt)` | Deposit to agentCrab | Free |
| `deposit_to_polymarket(amount_usdt)` | Deposit to Polymarket | 0.01 USDT |

### Market Data

| Method | Description | Cost |
|--------|-------------|------|
| `search(query, tag, category)` | Search events | 0.01 USDT |
| `browse(category, mood)` | Browse events | 0.01 USDT |
| `get_event(event_id)` | Get single event | 0.01 USDT |
| `get_market(market_id)` | Get single market | 0.01 USDT |
| `get_orderbook(token_id)` | Get orderbook | 0.01 USDT |
| `get_price(token_id)` | Get price | 0.01 USDT |

### Positions & History

| Method | Description | Cost |
|--------|-------------|------|
| `get_positions()` | Your positions | 0.01 USDT |
| `get_trades(limit, offset)` | Your trades | 0.01 USDT |
| `get_leaderboard(limit, offset)` | Leaderboard | 0.01 USDT |

### Trading (requires `setup_trading()` first)

| Method | Description | Cost |
|--------|-------------|------|
| `setup_trading()` | Deploy Safe + approvals + creds | 0.01-0.03 USDT |
| `set_credentials(key, secret, passphrase)` | Manual cred set | Free |
| `buy(token_id, size, price)` | Buy shares | 0.01 USDT |
| `sell(token_id, size, price)` | Sell shares | 0.01 USDT |
| `cancel_order(order_id)` | Cancel order | 0.01 USDT |
| `cancel_all_orders()` | Cancel all | 0.01 USDT |
| `get_open_orders(market)` | Open orders | 0.01 USDT |

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
from agentcrab import AgentCrabError, InsufficientBalance, SetupRequired

try:
    result = client.buy(token_id, size=5.0, price=0.65)
except SetupRequired:
    client.setup_trading()
    result = client.buy(token_id, size=5.0, price=0.65)
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
