# agentCrab — Polymarket Module

Full-stack API middleware for Polymarket prediction markets, designed for AI agents.

## Overview

This module provides structured access to all Polymarket functionality through a FastAPI server with on-chain payment verification on BSC (Binance Smart Chain).

**Features**: Market search, deposits (cross-chain relay), orderbooks, positions/P&L, leaderboard, order execution, batch orders, stop-loss/take-profit triggers, category leaderboards, health monitoring.

**For AI agents**: Read [`AGENT_README.md`](../AGENT_README.md) in the repo root — it contains all API endpoints, payment setup, and usage examples.

## Architecture

```
AI Agent → agentCrab API (FastAPI) → Polymarket APIs (Gamma, CLOB, Data, Bridge)
              ↓                           ↓
         BSC Smart Contract          Polymarket Builder-Relayer
         Payment: 0.01 USDT/call    (gasless Safe deploy + approvals)
```

## Project Structure

```
Polymarket/
├── api/
│   ├── main.py                # App entry point + background tasks + rate limiter
│   ├── config.py              # Pydantic Settings (from .env)
│   ├── models.py              # All Pydantic models (strict validation)
│   ├── auth.py                # Reusable auth + payment dependency
│   ├── services/
│   │   ├── balance.py         # SQLite off-chain balance + triggers tables
│   │   ├── payment.py         # BSC/Polygon tx builder, broadcaster, balance sync
│   │   ├── gamma.py           # General Gamma API client (all categories)
│   │   ├── clob.py            # CLOB L0 (orderbook) + L2 (trading) + batch orders
│   │   ├── bridge.py          # Polymarket deposit via fun.xyz relay
│   │   ├── relayer.py         # Builder-Relayer (gasless Safe deploy + approvals)
│   │   ├── data_api.py        # Data API (positions, trades, activity)
│   │   ├── leaderboard.py     # Global leaderboard
│   │   ├── category_leaderboard.py  # Category leaderboard sync + query
│   │   ├── triggers.py        # Stop loss / take profit trigger CRUD + monitor
│   │   ├── health.py          # Health probes + Telegram alerts
│   │   ├── history.py         # Historical (closed) events sync
│   │   └── http_pool.py       # Shared httpx connection pools
│   └── routes/
│       ├── agent.py           # /agent/* (capabilities, create-wallet)
│       ├── admin.py           # /admin/* (health-status, reload-config)
│       ├── markets.py         # /markets/* (search, browse, events, categories)
│       ├── orderbook.py       # /orderbook/*, /prices/*
│       ├── deposit.py         # /deposit/* (prepare-transfer, bridge)
│       ├── positions.py       # /positions/* (P&L, trades, activity)
│       ├── traders.py         # /traders/* (leaderboard, lookup)
│       ├── category_leaderboard.py  # /traders/categories/*
│       ├── trading.py         # /trading/* (setup, orders, batch, cancel)
│       ├── triggers.py        # /trading/triggers/* (stop-loss, take-profit)
│       └── payment.py         # /payment/* (balance, deposit, submit-tx)
├── contracts/                 # Foundry smart contracts
│   ├── src/AgentCrabPayment.sol
│   ├── test/AgentCrabPayment.t.sol
│   └── script/Deploy.s.sol
└── .env                       # All secrets (gitignored)
```

## Quick Start

```bash
pip install -r api/requirements.txt
cd Polymarket
uvicorn api.main:app --reload
curl http://localhost:8000/health
```

## Environment Variables

All configuration is in `.env` (gitignored). See `api/config.py` for the full list of fields.

Key variables:
- `PRIVATE_KEY` — Server wallet private key (for tx broadcasting)
- `BSC_RPC_URL` — BSC RPC endpoint
- `POLYGON_RPC_URL` — Polygon RPC endpoint
- `CONTRACT_ADDRESS` — Deployed payment contract address
- `POLY_BUILDER_API_KEY` / `SECRET` / `PASSPHRASE` — Builder-Relayer credentials
- `ADMIN_KEY` — Admin endpoint authentication key
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Health alert notifications

## License

BUSL-1.1 (see root LICENSE)
