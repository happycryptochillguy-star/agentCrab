# $CRAB Token Economics

## Overview

Every USDT you spend on agentCrab API calls earns you points. When $CRAB launches, you receive an airdrop worth **at least 2x your total spending**. Early users share a fixed 25% allocation — fewer users now means more tokens per person.

---

## Points System

Points accumulate automatically from day 1. No signup, no staking — just use the API.

| Action | Points earned | Example |
|--------|--------------|---------|
| Deposit 1 USDT | 100 points | 10 USDT deposit = 1,000 points |
| Use 1 API call (0.01 USDT) | 1 point | 100 calls = 100 points |

**Formula**: `total_points = deposit_points + usage_points`

Depositing AND using both earn points. Deposit 10 USDT and use all 1,000 calls = 1,000 + 1,000 = **2,000 points**.

### Why both deposit and usage earn points

- Deposit only (not using) = you trusted us with capital = 50% reward
- Usage only = you actively generated value = 50% reward
- Deposit + use everything = **full 100% reward**

This encourages active usage, not just parking funds.

### Retroactive

All deposits and API calls since day 1 are counted. If you deposited before the points system launched, you already have points.

### Check your points

```python
# SDK
points = client.get_points()
# points.total_points, points.deposit_points, points.usage_points

# HTTP
GET /token/points  # auth required, free
GET /token/points/leaderboard  # no auth, free
GET /token/info  # no auth, free
```

---

## $CRAB Token

| Property | Value |
|----------|-------|
| Name | Crab Token |
| Symbol | CRAB |
| Chain | BSC (BEP-20) |
| Decimals | 18 |
| Total supply | 1,000,000,000 (1 billion) |
| Mint function | None — fixed supply, no inflation |
| Contract | Immutable, no owner, no pause |

### Distribution

| Allocation | % | Amount | Lock |
|-----------|---|--------|------|
| Airdrop Phase 1 | 25% | 250M | Claimable immediately (90-day window) |
| Liquidity pool | 5% | 50M | LP tokens burned (permanent) |
| Team | 15% | 150M | 6-month cliff + 18-month linear vest |
| Treasury | 20% | 200M | Multi-sig wallet |
| Future airdrops | 20% | 200M | Quarterly seasons |
| Ecosystem / integrations | 15% | 150M | As needed |

---

## 2x Airdrop Math

### How it works

1. 50% of all USDT deposited goes to the DEX liquidity pool
2. The pool pairs this USDT with 50M CRAB tokens
3. This sets the initial token price: `price = (0.5 × total_deposits) / 50,000,000`
4. 250M CRAB (5x the pool amount) is distributed to users by points share

### Proof: you get at least 2x back

Assume you deposit X USDT and use all of it:

- Your points = 200 × X (deposit: 100X, usage: 100X)
- Total points = 200 × D (where D = total deposits across all users)
- Your CRAB = 250M × (200X / 200D) = 250M × X/D
- Token price = 0.5D / 50M = D / 100M
- Your airdrop value = 250M × X/D × D/100M = **2.5X**

**Result: 2.5x your total spend.** The extra 0.5x is safety margin since not everyone uses their full balance.

### Example scenarios

| Total platform deposits | Pool USDT | Token price | FDV | Your 10 USDT gets you |
|------------------------|-----------|-------------|-----|----------------------|
| $10,000 | $5,000 | $0.0001 | $100K | $25 in CRAB |
| $50,000 | $25,000 | $0.0005 | $500K | $25 in CRAB |
| $200,000 | $100,000 | $0.002 | $2M | $25 in CRAB |

The ratio stays constant: **2.5x regardless of total deposits**.

### Early user advantage

The 2.5x is the baseline. Early users benefit additionally because:
- Fewer users = larger share of 250M tokens
- You accumulate points across multiple seasons
- Phase 2+ airdrops (20% allocation) reward continued usage
- Token price may appreciate above initial LP price

---

## Liquidity Pool

- **DEX**: PancakeSwap V2 (BSC)
- **Pair**: CRAB/USDT
- **LP tokens**: Burned (sent to 0xdead) — liquidity is permanent, no rug pull possible
- **USDT source**: 50% of all user deposits

---

## Timeline

| Phase | When | What happens |
|-------|------|-------------|
| Phase 1a | Now | Points accumulate. Use API, earn points. |
| Phase 1b | Weeks 1-12 | Points keep accumulating. Early user window. |
| Phase 2a | Week 12 | Snapshot all points. Deploy contracts. |
| Phase 2b | Week 13 | Deploy token + LP pool + airdrop contract. |
| Phase 2c | Week 13 | Open claiming. 90-day claim window. |
| Phase 3+ | Ongoing | Future seasons with 20% allocation. |

---

## Smart Contracts

### CrabToken.sol

Minimal, immutable ERC20. No mint, no burn, no owner, no pause. All tokens minted to treasury at deployment.

### CrabAirdrop.sol

Merkle-tree airdrop contract:
- Users claim with `claim(amount, merkleProof)`
- Immutable merkle root (set at deployment)
- 90-day claim window
- Unclaimed tokens returned to treasury after deadline

### Claiming flow

1. `GET /token/airdrop-status` — check eligibility and amount
2. `POST /token/prepare-claim` — get unsigned claim tx with Merkle proof
3. Agent signs → `POST /payment/submit-tx` — broadcast to BSC
4. CRAB tokens arrive in your wallet

---

## FAQ

**Q: Do I need to do anything special to earn points?**
No. Just use the API normally. Points are calculated from your deposit and usage history.

**Q: What if I deposited before points were announced?**
You already have points. All activity since day 1 counts retroactively.

**Q: Can I lose my points?**
No. Points only go up. Withdrawals don't reduce points — they are based on total deposits and total usage.

**Q: Is this a Ponzi scheme?**
No. The 2x return comes from real economics: 50% of deposits create the liquidity pool. The math is transparent and verifiable on-chain.

**Q: When does the token launch?**
Approximately 90 days after launch (Week 13). Follow announcements for the exact date.
