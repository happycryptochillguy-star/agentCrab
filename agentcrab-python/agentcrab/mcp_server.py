"""agentCrab MCP Server — expose Polymarket trading tools via Model Context Protocol.

Start with:
    agentcrab-mcp                              # stdio (Claude Code, local agents)
    agentcrab-mcp --transport streamable-http   # HTTP (Claude web, ChatGPT, remote)

Optional: set AGENTCRAB_PRIVATE_KEY env var, or use connect_wallet / create_wallet tools.
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


# Fields that must never be serialized to MCP output
_REDACTED_FIELDS = {"raw", "api_key", "secret", "passphrase"}


def _to_dict(obj):
    """Convert a dataclass to dict (excluding raw + credential fields), or pass through."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: v for k, v in dataclasses.asdict(obj).items() if k not in _REDACTED_FIELDS}
    if isinstance(obj, dict):
        return obj
    return obj


def _error(e: Exception, tool_name: str = "") -> str:
    """Serialize exception to JSON error response."""
    from agentcrab import AgentCrabError

    if isinstance(e, AgentCrabError):
        log.warning("tool=%s error=%s msg=%s", tool_name, e.error_code, e)
        return json.dumps({"error": e.error_code or "ERROR", "message": str(e)})
    log.error("tool=%s unexpected: %s", tool_name, e)
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
        if _client_instance:
            _client_instance[0].close()
            _client_instance.clear()
        client = AgentCrab(_api_url, private_key)
        _client_instance.append(client)
        log.info("client initialized, wallet=%s", client.address)
        return client

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

    # ==================================================================
    # Wallet Setup
    # ==================================================================

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

    # ==================================================================
    # Discovery & Balance (free)
    # ==================================================================

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
    def get_wallet_balance() -> str:
        """Check your BSC wallet balance (USDT + BNB).

        Use this before depositing to see if you have enough funds.
        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_wallet_balance())
        except Exception as e:
            return _error(e, "get_wallet_balance")

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

    @mcp.tool()
    def get_categories() -> str:
        """List available Polymarket market categories.

        Returns hierarchical categories like 'crypto', 'sports.nba', 'politics', etc.
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

    # ==================================================================
    # $CRAB Token & Points (free)
    # ==================================================================

    @mcp.tool()
    def get_points() -> str:
        """Get your $CRAB airdrop points breakdown (deposit + usage points).

        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_points())
        except Exception as e:
            return _error(e, "get_points")

    @mcp.tool()
    def get_points_leaderboard(limit: int = 20) -> str:
        """Get the $CRAB points leaderboard. Free.

        Args:
            limit: Number of top users (default 20)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_points_leaderboard(limit=limit))
        except Exception as e:
            return _error(e, "get_points_leaderboard")

    @mcp.tool()
    def get_token_info() -> str:
        """Get $CRAB token info, rules, and stats. Free."""
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_token_info())
        except Exception as e:
            return _error(e, "get_token_info")

    # ==================================================================
    # Market Search (0.01 USDT each)
    # ==================================================================

    @mcp.tool()
    def search_markets(
        query: str,
        tag: str | None = None,
        category: str | None = None,
        limit: int = 10,
        closed: bool = False,
    ) -> str:
        """Search Polymarket prediction markets by keyword.

        Smart search: auto-detects tags from keywords (e.g. "NBA champion"
        auto-filters to NBA markets). Scores results by relevance.
        Costs 0.01 USDT.

        Args:
            query: Search keywords (e.g. "bitcoin", "Trump", "NBA finals")
            tag: Optional tag filter (e.g. "bitcoin", "nba", "nfl")
            category: Optional category filter (e.g. "crypto", "sports.nba")
            limit: Max results (default 10)
            closed: Include resolved/closed markets (default false)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            markets = client.search(
                query, tag=tag, category=category, limit=limit, closed=closed
            )
            return _serialize(markets)
        except Exception as e:
            return _error(e, "search_markets")

    @mcp.tool()
    def browse_markets(
        category: str | None = None,
        mood: str = "trending",
        limit: int = 10,
        closed: bool = False,
    ) -> str:
        """Browse Polymarket markets by category or mood.

        Use this to discover markets without a specific query. Great for
        "show me something interesting" or "what's trending in crypto".
        Costs 0.01 USDT.

        Args:
            category: Category to browse (e.g. "crypto", "sports.nba", "politics")
            mood: One of "trending", "interesting", "controversial", "new", "closing_soon"
            limit: Max results (default 10)
            closed: Include resolved/closed markets (default false)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            effective_mood = mood if mood else "trending"
            markets = client.browse(
                category=category or None, mood=effective_mood,
                limit=limit, closed=closed,
            )
            return _serialize(markets)
        except Exception as e:
            return _error(e, "browse_markets")

    @mcp.tool()
    def get_event(event_id: str) -> str:
        """Get full details for a specific Polymarket event by ID. Costs 0.01 USDT.

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
    def get_event_by_slug(slug: str) -> str:
        """Get a Polymarket event by its URL slug. Costs 0.01 USDT.

        Useful when someone shares a Polymarket link — extract the slug
        from the URL (e.g. "will-bitcoin-hit-100k-in-2026").

        Args:
            slug: The human-readable slug from the Polymarket URL
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_event_by_slug(slug))
        except Exception as e:
            return _error(e, "get_event_by_slug")

    @mcp.tool()
    def get_market(market_id: str) -> str:
        """Get a single market by its market ID (raw details). Costs 0.01 USDT.

        Args:
            market_id: The market ID (condition_id)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_market(market_id))
        except Exception as e:
            return _error(e, "get_market")

    @mcp.tool()
    def search_history(
        query: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search closed/resolved Polymarket events from history.

        Find past markets and their resolutions. Costs 0.01 USDT.

        Args:
            query: Optional keyword search
            category: Optional category prefix (e.g. "sports", "crypto")
            limit: Max results (default 20)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.search_history(query=query, category=category, limit=limit))
        except Exception as e:
            return _error(e, "search_history")

    @mcp.tool()
    def sync_history() -> str:
        """Trigger a background sync of closed events. Free.

        Call this to update the historical events database.
        Throttled to once per hour.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.sync_history())
        except Exception as e:
            return _error(e, "sync_history")

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
            mood: Mood for browsing when no query ("trending", "interesting", "controversial", "new", "closing_soon")
            min_price: Minimum outcome price (default 0.10)
            max_price: Maximum outcome price (default 0.90)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            market, outcome, orderbook = client.find_tradeable(
                query=query, category=category, mood=mood,
                price_range=(min_price, max_price),
            )
            return json.dumps({
                "market": _to_dict(market),
                "outcome": outcome,
                "orderbook": _to_dict(orderbook),
            }, indent=2)
        except Exception as e:
            return _error(e, "find_tradeable")

    # ==================================================================
    # Price & Orderbook (0.01 USDT each)
    # ==================================================================

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

        Returns all bids and asks with prices and sizes. Costs 0.01 USDT.

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

    # ==================================================================
    # Trading (0.01 USDT each)
    # ==================================================================

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
    def batch_order(orders: str) -> str:
        """Place multiple orders at once. Costs N x 0.01 USDT.

        Args:
            orders: JSON array of order objects, each with:
                    token_id (str), side ("BUY"/"SELL"), size (float), price (float).
                    Example: [{"token_id":"abc","side":"BUY","size":5,"price":0.6}]
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            order_list = json.loads(orders)
            log.info("batch_order count=%d", len(order_list))
            return _serialize(client.batch_order(order_list))
        except json.JSONDecodeError as e:
            return _error(ValueError(f"Invalid JSON for orders: {e}"), "batch_order")
        except Exception as e:
            return _error(e, "batch_order")

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
    def get_open_orders(market: str | None = None) -> str:
        """List your open orders on Polymarket. Costs 0.01 USDT.

        Args:
            market: Optional market filter (condition_id)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_open_orders(market=market))
        except Exception as e:
            return _error(e, "get_open_orders")

    @mcp.tool()
    def refresh_balance() -> str:
        """Refresh Polymarket's cached view of your trading balance.

        Call this after depositing USDC.e to Polymarket (wait 1-2 min for relay first).
        Free — no charge for this call.
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.refresh_balance())
        except Exception as e:
            return _error(e, "refresh_balance")

    # ==================================================================
    # Stop Loss / Take Profit
    # ==================================================================

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
            return _serialize(client.set_stop_loss(
                token_id, trigger_price, size, exit_price,
                expires_in_hours=expires_in_hours,
            ))
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
            return _serialize(client.set_take_profit(
                token_id, trigger_price, size, exit_price,
                expires_in_hours=expires_in_hours,
            ))
        except Exception as e:
            return _error(e, "set_take_profit")

    @mcp.tool()
    def get_triggers(
        status: str | None = None,
        token_id: str | None = None,
    ) -> str:
        """List your stop loss and take profit triggers. Free.

        Args:
            status: Optional filter — "active", "triggered", "cancelled", "expired"
            token_id: Optional filter by token
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_triggers(status=status, token_id=token_id))
        except Exception as e:
            return _error(e, "get_triggers")

    @mcp.tool()
    def cancel_trigger(trigger_id: str) -> str:
        """Cancel a single stop loss or take profit trigger.

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

    @mcp.tool()
    def cancel_all_triggers(token_id: str | None = None) -> str:
        """Cancel all triggers, optionally filtered by token.

        Args:
            token_id: Optional — only cancel triggers for this token
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.cancel_all_triggers(token_id=token_id))
        except Exception as e:
            return _error(e, "cancel_all_triggers")

    # ==================================================================
    # Positions & Activity
    # ==================================================================

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
    def get_activity(limit: int = 50) -> str:
        """Get your on-chain activity (trades, splits, merges, redemptions). Costs 0.01 USDT.

        Args:
            limit: Max records to return (default 50)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_activity(limit=limit))
        except Exception as e:
            return _error(e, "get_activity")

    # ==================================================================
    # Other Traders (0.01 USDT each)
    # ==================================================================

    @mcp.tool()
    def get_trader_positions(address: str) -> str:
        """Get another trader's Polymarket positions. Costs 0.01 USDT.

        Use this to see what top traders are holding (copy-trading research).

        Args:
            address: The trader's wallet address (EOA or Safe)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_trader_positions(address))
        except Exception as e:
            return _error(e, "get_trader_positions")

    @mcp.tool()
    def get_trader_trades(address: str, limit: int = 50) -> str:
        """Get another trader's recent trades. Costs 0.01 USDT.

        Args:
            address: The trader's wallet address
            limit: Max trades to return (default 50)
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_trader_trades(address, limit=limit))
        except Exception as e:
            return _error(e, "get_trader_trades")

    # ==================================================================
    # Leaderboard (0.01 USDT each)
    # ==================================================================

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
            return _serialize(client.get_category_leaderboard(category, limit=limit))
        except Exception as e:
            return _error(e, "get_category_leaderboard")

    @mcp.tool()
    def get_trader_category_profile(address: str, category: str | None = None) -> str:
        """Get a trader's per-category breakdown with optional positions. Costs 0.01 USDT.

        Args:
            address: The trader's wallet address
            category: Optional category filter
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_trader_category_profile(address, category=category))
        except Exception as e:
            return _error(e, "get_trader_category_profile")

    @mcp.tool()
    def get_category_stats(category: str) -> str:
        """Get aggregate stats for a category (total_traders, avg_pnl, etc.). Costs 0.01 USDT.

        Args:
            category: Category slug (e.g. "crypto", "sports.nba")
        """
        client = _get_client()
        if not client:
            return _NOT_CONNECTED
        try:
            return _serialize(client.get_category_stats(category))
        except Exception as e:
            return _error(e, "get_category_stats")

    # ==================================================================
    # Payment
    # ==================================================================

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
        "--transport", default="stdio",
        choices=["stdio", "streamable-http"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

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
