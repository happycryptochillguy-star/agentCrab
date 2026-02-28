from fastapi import APIRouter

from api.config import settings

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/capabilities")
async def get_capabilities():
    """Return full API capabilities for agent discovery. Free, no auth required."""
    return {
        "status": "ok",
        "summary": "agentWay Polymarket middleware capabilities. Use this to discover all available endpoints, authentication, and payment methods.",
        "data": {
            "auth": {
                "method": "EIP-191 personal_sign",
                "message_format": "agentway:{unix_timestamp}",
                "timestamp_tolerance_seconds": settings.signature_max_age_seconds,
                "required_headers": {
                    "X-Wallet-Address": "Your BSC wallet address (checksummed or lowercase)",
                    "X-Signature": "Hex signature of the message (0x-prefixed)",
                    "X-Message": "The signed message, e.g. agentway:1709136000",
                    "X-Payment-Mode": "direct or prepaid",
                    "X-Tx-Hash": "(direct mode only) BSC tx hash from calling pay()",
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
                            "AgentWayPayment.pay()",
                            "Use the tx hash in X-Tx-Hash header",
                        ],
                    },
                    "prepaid": {
                        "description": "Deposit once, use many times. Background scanner detects deposits every ~15s.",
                        "steps": [
                            "USDT.approve(CONTRACT_ADDRESS, amount)",
                            "AgentWayPayment.deposit(amount)",
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
            "endpoints": [
                {
                    "path": "/football/markets",
                    "method": "GET",
                    "description": "Get active football/soccer prediction markets from Polymarket.",
                    "auth_required": True,
                    "payment_required": True,
                    "parameters": {
                        "league": {
                            "type": "string",
                            "required": False,
                            "description": "Filter by league slug",
                            "values": [
                                "premier_league", "la_liga", "ucl",
                                "champions_league", "serie_a", "bundesliga",
                                "ligue_1", "mls", "world_cup", "europa_league",
                            ],
                        },
                        "limit": {
                            "type": "int",
                            "required": False,
                            "default": 20,
                            "min": 1,
                            "max": 100,
                        },
                        "offset": {
                            "type": "int",
                            "required": False,
                            "default": 0,
                        },
                    },
                    "example_response": {
                        "status": "ok",
                        "summary": "Found 3 active football events on Polymarket. Top event: \"Arsenal vs Chelsea\" with $45,000 in volume.",
                        "data": [
                            {
                                "event_id": "12345",
                                "title": "Arsenal vs Chelsea - Premier League",
                                "slug": "arsenal-vs-chelsea-premier-league",
                                "markets": [
                                    {
                                        "question": "Will Arsenal win against Chelsea?",
                                        "outcomes": [
                                            {"outcome": "Yes", "price": 0.65},
                                            {"outcome": "No", "price": 0.35},
                                        ],
                                        "volume": 45000.0,
                                        "liquidity": 12000.0,
                                    }
                                ],
                                "volume": 45000.0,
                            }
                        ],
                    },
                },
                {
                    "path": "/payment/balance",
                    "method": "GET",
                    "description": "Check prepaid balance and remaining API calls.",
                    "auth_required": True,
                    "payment_required": False,
                    "parameters": {},
                    "example_response": {
                        "status": "ok",
                        "summary": "Wallet 0xABC123... has 50 API calls remaining (0.5000 USDT).",
                        "data": {
                            "wallet_address": "0xabc123...",
                            "total_deposited_wei": "1000000000000000000",
                            "total_consumed_wei": "500000000000000000",
                            "remaining_wei": "500000000000000000",
                            "calls_remaining": 50,
                        },
                    },
                },
                {
                    "path": "/payment/verify",
                    "method": "POST",
                    "description": "Verify a direct payment transaction.",
                    "auth_required": True,
                    "payment_required": False,
                    "parameters": {
                        "tx_hash": {
                            "type": "string",
                            "required": True,
                            "description": "BSC transaction hash to verify",
                        },
                    },
                    "example_response": {
                        "status": "ok",
                        "summary": "Transaction 0xabc123... verified. DirectPayment confirmed.",
                        "data": {
                            "tx_hash": "0xabc123...",
                            "verified": True,
                            "wallet_address": "0xdef456...",
                            "message": "Payment verified successfully.",
                        },
                    },
                },
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Check if the API is running.",
                    "auth_required": False,
                    "payment_required": False,
                    "parameters": {},
                },
                {
                    "path": "/agent/capabilities",
                    "method": "GET",
                    "description": "This endpoint. Returns full API capabilities for agent discovery.",
                    "auth_required": False,
                    "payment_required": False,
                    "parameters": {},
                },
            ],
            "error_codes": {
                "INVALID_SIGNATURE": {
                    "http_status": 401,
                    "meaning": "Signature verification failed",
                    "fix": "Re-sign 'agentway:{current_unix_timestamp}' with your wallet key. Timestamp must be within 5 minutes.",
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
        },
    }
