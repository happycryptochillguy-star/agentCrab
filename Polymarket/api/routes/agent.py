from fastapi import APIRouter

from api.config import settings

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/capabilities")
async def get_capabilities():
    """Return full API capabilities for agent discovery. Free, no auth required."""
    return {
        "status": "ok",
        "summary": "agentCrab Polymarket middleware capabilities. Full-stack trading middleware for AI agents.",
        "data": {
            "auth": {
                "method": "EIP-191 personal_sign",
                "message_format": "agentcrab:{unix_timestamp}",
                "timestamp_tolerance_seconds": settings.signature_max_age_seconds,
                "required_headers": {
                    "X-Wallet-Address": "Your BSC wallet address (checksummed or lowercase)",
                    "X-Signature": "Hex signature of the message (0x-prefixed)",
                    "X-Message": "The signed message, e.g. agentcrab:1709136000",
                    "X-Payment-Mode": "direct or prepaid",
                    "X-Tx-Hash": "(direct mode only) BSC tx hash from calling pay()",
                },
                "trading_headers": {
                    "X-Poly-Api-Key": "Polymarket L2 API key (for trading endpoints)",
                    "X-Poly-Secret": "Polymarket L2 secret",
                    "X-Poly-Passphrase": "Polymarket L2 passphrase",
                    "X-Poly-Address": "Your Polygon wallet address (for trading/positions)",
                },
            },
            "payment": {
                "chain": "BSC (Chain ID: 56)",
                "contract_address": settings.contract_address or "not configured",
                "usdt_address": settings.usdt_address,
                "cost_per_call": "0.01 USDT (10^16 wei, 18 decimals)",
                "modes": {
                    "direct": {
                        "description": "Pay per call. Call pay() on contract, pass tx hash in header.",
                        "steps": [
                            "USDT.approve(CONTRACT_ADDRESS, amount)",
                            "AgentCrabPayment.pay()",
                            "Use the tx hash in X-Tx-Hash header",
                        ],
                    },
                    "prepaid": {
                        "description": "Deposit once, use many times. Background scanner detects deposits every ~15s.",
                        "steps": [
                            "USDT.approve(CONTRACT_ADDRESS, amount)",
                            "AgentCrabPayment.deposit(amount)",
                            "Wait ~15s for scanner, then call API with X-Payment-Mode: prepaid",
                        ],
                    },
                },
                "contract_abi": [
                    {
                        "inputs": [],
                        "name": "pay",
                        "outputs": [],
                        "stateMutability": "nonpayable",
                        "type": "function",
                    },
                    {
                        "inputs": [{"name": "amount", "type": "uint256"}],
                        "name": "deposit",
                        "outputs": [],
                        "stateMutability": "nonpayable",
                        "type": "function",
                    },
                    {
                        "inputs": [{"name": "user", "type": "address"}],
                        "name": "getBalance",
                        "outputs": [{"name": "", "type": "uint256"}],
                        "stateMutability": "view",
                        "type": "function",
                    },
                    {
                        "inputs": [{"name": "user", "type": "address"}],
                        "name": "getDirectPaymentCount",
                        "outputs": [{"name": "", "type": "uint256"}],
                        "stateMutability": "view",
                        "type": "function",
                    },
                ],
            },
            "endpoints": {
                "free": [
                    {
                        "path": "/health",
                        "method": "GET",
                        "description": "Check if the API is running.",
                    },
                    {
                        "path": "/agent/capabilities",
                        "method": "GET",
                        "description": "This endpoint. Returns full API capabilities for agent discovery.",
                    },
                    {
                        "path": "/markets/tags",
                        "method": "GET",
                        "description": "Get all Polymarket tag categories.",
                    },
                    {
                        "path": "/trading/setup",
                        "method": "GET",
                        "description": "Polymarket trading setup guide (L2 credential derivation).",
                    },
                    {
                        "path": "/trading/contracts",
                        "method": "GET",
                        "description": "Polygon contract addresses + approval instructions.",
                    },
                    {
                        "path": "/payment/balance",
                        "method": "GET",
                        "description": "Check agentCrab prepaid balance. Auth required, no payment.",
                    },
                    {
                        "path": "/payment/verify",
                        "method": "POST",
                        "description": "Verify agentCrab payment transaction. Auth required, no payment.",
                    },
                    {
                        "path": "/deposit/supported-assets",
                        "method": "GET",
                        "description": "List supported chains/tokens for Polymarket deposits.",
                    },
                ],
                "paid_deposit": [
                    {
                        "path": "/deposit/create",
                        "method": "POST",
                        "description": "Get deposit addresses for funding Polymarket. Returns EVM/Solana/BTC addresses. Send tokens to the EVM address from any supported chain.",
                        "body": {"polymarket_address": "str (Polygon wallet address)"},
                    },
                    {
                        "path": "/deposit/withdraw",
                        "method": "POST",
                        "description": "Get withdrawal address for withdrawing from Polymarket to another chain.",
                        "body": {"polymarket_address": "str", "to_chain_id": "str", "to_token_address": "str", "recipient_address": "str"},
                    },
                ],
                "paid_markets": [
                    {
                        "path": "/markets/search",
                        "method": "GET",
                        "description": "Search events across all Polymarket categories.",
                        "params": {"query": "str?", "tag": "str?", "limit": "int (1-100)", "offset": "int"},
                    },
                    {
                        "path": "/markets/events/{event_id}",
                        "method": "GET",
                        "description": "Get event details by ID.",
                    },
                    {
                        "path": "/markets/events/slug/{slug}",
                        "method": "GET",
                        "description": "Get event details by slug.",
                    },
                    {
                        "path": "/markets/{market_id}",
                        "method": "GET",
                        "description": "Get market details by ID.",
                    },
                    {
                        "path": "/football/markets",
                        "method": "GET",
                        "description": "Get football/soccer markets (legacy, backward compatible).",
                        "params": {"league": "str?", "limit": "int (1-100)", "offset": "int"},
                    },
                ],
                "paid_orderbook": [
                    {
                        "path": "/orderbook/{token_id}",
                        "method": "GET",
                        "description": "Full orderbook for a token.",
                    },
                    {
                        "path": "/orderbook/batch",
                        "method": "POST",
                        "description": "Batch orderbooks (1 charge). Body: list of token IDs.",
                    },
                    {
                        "path": "/prices/{token_id}",
                        "method": "GET",
                        "description": "Price summary (bid, ask, mid, spread, last trade).",
                    },
                    {
                        "path": "/prices/batch",
                        "method": "POST",
                        "description": "Batch prices (1 charge). Body: list of token IDs.",
                    },
                ],
                "paid_positions": [
                    {
                        "path": "/positions",
                        "method": "GET",
                        "description": "Your Polymarket positions + P&L. Requires X-Poly-Address header.",
                    },
                    {
                        "path": "/positions/trades",
                        "method": "GET",
                        "description": "Your trade history. Requires X-Poly-Address header.",
                    },
                    {
                        "path": "/positions/activity",
                        "method": "GET",
                        "description": "Your on-chain activity. Requires X-Poly-Address header.",
                    },
                ],
                "paid_traders": [
                    {
                        "path": "/traders/leaderboard",
                        "method": "GET",
                        "description": "Top traders ranking.",
                        "params": {"limit": "int (1-100)", "offset": "int"},
                    },
                    {
                        "path": "/traders/{address}/positions",
                        "method": "GET",
                        "description": "Another trader's positions.",
                    },
                    {
                        "path": "/traders/{address}/trades",
                        "method": "GET",
                        "description": "Another trader's trade history.",
                    },
                ],
                "paid_trading": [
                    {
                        "path": "/trading/order",
                        "method": "POST",
                        "description": "Place order (limit/market). Requires L2 headers.",
                        "body": {"token_id": "str", "side": "BUY|SELL", "size": "float", "price": "float", "order_type": "GTC|GTD|FOK|FAK"},
                        "extra_headers": ["X-Poly-Api-Key", "X-Poly-Secret", "X-Poly-Passphrase", "X-Poly-Address"],
                    },
                    {
                        "path": "/trading/order/{order_id}",
                        "method": "DELETE",
                        "description": "Cancel single order. Requires L2 headers.",
                    },
                    {
                        "path": "/trading/orders",
                        "method": "DELETE",
                        "description": "Cancel all open orders. Requires L2 headers.",
                    },
                    {
                        "path": "/trading/orders",
                        "method": "GET",
                        "description": "Get open orders. Requires L2 headers.",
                    },
                ],
            },
            "error_codes": {
                "INVALID_SIGNATURE": {
                    "http_status": 401,
                    "meaning": "Signature verification failed",
                    "fix": "Re-sign 'agentcrab:{current_unix_timestamp}' with your wallet key. Timestamp must be within 5 minutes.",
                },
                "MISSING_TX_HASH": {
                    "http_status": 400,
                    "meaning": "Direct mode but no tx hash provided",
                    "fix": "Add X-Tx-Hash header with the pay() transaction hash.",
                },
                "PAYMENT_NOT_VERIFIED": {
                    "http_status": 402,
                    "meaning": "Cannot find DirectPayment event in transaction",
                    "fix": "Verify you called pay() on the correct contract and tx is confirmed on BSC.",
                },
                "INSUFFICIENT_BALANCE": {
                    "http_status": 402,
                    "meaning": "Prepaid balance too low",
                    "fix": "Deposit more USDT via deposit() on the contract.",
                },
                "BALANCE_DEDUCTION_FAILED": {
                    "http_status": 402,
                    "meaning": "Off-chain balance deduction failed",
                    "fix": "Retry the request.",
                },
                "INVALID_PAYMENT_MODE": {
                    "http_status": 400,
                    "meaning": "Unknown payment mode",
                    "fix": "Set X-Payment-Mode header to 'direct' or 'prepaid'.",
                },
                "UPSTREAM_ERROR": {
                    "http_status": 502,
                    "meaning": "Polymarket API failed",
                    "fix": "Retry after a few seconds.",
                },
                "BRIDGE_ERROR": {
                    "http_status": 400,
                    "meaning": "Bridge routing failed (bad params or no route)",
                    "fix": "Check amount, token, and chain are valid. See /deposit/supported-assets.",
                },
                "ORDER_REJECTED": {
                    "http_status": 400,
                    "meaning": "Polymarket CLOB rejected the order",
                    "fix": "Check order params (price 0.01-0.99, valid token_id, sufficient balance).",
                },
                "NOT_FOUND": {
                    "http_status": 404,
                    "meaning": "Resource not found on Polymarket",
                    "fix": "Check the ID or slug is correct.",
                },
                "RATE_LIMITED": {
                    "http_status": 429,
                    "meaning": "Too many requests",
                    "fix": "Wait and retry. Maximum 30 requests per 60 seconds per IP.",
                },
            },
            "rate_limits": {
                "max_requests": 30,
                "window_seconds": 60,
                "scope": "per IP address",
            },
            "workflow": {
                "deposit": [
                    "1. GET /deposit/supported-assets — see supported chains/tokens",
                    "2. POST /deposit/create — get deposit addresses (EVM, Solana, BTC)",
                    "3. Agent sends supported tokens (USDT, USDC, etc.) to the EVM deposit address from any chain",
                    "4. Polymarket automatically bridges funds to USDC.e on Polygon",
                ],
                "withdraw": [
                    "1. POST /deposit/withdraw — get withdrawal address for destination chain",
                    "2. Agent sends USDC.e on Polygon to the returned address",
                    "3. Polymarket bridges funds to destination chain/token",
                ],
                "trading": [
                    "1. GET /trading/setup — learn how to derive L2 credentials",
                    "2. Agent derives L2 creds locally (one-time, using py-clob-client)",
                    "3. GET /trading/contracts — get Polygon contract addresses for token approvals",
                    "4. Agent approves tokens on Polygon (one-time)",
                    "5. GET /markets/search — find markets",
                    "6. GET /orderbook/{token_id} — check prices",
                    "7. POST /trading/order — place order (with L2 headers)",
                    "8. GET /positions — track positions and P&L",
                ],
            },
        },
    }
