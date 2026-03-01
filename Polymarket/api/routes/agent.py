from eth_account import Account
from fastapi import APIRouter

from api.config import settings
from api.models import SuccessResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/create-wallet")
async def create_wallet():
    """Create a new wallet (EOA). Free, no auth required.

    Returns address + private key. Works on both BSC (payment) and Polygon (trading).
    The agent should save the private key and tell the human to fund the address with USDT + BNB on BSC.
    """
    acct = Account.create()
    return SuccessResponse(
        summary=f"Wallet created: {acct.address}. Fund with USDT + BNB on BSC to start using paid features.",
        data={
            "address": acct.address,
            "private_key": f"0x{acct.key.hex()}",
        },
    )


@router.get("/capabilities")
async def get_capabilities():
    """Return full API capabilities for agent discovery. Free, no auth required."""
    return {
        "status": "ok",
        "summary": "agentCrab Polymarket middleware capabilities. Full-stack trading middleware for AI agents. All paths below are relative to /polymarket.",
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
                        "path": "/agent/create-wallet",
                        "method": "POST",
                        "description": "Create a new wallet. Returns address + private key. No auth needed.",
                    },
                    {
                        "path": "/agent/capabilities",
                        "method": "GET",
                        "description": "This endpoint. Returns full API capabilities for agent discovery.",
                    },
                    {
                        "path": "/markets/categories",
                        "method": "GET",
                        "description": "Hierarchical market category taxonomy (politics, sports, crypto, etc.). Use category paths with /markets/browse.",
                    },
                    {
                        "path": "/markets/tags",
                        "method": "GET",
                        "description": "Get all raw Polymarket tags (use /markets/categories for organized browsing).",
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
                        "path": "/markets/history/sync",
                        "method": "POST",
                        "description": "Trigger sync of historical (closed) events from Polymarket. Auth required, no payment. Throttled to 1 hour.",
                    },
                    {
                        "path": "/traders/categories/sync",
                        "method": "POST",
                        "description": "Trigger category leaderboard sync. Auth required, no payment. Throttled to 2 hours.",
                    },
                    {
                        "path": "/trading/prepare-deploy-safe",
                        "method": "POST",
                        "description": "Check if Safe is deployed; if not, returns CreateProxy EIP-712 typed data for signing. Auth required, no payment.",
                    },
                    {
                        "path": "/trading/prepare-enable",
                        "method": "POST",
                        "description": "Get SafeTx hash (for gasless token approvals) + CLOB typed data (for L2 credentials). Requires Safe deployed. Auth required, no payment.",
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
                        "path": "/payment/prepare-deposit",
                        "method": "POST",
                        "description": "Build unsigned BSC transactions for prepaid deposit. Auth required, no payment.",
                        "body": {"amount_usdt": "float (e.g. 1.0 = 100 calls)"},
                    },
                    {
                        "path": "/payment/prepare-pay",
                        "method": "POST",
                        "description": "Build unsigned BSC transaction for a single direct payment (0.01 USDT). Auth required, no payment.",
                    },
                    {
                        "path": "/payment/submit-tx",
                        "method": "POST",
                        "description": "Broadcast a signed BSC transaction. Auth required, no payment.",
                        "body": {"signed_tx": "str (hex-encoded signed raw transaction)"},
                    },
                    {
                        "path": "/deposit/supported-assets",
                        "method": "GET",
                        "description": "List supported chains/tokens for Polymarket deposits.",
                    },
                ],
                "paid_account_setup": [
                    {
                        "path": "/trading/submit-deploy-safe",
                        "method": "POST",
                        "description": "Deploy Safe wallet via Polymarket relayer (gasless). 0.01 USDT per call.",
                        "body": {"signature": "str (0x-prefixed hex, from sign_typed_data)"},
                    },
                    {
                        "path": "/trading/submit-approvals",
                        "method": "POST",
                        "description": "Submit token approvals via Polymarket relayer (gasless). 0.01 USDT per call.",
                        "body": {"signature": "str (personal_sign of SafeTx hash)", "approval_data": "dict (from prepare-enable)"},
                    },
                    {
                        "path": "/trading/submit-credentials",
                        "method": "POST",
                        "description": "Submit EIP-712 signature to derive Polymarket L2 API credentials. 0.01 USDT per call.",
                        "body": {"signature": "str (0x-prefixed hex)", "timestamp": "str (from prepare-enable)"},
                    },
                ],
                "paid_deposit": [
                    {
                        "path": "/deposit/prepare-transfer",
                        "method": "POST",
                        "description": "One-step Polymarket deposit: gets deposit address from Polymarket bridge and builds unsigned BSC USDT transfer. Agent signs and submits via /payment/submit-tx.",
                        "body": {"amount_usdt": "float (amount to deposit)"},
                    },
                    {
                        "path": "/deposit/create",
                        "method": "POST",
                        "description": "Get deposit addresses for funding Polymarket. Returns EVM/Solana/BTC addresses.",
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
                        "path": "/markets/browse",
                        "method": "GET",
                        "description": "Browse markets by category (e.g. sports.nba, crypto.bitcoin, politics.trump). Use /markets/categories to discover paths.",
                        "params": {"category": "str (required, dot path)", "limit": "int (1-100)", "offset": "int", "closed": "bool"},
                    },
                    {
                        "path": "/markets/search",
                        "method": "GET",
                        "description": "Search events across all Polymarket categories. Supports optional category filter.",
                        "params": {"query": "str?", "tag": "str?", "category": "str? (dot path, e.g. sports.nba)", "limit": "int (1-100)", "offset": "int"},
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
                        "path": "/markets/history",
                        "method": "GET",
                        "description": "Search historical (closed) events with resolution data. Supports query and category filters.",
                        "params": {"query": "str?", "category": "str? (prefix match, e.g. politics, sports.soccer)", "limit": "int (1-100)", "offset": "int"},
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
                        "description": "Your Polymarket positions + P&L. Server derives address from your wallet.",
                    },
                    {
                        "path": "/positions/trades",
                        "method": "GET",
                        "description": "Your trade history. Server derives address from your wallet.",
                    },
                    {
                        "path": "/positions/activity",
                        "method": "GET",
                        "description": "Your on-chain activity. Server derives address from your wallet.",
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
                    {
                        "path": "/traders/categories/leaderboard",
                        "method": "GET",
                        "description": "Category leaderboard — top traders in a specific category (e.g. crypto, sports.nba). Synced every 4h from top 200 global traders.",
                        "params": {"category": "str (required, dot path)", "sort_by": "pnl|volume|positions|win_rate", "limit": "int (1-100)", "offset": "int"},
                    },
                    {
                        "path": "/traders/categories/{address}/profile",
                        "method": "GET",
                        "description": "A trader's per-category performance breakdown. Optionally filter to one category for position details.",
                        "params": {"category": "str? (optional, dot path)"},
                    },
                    {
                        "path": "/traders/categories/stats",
                        "method": "GET",
                        "description": "Category aggregate stats: total traders, volume, avg PnL, best/worst performers.",
                        "params": {"category": "str (required, dot path)"},
                    },
                ],
                "paid_trading": [
                    {
                        "path": "/trading/submit-order",
                        "method": "POST",
                        "description": "Submit signed order to Polymarket CLOB. Requires L2 headers.",
                        "body": {"signature": "str", "clob_order": "dict (from prepare-order)", "order_type": "GTC|GTD|FOK|FAK"},
                        "extra_headers": ["X-Poly-Api-Key", "X-Poly-Secret", "X-Poly-Passphrase"],
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
            "workflow_reference": {
                "note": "These describe how each flow works. Only execute when the user requests it.",
                "agentcrab_payment": [
                    "POST /payment/prepare-deposit — server builds unsigned BSC transactions",
                    "Agent signs each transaction locally with eth_account.sign_transaction()",
                    "POST /payment/submit-tx — server broadcasts to BSC",
                    "Balance available immediately for API calls",
                ],
                "deposit": [
                    "POST /deposit/prepare-transfer — server builds unsigned BSC depositErc20 transaction",
                    "Agent signs the transaction locally",
                    "POST /payment/submit-tx — server broadcasts to BSC",
                    "Polymarket automatically bridges funds to USDC.e on Polygon",
                ],
                "withdraw": [
                    "POST /deposit/withdraw — get withdrawal address for destination chain",
                    "Agent sends USDC.e on Polygon to the returned address",
                    "Polymarket bridges funds to destination chain/token",
                ],
                "deploy_safe": [
                    "POST /trading/prepare-deploy-safe — check if Safe exists, get CreateProxy typed data",
                    "Agent signs with sign_typed_data()",
                    "POST /trading/submit-deploy-safe — server deploys Safe via Polymarket relayer (gasless)",
                ],
                "enable_trading": [
                    "POST /trading/prepare-enable — returns SafeTx hash + CLOB typed data",
                    "Agent personal_signs the SafeTx hash (for gasless approvals)",
                    "POST /trading/submit-approvals — server submits to Polymarket relayer (gasless)",
                    "Agent signs CLOB typed data with sign_typed_data()",
                    "POST /trading/submit-credentials — server derives L2 API credentials",
                ],
            },
        },
    }
