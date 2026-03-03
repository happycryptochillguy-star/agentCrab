# Agent Payment Protocol (APP) v0.1

**Status**: Draft
**License**: CC-BY 4.0 — anyone may implement this protocol freely.
**Reference Implementation**: agentCrab (https://agentcrab.ai)

---

## 1. Goal

Define a standard way for AI agents to:
1. Discover API capabilities via a single URL
2. Authenticate using wallet signatures (no API keys, no OAuth)
3. Pay per API call via on-chain smart contracts
4. Interact with the service using only HTTP + local signing

## 2. Design Principles

- **One prompt**: Agent reads a single README URL and becomes a full assistant
- **Agent only needs HTTP**: No web3 libraries, no ABIs, no gas management
- **Private key stays local**: Agent signs locally, never sends the key
- **Human-friendly**: Agent talks to users like an assistant, not a programmer

## 3. Authentication

### 3.1 Message Format

```
agentcrab:{unix_timestamp}
```

The agent signs this message using EIP-191 `personal_sign` with its wallet
private key. Timestamp must be within 5 minutes of server time.

### 3.2 Headers

Every authenticated request includes:

| Header | Description |
|--------|-------------|
| `X-Wallet-Address` | Agent's EOA address (0x-prefixed, checksummed) |
| `X-Signature` | EIP-191 signature of the message |
| `X-Message` | The signed message (`agentcrab:{timestamp}`) |
| `X-Payment-Mode` | `prepaid` or `direct` |
| `X-Tx-Hash` | (direct mode only) BSC transaction hash |

## 4. Payment

### 4.1 Smart Contract Interface

A payment contract on a supported chain (e.g., BSC) with at minimum:

```solidity
function deposit(uint256 amount) external;  // Prepay for multiple calls
function pay() external;                     // Pay for a single call
function getBalance(address user) external view returns (uint256);
```

The contract holds a stablecoin (e.g., USDT) and tracks per-user deposits.

### 4.2 Prepaid Mode

1. Agent calls `deposit(amount)` on-chain (via server-built unsigned tx)
2. Server syncs on-chain balance to local database
3. Each API call atomically deducts from the local balance

### 4.3 Direct Mode

1. Agent calls `pay()` on-chain
2. Agent passes the tx hash in `X-Tx-Hash` header
3. Server verifies the `DirectPayment` event in the receipt
4. Server marks the tx hash as used (prevents replay)

### 4.4 Server-Side Transaction Builder

To keep agents simple (no web3/ABI needed), the server provides:

- `POST /payment/prepare-deposit` — returns unsigned approve + deposit txs
- `POST /payment/prepare-pay` — returns unsigned approve + pay txs
- `POST /payment/submit-tx` — broadcasts agent-signed raw transaction

## 5. Discovery

### 5.1 Capabilities Endpoint

Every APP-compliant server exposes a free, unauthenticated endpoint:

```
GET /agent/capabilities
```

Returns a JSON object describing all available endpoints, their costs,
required headers, and example usage. This allows any AI agent to
self-discover the full API surface from a single URL.

### 5.2 Wallet Creation

For agents without an existing wallet:

```
POST /agent/create-wallet
```

Returns a new EOA address and private key. The agent stores the key locally.

## 6. Response Format

All endpoints return a consistent JSON structure:

```json
{
  "status": "ok",
  "summary": "Human-readable description of what happened",
  "data": { ... }
}
```

Error responses:

```json
{
  "status": "error",
  "error_code": "INSUFFICIENT_BALANCE",
  "message": "Human-readable error description with actionable guidance"
}
```

The `summary` field is designed for AI agents to relay directly to users.
The `data` field contains structured data for programmatic use.

## 7. Extensibility

### 7.1 Product Namespacing

Endpoints are namespaced by product:

```
/polymarket/markets/search
/polymarket/trading/order
/dydx/markets/search      (hypothetical)
```

### 7.2 Multi-Chain Support

The protocol supports multiple chains. The `submit-tx` endpoint accepts
a `chain` parameter:

```json
{ "signed_tx": "0x...", "chain": "bsc" }
{ "signed_tx": "0x...", "chain": "polygon" }
```

## 8. Implementer Checklist

To build an APP-compliant service:

1. Deploy a payment smart contract on a supported chain
2. Implement EIP-191 signature verification
3. Expose `GET /agent/capabilities` (free, no auth)
4. Use the standard header scheme for auth + payment
5. Return responses in the standard format with `summary` + `data`
6. Provide server-side transaction builders so agents need only HTTP

---

*This specification is open. Build freely, attribute agentCrab.*
