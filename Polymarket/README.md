# agentCrab — Polymarket Module

Full-stack API middleware for Polymarket prediction markets, designed for AI agents.

## Overview

This module provides structured access to all Polymarket functionality through a FastAPI server with on-chain payment verification on BSC (Binance Smart Chain).

**Features**: Market search, deposits (cross-chain bridge), orderbooks, positions/P&L, leaderboard, order execution.

**For AI agents**: Read [`AGENT_README.md`](../AGENT_README.md) in the repo root — it contains all API endpoints, payment setup, and usage examples.

## Architecture

```
AI Agent → agentCrab API (FastAPI) → Polymarket APIs (Gamma, CLOB, Data, Bridge)
              ↓
         BSC Smart Contract (UUPS Proxy)
         Payment: 0.01 USDT per call
```

## Project Structure

```
Polymarket/
├── api/
│   ├── main.py             # App entry point + background scanner
│   ├── config.py           # Environment config
│   ├── models.py           # Pydantic models
│   ├── auth.py             # Reusable auth + payment dependency
│   ├── services/
│   │   ├── polymarket.py   # Gamma API client (football, legacy)
│   │   ├── gamma.py        # General Gamma API client (all categories)
│   │   ├── clob.py         # CLOB API client (L0 orderbook + L2 trading)
│   │   ├── bridge.py       # Polymarket native bridge (deposit/withdraw)
│   │   ├── data_api.py     # Data API client (positions, trades)
│   │   ├── leaderboard.py  # Leaderboard service
│   │   ├── payment.py      # On-chain payment verification
│   │   └── balance.py      # Off-chain balance (SQLite)
│   └── routes/
│       ├── agent.py        # /agent/capabilities (free)
│       ├── football.py     # /football/* (legacy)
│       ├── markets.py      # /markets/* (search, details)
│       ├── orderbook.py    # /orderbook/*, /prices/*
│       ├── deposit.py      # /deposit/* (bridge to Polymarket)
│       ├── positions.py    # /positions/* (P&L, trades)
│       ├── traders.py      # /traders/* (leaderboard)
│       ├── trading.py      # /trading/* (orders, setup)
│       └── payment.py      # /payment/* (agentCrab balance)
├── contracts/              # Foundry smart contracts
│   ├── src/AgentCrabPayment.sol
│   ├── test/AgentCrabPayment.t.sol
│   └── script/Deploy.s.sol
└── .env
```

## Quick Start

```bash
pip install -r api/requirements.txt
cd Polymarket
uvicorn api.main:app --reload
curl http://localhost:8000/health
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PRIVATE_KEY` | Deployer wallet private key |
| `BSC_RPC_URL` | BSC RPC endpoint |
| `CONTRACT_ADDRESS` | Deployed proxy contract address |

## License

MIT
