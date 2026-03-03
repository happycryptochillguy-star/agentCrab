"""agentCrab MCP Server — expose Polymarket trading tools via Model Context Protocol.

Start with:
    agentcrab-mcp                              # stdio (Claude Code, local agents)
    agentcrab-mcp --transport streamable-http   # HTTP (Claude web, ChatGPT, remote)

Requires AGENTCRAB_PRIVATE_KEY environment variable.
"""

from __future__ import annotations

import atexit
import dataclasses
import json
import logging
import os
import sys

log = logging.getLogger("agentcrab.mcp")


def _serialize(obj) -> str:
    """Convert SDK result (dataclass, list, or dict) to JSON string."""
    if isinstance(obj, list):
        return json.dumps([_to_dict(item) for item in obj], indent=2)
    return json.dumps(_to_dict(obj), indent=2)


def _to_dict(obj):
    """Convert a dataclass to dict (excluding 'raw'), or pass through."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: v for k, v in dataclasses.asdict(obj).items() if k != "raw"}
    if isinstance(obj, dict):
        return obj
    return obj


def _error(e: Exception, tool_name: str = "") -> str:
    """Serialize exception to JSON error response."""
    from agentcrab import AgentCrabError

    if isinstance(e, AgentCrabError):
        log.warning("tool=%s error=%s msg=%s", tool_name, e.error_code, e)
        return json.dumps({"error": e.error_code or "ERROR", "message": str(e)})
    log.error("tool=%s unexpected: %s", tool_name, e, exc_info=True)
    return json.dumps({"error": "INTERNAL_ERROR", "message": str(e)})


def create_server():
    """Create and return a configured FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "Error: MCP SDK not installed. Install with:\n"
            "  pip install agentcrab[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    from agentcrab import AgentCrab

    mcp = FastMCP(
        "agentcrab",
        instructions=(
            "agentCrab gives you full access to Polymarket prediction markets. "
            "You can search markets, check prices, buy/sell shares, manage positions, "
            "set stop-loss/take-profit triggers, and view leaderboards. "
            "Before using any tool, check if a wallet is connected. If not, ask the user "
            "whether they have an existing private key (use connect_wallet) or want to "
            "create a new one (use create_wallet). Never call other tools before a wallet "
            "is connected."
        ),
    )

    _api_url = os.environ.get(
        "AGENTCRAB_API_URL", "https://api.agentcrab.ai/polymarket"
    )
    _client_instance: list[AgentCrab] = []

    def _cleanup() -> None:
        if _client_instance:
            _client_instance[0].close()
            log.info("client closed")

    atexit.register(_cleanup)

    def _init_client(private_key: str) -> AgentCrab:
        """Initialize (or replace) the SDK client with a private key."""
        if _client_instance:
            _client_instance[0].close()
            _client_instance.clear()
        client = AgentCrab(_api_url, private_key)
        _client_instance.append(client)
        log.info("client initialized, wallet=%s", client.address)
        return client

    # Auto-connect if env var is set (for pre-configured setups)
    _auto_key = os.environ.get("AGENTCRAB_PRIVATE_KEY", "")
    if _auto_key:
        _init_client(_auto_key)

    def _get_client() -> AgentCrab:
        if not _client_instance:
            return None  # type: ignore[return-value]
        return _client_instance[0]

    _NOT_CONNECTED = json.dumps({
        "error": "WALLET_NOT_CONNECTED",
        "message": "No wallet connected. Use connect_wallet with your private key, or create_wallet to create a new one.",
    })

    def _require_client() -> AgentCrab | None:
        """Return client or None. Caller should check and return _NOT_CONNECTED."""
        return _get_client()

    # ------------------------------------------------------------------
    # Wallet Setup
    # ------------------------------------------------------------------

    @mcp.tool()
    def connect_wallet(private_key: str) -> str:
        """Connect your existing wallet by providing your private key.

        The private key stays local — it is only used to sign transactions
        on your machine and is never sent to any server.

        Args:
            private_key: Your Ethereum private key (0x...)
        """
        try:
            client = _init_client(private_key)
            return json.dumps({
                "status": "connected",
                "wallet_address": client.address,
                "message": "Wallet connected. You can now search markets, trade, and more.",
            })
        except Exception as e:
            return _error(e, "connect_wallet")

    @mcp.tool()
    def create_wallet() -> str:
        """Create a brand new wallet. Returns the address and private key.

        The wallet works on both BSC (for payments) and Polygon (for trading).
        After creation, the wallet needs to be funded with USDT + BNB on BSC.
        The wallet is automatically connected after creation.
        """
        try:
            result = AgentCrab.create_wallet(_api_url)
            pk = result.get("private_key", "")
            if pk:
                client = _init_client(pk)
                result["status"] = "created_and_connected"
                result["wallet_address"] = client.address
                result["next_steps"] = (
                    "Fund this wallet with USDT and a small amount of BNB on BSC "
                    "for gas fees. Then use deposit() to add API credits."
                )
            return json.dumps(result, indent=2)
        except Exception as e:
            return _error(e, "create_wallet")

    # ------------------------------------------------------------------
    # Discovery & Balance (free)
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_balance() -> str:
        """Check your agentCrab API balance and Polymarket trading balance.

        Returns calls remaining, USDT balance, Safe address, and USDC trading balance.
        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_balance())
        except Exception as e:
            return _error(e, "get_balance")

    @mcp.tool()
    def get_categories() -> str:
        """List available Polymarket market categories.

        Returns categories like 'crypto', 'sports', 'politics', etc.
        Use these as the 'category' filter in search_markets or browse_markets.
        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_categories())
        except Exception as e:
            return _error(e, "get_categories")

    @mcp.tool()
    def get_trading_status() -> str:
        """Check your trading setup status: Safe deployed, approvals, credentials.

        Returns current onboarding status and next_step recommendation.
        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_trading_status())
        except Exception as e:
            return _error(e, "get_trading_status")

    # ------------------------------------------------------------------
    # Market Search (0.01 USDT each)
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_markets(
        query: str,
        category: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search Polymarket prediction markets by keyword.

        Returns markets with titles, outcomes (Yes/No/named), prices, volumes,
        and token_ids needed for trading. Costs 0.01 USDT.

        Args:
            query: Search keywords (e.g. "bitcoin", "US election", "NBA finals")
            category: Optional category filter (e.g. "crypto", "sports")
            limit: Max results (default 10)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            markets = client.search(query, category=category, limit=limit)
            return _serialize(markets)
        except Exception as e:
            return _error(e, "search_markets")

    @mcp.tool()
    def browse_markets(
        category: str | None = None,
        mood: str = "trending",
        limit: int = 10,
    ) -> str:
        """Browse Polymarket markets by category or mood.

        Use this to discover popular markets without a specific search query.
        Costs 0.01 USDT.

        Args:
            category: Category to browse (e.g. "crypto", "sports", "politics")
            mood: Market mood — "trending", "new", or "closing_soon"
            limit: Max results (default 10)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            effective_mood = mood if mood else "trending"
            markets = client.browse(
                category=category or None, mood=effective_mood, limit=limit
            )
            return _serialize(markets)
        except Exception as e:
            return _error(e, "browse_markets")

    @mcp.tool()
    def get_event(event_id: str) -> str:
        """Get full details for a specific Polymarket event.

        Returns all markets and outcomes within the event. Costs 0.01 USDT.

        Args:
            event_id: The event ID from search results
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_event(event_id))
        except Exception as e:
            return _error(e, "get_event")

    @mcp.tool()
    def find_tradeable(
        query: str | None = None,
        category: str | None = None,
        mood: str = "trending",
        min_price: float = 0.10,
        max_price: float = 0.90,
    ) -> str:
        """Find the best liquid, tradeable market in one call.

        Searches markets and returns the highest-volume outcome with an active
        orderbook in the given price range. Returns market info, best outcome,
        and orderbook. Costs 0.01-0.02 USDT (search + orderbook checks).

        Args:
            query: Optional search keywords (if empty, browses by mood)
            category: Optional category filter
            mood: Mood for browsing when no query given (default "trending")
            min_price: Minimum outcome price (default 0.10)
            max_price: Maximum outcome price (default 0.90)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            market, outcome, orderbook = client.find_tradeable(
                query=query,
                category=category,
                mood=mood,
                price_range=(min_price, max_price),
            )
            return json.dumps(
                {
                    "market": _to_dict(market),
                    "outcome": outcome,
                    "orderbook": _to_dict(orderbook),
                },
                indent=2,
            )
        except Exception as e:
            return _error(e, "find_tradeable")

    # ------------------------------------------------------------------
    # Price & Orderbook (0.01 USDT each)
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_price(token_id: str) -> str:
        """Get the current price for a token.

        Returns best bid, best ask, midpoint, spread, and last trade price.
        Costs 0.01 USDT.

        Args:
            token_id: The token ID from market outcomes
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_price(token_id))
        except Exception as e:
            return _error(e, "get_price")

    @mcp.tool()
    def get_orderbook(token_id: str) -> str:
        """Get the full orderbook for a token.

        Returns all bids and asks with prices and sizes.
        Costs 0.01 USDT.

        Args:
            token_id: The token ID from market outcomes
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_orderbook(token_id))
        except Exception as e:
            return _error(e, "get_orderbook")

    # ------------------------------------------------------------------
    # Trading (0.01 USDT each)
    # ------------------------------------------------------------------

    @mcp.tool()
    def buy(token_id: str, size: float, price: float) -> str:
        """Buy shares on Polymarket.

        Automatically sets up trading (Safe, approvals, credentials) on first use.
        Minimum order value is $1 (size * price >= 1). Costs 0.01 USDT.

        Args:
            token_id: Token ID of the outcome to buy
            size: Number of shares to buy
            price: Price per share (0.001 to 0.999)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            log.info("buy token=%s size=%s price=%s", token_id[:12], size, price)
            return _serialize(client.buy(token_id, size, price))
        except Exception as e:
            return _error(e, "buy")

    @mcp.tool()
    def sell(token_id: str, size: float, price: float) -> str:
        """Sell shares on Polymarket.

        Automatically sets up trading on first use. Costs 0.01 USDT.

        Args:
            token_id: Token ID of the outcome to sell
            size: Number of shares to sell
            price: Price per share (0.001 to 0.999)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            log.info("sell token=%s size=%s price=%s", token_id[:12], size, price)
            return _serialize(client.sell(token_id, size, price))
        except Exception as e:
            return _error(e, "sell")

    @mcp.tool()
    def cancel_order(order_id: str) -> str:
        """Cancel a single open order. Costs 0.01 USDT.

        Args:
            order_id: The order ID to cancel
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.cancel_order(order_id))
        except Exception as e:
            return _error(e, "cancel_order")

    @mcp.tool()
    def cancel_all_orders() -> str:
        """Cancel all your open orders. Costs 0.01 USDT."""
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.cancel_all_orders())
        except Exception as e:
            return _error(e, "cancel_all_orders")

    @mcp.tool()
    def get_open_orders() -> str:
        """List your open orders on Polymarket. Costs 0.01 USDT."""
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_open_orders())
        except Exception as e:
            return _error(e, "get_open_orders")

    # ------------------------------------------------------------------
    # Stop Loss / Take Profit
    # ------------------------------------------------------------------

    @mcp.tool()
    def set_stop_loss(
        token_id: str,
        trigger_price: float,
        size: float,
        exit_price: float,
        expires_in_hours: float | None = None,
    ) -> str:
        """Set a stop loss trigger. When price drops to trigger_price, auto-sells.

        Costs 0.01 USDT.

        Args:
            token_id: Token ID of the position to protect
            trigger_price: Price that triggers the stop loss
            size: Number of shares to sell when triggered
            exit_price: Limit price for the exit order
            expires_in_hours: Optional expiry in hours (default: no expiry)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(
                client.set_stop_loss(
                    token_id,
                    trigger_price,
                    size,
                    exit_price,
                    expires_in_hours=expires_in_hours,
                )
            )
        except Exception as e:
            return _error(e, "set_stop_loss")

    @mcp.tool()
    def set_take_profit(
        token_id: str,
        trigger_price: float,
        size: float,
        exit_price: float,
        expires_in_hours: float | None = None,
    ) -> str:
        """Set a take profit trigger. When price rises to trigger_price, auto-sells.

        Costs 0.01 USDT.

        Args:
            token_id: Token ID of the position
            trigger_price: Price that triggers the take profit
            size: Number of shares to sell when triggered
            exit_price: Limit price for the exit order
            expires_in_hours: Optional expiry in hours (default: no expiry)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(
                client.set_take_profit(
                    token_id,
                    trigger_price,
                    size,
                    exit_price,
                    expires_in_hours=expires_in_hours,
                )
            )
        except Exception as e:
            return _error(e, "set_take_profit")

    @mcp.tool()
    def get_triggers() -> str:
        """List your active stop loss and take profit triggers. Free."""
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_triggers())
        except Exception as e:
            return _error(e, "get_triggers")

    @mcp.tool()
    def cancel_trigger(trigger_id: str) -> str:
        """Cancel a stop loss or take profit trigger.

        Args:
            trigger_id: The trigger ID to cancel
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.cancel_trigger(trigger_id))
        except Exception as e:
            return _error(e, "cancel_trigger")

    # ------------------------------------------------------------------
    # Positions & Leaderboard
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_positions() -> str:
        """Get your Polymarket positions with P&L.

        Returns token_id, outcome, size, avg_price, current_price, pnl.
        Costs 0.01 USDT.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_positions())
        except Exception as e:
            return _error(e, "get_positions")

    @mcp.tool()
    def get_trades(limit: int = 20) -> str:
        """Get your recent trade history. Costs 0.01 USDT.

        Args:
            limit: Max trades to return (default 20)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_trades(limit=limit))
        except Exception as e:
            return _error(e, "get_trades")

    @mcp.tool()
    def get_leaderboard(limit: int = 20) -> str:
        """Get the Polymarket global trader leaderboard. Costs 0.01 USDT.

        Args:
            limit: Number of top traders (default 20)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_leaderboard(limit=limit))
        except Exception as e:
            return _error(e, "get_leaderboard")

    @mcp.tool()
    def get_category_leaderboard(category: str, limit: int = 20) -> str:
        """Get the leaderboard for a specific category. Costs 0.01 USDT.

        Args:
            category: Category slug (e.g. "crypto", "sports.nba")
            limit: Number of top traders (default 20)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(
                client.get_category_leaderboard(category, limit=limit)
            )
        except Exception as e:
            return _error(e, "get_category_leaderboard")

    # ------------------------------------------------------------------
    # Payment
    # ------------------------------------------------------------------

    @mcp.tool()
    def deposit(amount_usdt: float) -> str:
        """Deposit USDT to your agentCrab prepaid balance (for API call credits).

        Signs and submits BSC transactions automatically.
        Each API call costs 0.01 USDT.

        Args:
            amount_usdt: Amount of USDT to deposit
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            log.info("deposit amount=%s USDT", amount_usdt)
            return _serialize(client.deposit(amount_usdt))
        except Exception as e:
            return _error(e, "deposit")

    @mcp.tool()
    def deposit_to_polymarket(amount_usdt: float) -> str:
        """Deposit USDT from BSC to your Polymarket trading balance.

        Converts BSC USDT to Polygon USDC.e in your Polymarket Safe.
        Signs and submits transactions automatically.

        Args:
            amount_usdt: Amount of USDT to deposit to Polymarket
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            log.info("deposit_to_polymarket amount=%s USDT", amount_usdt)
            return _serialize(client.deposit_to_polymarket(amount_usdt))
        except Exception as e:
            return _error(e, "deposit_to_polymarket")

    return mcp


def main():
    """CLI entry point for the agentCrab MCP server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="agentCrab MCP Server — Polymarket trading tools for AI agents",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="HTTP port (default: 8000)"
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Log level (default: INFO)"
    )
    args = parser.parse_args()

    # Logging to stderr so it doesn't interfere with stdio transport
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    server = create_server()
    log.info("starting transport=%s", args.transport)
    if args.transport == "streamable-http":
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
