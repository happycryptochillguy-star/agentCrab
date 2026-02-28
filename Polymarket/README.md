# agentWay — Polymarket Module

Paid API middleware for Polymarket football/soccer prediction markets, designed for AI agents.

## Overview

This module provides structured access to Polymarket's football markets through a FastAPI server with on-chain payment verification on BSC (Binance Smart Chain).

**For AI agents**: Read [`AGENT_README.md`](../AGENT_README.md) in the repo root — it contains all API endpoints, payment setup, and usage examples.

## Architecture

```
AI Agent → agentWay API (FastAPI) → Polymarket Gamma API
              ↓
         BSC Smart Contract (UUPS Proxy)
         Payment: 0.01 USDT per call
```

## Project Structure

```
Polymarket/
├── api/                    # FastAPI server
│   ├── main.py             # App entry point + background scanner
│   ├── config.py           # Environment config
│   ├── models.py           # Pydantic models
│   ├── services/
│   │   ├── polymarket.py   # Gamma API client
│   │   ├── payment.py      # On-chain payment verification
│   │   └── balance.py      # Off-chain balance (SQLite)
│   └── routes/
│       ├── football.py     # /football/markets endpoint
│       └── payment.py      # /payment/* endpoints
├── contracts/              # Foundry smart contracts
│   ├── src/
│   │   └── AgentWayPayment.sol
│   ├── test/
│   │   └── AgentWayPayment.t.sol
│   └── script/
│       └── Deploy.s.sol
└── .env                    # Environment variables (not committed)
```

## Quick Start

```bash
# Install Python dependencies
pip install -r api/requirements.txt

# Run the server
cd Polymarket
uvicorn api.main:app --reload

# Health check
curl http://localhost:8000/health
```

## Smart Contract

Built with Foundry. UUPS upgradeable proxy pattern.

```bash
cd contracts
forge build
forge test -vvv
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PRIVATE_KEY` | Deployer wallet private key |
| `BSC_RPC_URL` | BSC RPC endpoint |
| `CONTRACT_ADDRESS` | Deployed proxy contract address |

## License

MIT
