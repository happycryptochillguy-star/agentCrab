# agentCrab — AI Middleware for Polymarket

Simple HTTP API that gives any AI agent full Polymarket access: browse markets, deposit, trade, check positions. Every response has a `summary` you can relay to the human.

**Pricing**: 0.01 USDT/call on BSC &nbsp;|&nbsp; **Base URL**: `http://localhost:8000/polymarket` (local) or `https://api.agentcrab.ai/polymarket` (production)

---

## Agent Rules

**Be reactive, not proactive.**
- NEVER call any API unless the human explicitly asks
- After any step completes, STOP and wait for the human's next request
- Be concise. No jargon. Show results, not process. Don't narrate code.
- Don't skip payment confirmation for on-chain transactions

---

## Guides (load only when needed)

| Guide | When to load | File |
|-------|-------------|------|
| Auth & Signing | Before your first API call — how to build auth headers and sign transactions | [docs/auth-and-signing.md](docs/auth-and-signing.md) |
| Wallet & Payment | Human wants to create a wallet or set up payment | [docs/wallet-and-payment.md](docs/wallet-and-payment.md) |
| Enable Trading | Human wants to place their first trade (one-time setup) | [docs/enable-trading.md](docs/enable-trading.md) |
| Place Orders | Human wants to buy/sell on a market | [docs/place-orders.md](docs/place-orders.md) |

---

## Market Browsing & Search

The most common operation. Markets are organized in a hierarchical category system. All queries hit Polymarket in real-time — new events appear automatically.

### Quick start

**1. Discover categories** (free):
```
GET /markets/categories
```
Returns: `politics`, `sports`, `crypto`, `pop_culture`, `tech`, `finance`, `world` — each with subcategories.

**2. Browse** (0.01 USDT):
```
GET /markets/browse?category=sports.nba&limit=10
GET /markets/browse?category=crypto.bitcoin
GET /markets/browse?category=sports.soccer.epl
```

**3. Search** (0.01 USDT):
```
GET /markets/search?query=bitcoin
GET /markets/search?query=Trump&category=crypto
```

**4. Historical events** (0.01 USDT) — closed events with resolution data:
```
GET /markets/history?query=bitcoin&limit=5
GET /markets/history?category=politics
```

### Human says → You call

| Human says | API call |
|-----------|---------|
| "Show me NBA markets" | `GET /markets/browse?category=sports.nba` |
| "Find Trump crypto markets" | `GET /markets/search?query=Trump&category=crypto` |
| "What categories are there?" | `GET /markets/categories` |
| "Search for bitcoin" | `GET /markets/search?query=bitcoin` |
| "Show me EPL matches" | `GET /markets/browse?category=sports.soccer.epl` |
| "What are the hottest markets?" | `GET /markets/browse?category=politics&limit=5` |
| "Show past bitcoin events" | `GET /markets/history?query=bitcoin` |
| "What political events resolved?" | `GET /markets/history?category=politics` |

### Category paths

Use dot-separated paths: `{top}`, `{top}.{sub}`, or `{top}.{sub}.{subsub}`.

| Path | Markets |
|------|---------|
| `sports` | All sports |
| `sports.nba` | NBA / basketball |
| `sports.soccer.epl` | English Premier League |
| `sports.soccer.ucl` | Champions League |
| `sports.f1` | Formula 1 |
| `politics` | All politics |
| `politics.trump` | Trump-related |
| `politics.geopolitics.ukraine` | Ukraine / Russia |
| `politics.economy.fed` | Federal Reserve |
| `crypto` | All crypto |
| `crypto.bitcoin` | Bitcoin |
| `crypto.memecoins` | Memecoins |
| `pop_culture.tweets` | Tweet markets |
| `tech.ai` | AI markets |

---

## Category Leaderboard

See who's best at what. Data synced every 4 hours from top 200 global traders.

### Quick start

**1. Top traders in a category** (0.01 USDT):
```
GET /traders/categories/leaderboard?category=crypto&limit=5
GET /traders/categories/leaderboard?category=sports.nba&sort_by=win_rate
GET /traders/categories/leaderboard?category=politics.trump&sort_by=pnl
```

**2. Trader's category breakdown** (0.01 USDT):
```
GET /traders/categories/{address}/profile
GET /traders/categories/{address}/profile?category=sports.nba
```

**3. Category stats** (0.01 USDT):
```
GET /traders/categories/stats?category=crypto
GET /traders/categories/stats?category=sports
```

### Human says -> You call

| Human says | API call |
|-----------|---------|
| "Who's best at crypto?" | `GET /traders/categories/leaderboard?category=crypto` |
| "Top NBA bettors" | `GET /traders/categories/leaderboard?category=sports.nba` |
| "Sort by win rate in EPL" | `GET /traders/categories/leaderboard?category=sports.soccer.epl&sort_by=win_rate` |
| "Show me this trader's strengths" | `GET /traders/categories/{addr}/profile` |
| "How competitive is politics?" | `GET /traders/categories/stats?category=politics` |

---

## All Endpoints

### Free (no payment)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agent/create-wallet` | Create new wallet (returns address + private key) |
| GET | `/agent/capabilities` | Full machine-readable API reference |
| GET | `/markets/categories` | Category taxonomy |
| GET | `/markets/tags` | Raw Polymarket tags |
| GET | `/payment/balance` | Prepaid balance (auth required) |
| POST | `/payment/prepare-deposit` | Build deposit tx (auth) |
| POST | `/payment/prepare-pay` | Build pay tx (auth) |
| POST | `/payment/submit-tx` | Broadcast signed tx (auth) |
| POST | `/trading/prepare-deploy-safe` | Safe deployment check (auth) |
| POST | `/trading/prepare-enable` | Trading setup data (auth) |
| POST | `/trading/prepare-order` | Build order typed data (auth) |
| POST | `/markets/history/sync` | Sync historical events (auth, throttled 1h) |
| POST | `/traders/categories/sync` | Sync category leaderboard (auth, throttled 2h) |

### Paid (0.01 USDT/call)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/markets/browse` | Browse by category |
| GET | `/markets/search` | Search (query + optional category) |
| GET | `/markets/events/{id}` | Event details |
| GET | `/markets/{market_id}` | Market details |
| GET | `/markets/history` | Historical (closed) events with resolution |
| GET | `/orderbook/{token_id}` | Orderbook |
| GET | `/prices/{token_id}` | Price summary |
| GET | `/positions` | Your positions + P&L |
| GET | `/positions/trades` | Trade history |
| GET | `/traders/leaderboard` | Top traders |
| GET | `/traders/categories/leaderboard` | Category leaderboard (by category) |
| GET | `/traders/categories/{address}/profile` | Trader category breakdown |
| GET | `/traders/categories/stats` | Category aggregate stats |
| POST | `/trading/submit-deploy-safe` | Deploy Safe (gasless) |
| POST | `/trading/submit-approvals` | Token approvals (gasless) |
| POST | `/trading/submit-credentials` | Get L2 credentials |
| POST | `/trading/submit-order` | Submit order |
| DELETE | `/trading/order/{order_id}` | Cancel order |
| GET | `/trading/orders` | Open orders |
