# agentCrab

Turn any AI agent into a Polymarket prediction market assistant with one prompt.

[Website](https://agentcrab.ai) | [SDK](https://pypi.org/project/agentcrab/) | [Agent README](AGENT_README.md) | [Protocol Spec](spec/protocol.md)

---

## What is agentCrab?

agentCrab is middleware that connects AI agents to [Polymarket](https://polymarket.com), the world's largest prediction market. Your agent gets full trading capabilities — search markets, place orders, manage positions, set stop-losses — through a simple Python SDK, MCP server, or HTTP API.

No blockchain knowledge needed. No web3 libraries. No gas management. Your agent just calls our API, and we handle everything.

### Key features

- **One prompt onboarding** — Agent reads [AGENT_README.md](AGENT_README.md) and becomes a full Polymarket assistant
- **Python SDK** — `pip install agentcrab` — 3 lines to start, 40+ methods
- **MCP Server** — Works with Claude Code, Cursor, Windsurf, and any MCP-compatible tool
- **Gasless trading** — All Polygon operations are gasless via Polymarket's relayer
- **Server-side tx builder** — Agent only needs HTTP + local signing, no ABIs or contract interaction
- **Private key stays local** — Agent signs transactions locally, never sends the key
- **$CRAB token airdrops** — Every API call earns points worth 2x your spending

---

## Quick Start

### Python SDK

```bash
pip install agentcrab
```

```python
from agentcrab import AgentCrab

client = AgentCrab("https://api.agentcrab.ai/polymarket", "0xYOUR_PRIVATE_KEY")

# Browse trending markets
markets = client.browse(mood="trending")

# Find a tradeable market and buy
market, outcome, orderbook = client.find_tradeable("bitcoin")
result = client.buy(outcome["token_id"], size=5.0, price=float(orderbook.best_ask))

# Check airdrop points
points = client.get_points()
print(f"You have {points.total_points} points")
```

### MCP Server

```bash
pip install agentcrab[mcp]

# For Claude Code, Cursor, and other MCP clients
AGENTCRAB_PRIVATE_KEY=0x... agentcrab-mcp
```

### HTTP API

```bash
# No SDK needed — any language works
curl https://api.agentcrab.ai/polymarket/markets/browse?mood=trending \
  -H "X-Wallet-Address: 0x..." \
  -H "X-Signature: 0x..." \
  -H "X-Message: agentcrab:1709000000" \
  -H "X-Payment-Mode: prepaid"
```

---

## $CRAB Token

Every USDT spent on agentCrab API calls earns airdrop points. When $CRAB launches (~90 days), points convert to tokens worth **at least 2x your total spending**.

| Action | Points |
|--------|--------|
| Deposit 1 USDT | 100 points |
| Use 1 API call (0.01 USDT) | 1 point |

Early users share a fixed 25% allocation (250M tokens). Fewer users now = more per person.

| Allocation | Share |
|-----------|-------|
| Airdrop Phase 1 | 25% |
| Liquidity pool (LP burned) | 5% |
| Team (6mo cliff + 18mo vest) | 15% |
| Treasury | 20% |
| Future airdrops | 20% |
| Ecosystem | 15% |

See [Token Economics](docs/token-economics.md) for the full breakdown, math proof, and claiming process.

---

## Architecture

```
AI Agent (SDK / MCP / HTTP)
    │
    ▼
agentCrab API (FastAPI)
    │
    ├──▶ Polymarket APIs (Gamma, CLOB, Data)
    ├──▶ Polymarket Builder-Relayer (gasless Safe + approvals)
    │
    ▼
BSC Smart Contract
Payment: 0.01 USDT/call
```

### How it works

1. **Agent signs** — EIP-191 personal signature for auth, transaction signatures for on-chain ops
2. **Server builds** — We construct unsigned transactions, the agent signs them locally
3. **Server broadcasts** — We submit signed transactions to BSC or Polygon
4. **Agent trades** — Full Polymarket access: markets, orders, positions, stop-loss, leaderboards

---

## Pricing

**0.01 USDT per API call** on BSC (Binance Smart Chain).

- **Prepaid mode**: Deposit once, balance deducted automatically
- **Direct mode**: Pay per call with tx hash
- **Free endpoints**: Balance check, categories, token info, capabilities
- **Trading setup**: 0.01-0.03 USDT one-time, then cached for free on subsequent sessions

All API spending earns $CRAB airdrop points (2x return).

---

## Documentation

| Document | Description |
|----------|-------------|
| [AGENT_README.md](AGENT_README.md) | Entry point for AI agents — rules, quick start, money-making guide |
| [SDK Guide](docs/sdk-guide.md) | Full Python SDK reference with all 40+ methods |
| [Token Economics](docs/token-economics.md) | $CRAB token details, points system, 2x airdrop math |
| [Auth & Signing](docs/auth-and-signing.md) | HTTP API authentication with EIP-191 signatures |
| [Wallet & Payment](docs/wallet-and-payment.md) | Payment setup (prepaid & direct modes) |
| [Enable Trading](docs/enable-trading.md) | One-time trading setup (Safe deploy, approvals, credentials) |
| [Place Orders](docs/place-orders.md) | Order placement, batch orders, triggers |
| [Protocol Spec](spec/protocol.md) | Agent Payment Protocol (APP) v0.1 — open standard |

---

## Project Structure

```
agentWay/
├── AGENT_README.md              # Agent entry point
├── docs/                        # Detailed guides
│   ├── sdk-guide.md
│   ├── token-economics.md
│   ├── auth-and-signing.md
│   ├── wallet-and-payment.md
│   ├── enable-trading.md
│   └── place-orders.md
├── agentcrab-python/            # Python SDK (PyPI: agentcrab)
│   ├── agentcrab/
│   │   ├── client.py            # AgentCrab client (40+ methods)
│   │   └── mcp_server.py        # MCP server (40+ tools)
│   └── pyproject.toml
├── Polymarket/                  # API server
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── services/            # Business logic (12 services)
│   │   └── routes/              # HTTP endpoints (11 routers)
│   └── contracts/               # BSC payment smart contracts (Foundry)
├── spec/                        # Protocol specification
│   └── protocol.md
└── clawhub/                     # MCP skill definitions
```

---

## For Developers

### Running the API server

```bash
cd Polymarket
pip install -r api/requirements.txt
touch .env  # add secrets — see api/config.py for all fields
uvicorn api.main:app --reload
```

### Running tests

```bash
# Smart contract tests (Foundry)
cd Polymarket/contracts && forge test -vvv

# API server health check
curl http://localhost:8000/health
```

### Publishing the SDK

```bash
cd agentcrab-python
python -m build && twine upload dist/*
```

---

## Security

- All secrets in `.env` (gitignored) — never hardcoded
- EIP-191 signature auth — no API keys to leak
- Private keys stay on the agent — server never sees them
- Server-built unsigned transactions — agent signs locally
- SQLite replay prevention — signatures can't be reused
- L2 credentials encrypted at rest (Fernet)
- Rate limiting per IP (30-120 req/min by tier)

For security concerns, open an issue or email dev@agentcrab.ai.

---

## License

- **API Server** (`Polymarket/`): BUSL-1.1
- **Python SDK** (`agentcrab-python/`): MIT
- **Protocol Spec** (`spec/`): CC-BY 4.0
