# agentCrab — AI Middleware for Polymarket

Simple HTTP API that gives any AI agent full Polymarket access: browse markets, deposit, trade, check positions.

**Pricing**: 0.01 USDT/call on BSC | **Base URL**: `https://api.agentcrab.ai/polymarket`

---

## Agent Rules (MUST follow)

**1. NEVER write code. You are an HTTP client.**
- Use your built-in HTTP tools (fetch, curl, web requests) to call the API directly
- Do NOT generate Python scripts, JavaScript files, or any standalone code
- The ONLY exception: signing transactions requires minimal inline code — see [Auth & Signing guide](docs/auth-and-signing.md)

**2. Be reactive, not proactive.**
- NEVER call any API unless the human explicitly asks
- After any step completes, STOP and wait for the human's next request
- Be concise. Show results, not process

**3. Check wallet FIRST.**
- Before ANY paid API call, you MUST have a private key. If you don't have one, immediately ask: "I need a wallet to use paid features. Do you have a private key, or should I create a new wallet for you?"
- Before ANY paid API call, check balance: `GET /payment/balance`. If zero, tell the user: "Your balance is 0. You need to deposit USDT to use paid features. Want me to set up payment?" Do NOT call any paid endpoint until balance > 0.
- NEVER attempt to transfer funds, write transfer scripts, or interact with blockchain directly. All on-chain operations go through our API.

**4. Tell human about costs upfront.**
- When the human asks something that requires a paid call, tell them IMMEDIATELY (before calling): "This requires a paid API call (0.01 USDT). You need a funded wallet first."
- Don't discover the cost after failing — tell them before trying.

---

## First Contact Flow

When the human first asks you to do anything with Polymarket:

1. **Do you have a private key?**
   - YES → go to step 2
   - NO → ask: "Do you have a BSC private key, or should I create a new wallet?"
     - Create wallet: `POST /agent/create-wallet` (free, no auth)
     - Tell human: "Your wallet is `0xABC...`. Send USDT + small BNB (for gas) to this address on BSC."
     - STOP. Wait for human to confirm they funded it.

2. **Is the request free or paid?**
   - Free requests (`/markets/categories`, `/payment/balance`, etc.) → just call it
   - Paid requests → go to step 3

3. **Check balance**: `GET /payment/balance`
   - Has balance → make the paid call
   - Zero balance → tell human: "Your balance is 0. Want me to set up prepaid deposit first?"
   - STOP. Don't call paid endpoints with zero balance.

---

## Guides (load when needed)

| Guide | When to load |
|-------|-------------|
| [Auth & Signing](docs/auth-and-signing.md) | Before your first API call — how to build headers and sign |
| [Wallet & Payment](docs/wallet-and-payment.md) | Human wants to set up payment |
| [Enable Trading](docs/enable-trading.md) | Human wants to place their first trade |
| [Place Orders](docs/place-orders.md) | Human wants to buy/sell |

---

## Market Browsing & Search

The most common operation. All responses include a `summary` field — relay it to the human.

### Quick start

**1. Discover categories** (free):
```
GET /markets/categories
```

**2. Browse by category** (0.01 USDT):
```
GET /markets/browse?category=sports.nba&limit=10
GET /markets/browse?category=crypto.bitcoin
```

**3. Search** (0.01 USDT):
```
GET /markets/search?query=bitcoin
GET /markets/search?query=Trump&category=crypto
```

**4. Browse by mood** (0.01 USDT) — for vague requests:
```
GET /markets/browse?mood=trending
GET /markets/browse?mood=controversial
GET /markets/browse?mood=interesting
```

**5. Historical events** (0.01 USDT):
```
GET /markets/history?query=bitcoin&limit=5
```

### Human says → You call

| Human says | API call |
|-----------|---------|
| "What's interesting on Polymarket?" | `GET /markets/browse?mood=interesting` |
| "Show me trending markets" | `GET /markets/browse?mood=trending` |
| "Any controversial bets?" | `GET /markets/browse?mood=controversial` |
| "What's hot right now?" | `GET /markets/browse?mood=trending` |
| "Show me some fun markets" | `GET /markets/browse?mood=interesting` |
| "Show me NBA markets" | `GET /markets/browse?category=sports.nba` |
| "Find Trump crypto markets" | `GET /markets/search?query=Trump&category=crypto` |
| "What categories are there?" | `GET /markets/categories` |
| "Search for bitcoin" | `GET /markets/search?query=bitcoin` |
| "What are the hottest markets?" | `GET /markets/browse?mood=trending` |

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

### Mood keywords

| Mood | What it returns |
|------|----------------|
| `trending` | Highest volume markets in last 24h |
| `interesting` | Curated mix across categories — unusual, high-engagement markets |
| `controversial` | Markets with prices near 50/50 (most divided opinion) |
| `new` | Recently created markets |
| `closing_soon` | Markets closing within 7 days |

---

## Category Leaderboard

| Human says | API call |
|-----------|---------|
| "Who's best at crypto?" | `GET /traders/categories/leaderboard?category=crypto` |
| "Top NBA bettors" | `GET /traders/categories/leaderboard?category=sports.nba` |
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
| GET | `/markets/browse` | Browse by category or mood |
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
