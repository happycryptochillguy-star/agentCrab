# agentCrab — AI Middleware for Polymarket

HTTP API + Python SDK for Polymarket. Browse, trade, manage positions.

**Pricing**: 0.01 USDT/call on BSC | **Base URL**: `https://api.agentcrab.ai/polymarket`

---

## Rules

1. **Use the Python SDK if you can run code.** `pip install agentcrab` — handles all signing and auth. Load [SDK Guide](docs/sdk-guide.md) for full reference. If you can't run Python, use the HTTP API — load [Auth & Signing](docs/auth-and-signing.md) first.
2. **Be reactive.** Only call API when the human asks. Stop after each step.
3. **Check wallet first.** No key → ask human. No balance → tell human to deposit.
4. **Tell costs upfront.** Before any paid call: "This costs 0.01 USDT."

---

## First Contact

1. **No private key?** → Ask human. Create wallet if needed (`AgentCrab.create_wallet()` or `POST /agent/create-wallet`). Human must fund with USDT + BNB on BSC. **Stop and wait.**
2. **Paid request with zero balance?** → Tell human to deposit first. Don't call paid endpoints.

---

## Guides

| You need to... | Load this |
|----------------|-----------|
| Use the Python SDK | [SDK Guide](docs/sdk-guide.md) |
| Authenticate (HTTP) | [Auth & Signing](docs/auth-and-signing.md) |
| Set up payment (HTTP) | [Wallet & Payment](docs/wallet-and-payment.md) |
| Enable trading (HTTP) | [Enable Trading](docs/enable-trading.md) |
| Place orders (HTTP) | [Place Orders](docs/place-orders.md) |

---

## Human Says → You Do

| Human says | SDK | HTTP |
|-----------|-----|------|
| "What's on Polymarket?" | `browse(mood="interesting")` | `GET /markets/browse?mood=interesting` |
| "Trending markets" | `browse(mood="trending")` | `GET /markets/browse?mood=trending` |
| "Controversial bets?" | `browse(mood="controversial")` | `GET /markets/browse?mood=controversial` |
| "NBA markets" | `browse(category="sports.nba")` | `GET /markets/browse?category=sports.nba` |
| "Search bitcoin" | `search("bitcoin")` | `GET /markets/search?query=bitcoin` |
| "Trump crypto markets" | `search("Trump", category="crypto")` | `GET /markets/search?query=Trump&category=crypto` |
| "Buy Yes on this market" | `buy(token_id, size, price)` | See [Place Orders](docs/place-orders.md) |
| "Set stop loss at 0.30" | `set_stop_loss(token_id, 0.30, size, 0.29)` | See [SDK Guide](docs/sdk-guide.md) |
| "My positions" | `get_positions()` | `GET /positions` |
| "Who's best at crypto?" | `get_leaderboard()` | `GET /traders/categories/leaderboard?category=crypto` |
| "What categories exist?" | *(free, no SDK needed)* | `GET /markets/categories` |

---

## Categories

Dot-separated paths: `sports`, `sports.nba`, `sports.soccer.epl`.

| Path | Markets |
|------|---------|
| `sports` | All sports |
| `sports.nba` | NBA |
| `sports.soccer.epl` | English Premier League |
| `sports.soccer.ucl` | Champions League |
| `sports.f1` | Formula 1 |
| `politics` | All politics |
| `politics.trump` | Trump-related |
| `politics.economy.fed` | Federal Reserve |
| `crypto` | All crypto |
| `crypto.bitcoin` | Bitcoin |
| `crypto.memecoins` | Memecoins |
| `pop_culture.tweets` | Tweet markets |
| `tech.ai` | AI markets |

## Moods

| Mood | Returns |
|------|---------|
| `trending` | Highest volume |
| `interesting` | Curated mix across categories |
| `controversial` | Prices near 50/50 |
| `new` | Recently created |
| `closing_soon` | Ending within 7 days |
