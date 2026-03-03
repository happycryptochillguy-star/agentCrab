"""Main AgentCrab client — all public methods."""

from __future__ import annotations

from eth_account import Account

from ._exceptions import SetupRequired
from ._http import HttpTransport, _extract_data
from ._signer import sign_safe_tx_hash, sign_transaction, sign_typed_data
from ._types import (
    Activity,
    Balance,
    BatchOrderResult,
    DepositResult,
    HistoricalEvent,
    Market,
    Orderbook,
    OrderResult,
    Position,
    Price,
    SetupResult,
    Trade,
    Trigger,
    TriggerResult,
)


class AgentCrab:
    """agentCrab SDK client — turn any Python script into a Polymarket assistant.

    Usage::

        from agentcrab import AgentCrab

        client = AgentCrab("https://api.agentcrab.ai/polymarket", "0xPRIVATE_KEY")
        markets = client.search("bitcoin")
        result = client.buy(token_id, size=5.0, price=0.65)
    """

    def __init__(
        self,
        api_url: str,
        private_key: str,
        payment_mode: str = "prepaid",
        timeout: float = 60.0,
    ):
        self._private_key = private_key
        self._account = Account.from_key(private_key)
        self.address: str = self._account.address
        self._l2_creds: dict | None = None
        self._http = HttpTransport(
            base_url=api_url,
            private_key=private_key,
            address=self.address,
            payment_mode=payment_mode,
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> AgentCrab:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Wallet (static)
    # ------------------------------------------------------------------

    @staticmethod
    def create_wallet(api_url: str) -> dict:
        """Create a new wallet via the server (no private key needed).

        Returns ``{"address": "0x...", "private_key": "0x..."}``.
        """
        import httpx

        resp = httpx.post(f"{api_url.rstrip('/')}/agent/create-wallet", timeout=30)
        resp.raise_for_status()
        return _extract_data(resp.json())

    # ------------------------------------------------------------------
    # Balance & Payment
    # ------------------------------------------------------------------

    def get_balance(self) -> Balance:
        """Get prepaid balance on agentCrab + Polymarket trading balance."""
        resp = self._http.get("/payment/balance")
        d = _extract_data(resp)
        return Balance(
            wallet_address=d.get("wallet_address", self.address),
            calls_remaining=d.get("calls_remaining", 0),
            remaining_usdt=d.get("remaining_usdt", 0.0),
            safe_address=d.get("safe_address", ""),
            trading_balance_usdc=d.get("trading_balance_usdc", 0.0),
            raw=d,
        )

    def deposit(self, amount_usdt: float) -> DepositResult:
        """Deposit USDT to agentCrab prepaid balance on BSC.

        Full flow: prepare-deposit -> sign txs -> submit-tx.
        """
        # 1. Prepare
        prep = self._http.post("/payment/prepare-deposit", json={"amount_usdt": amount_usdt})
        data = _extract_data(prep)

        # 2. Sign all transactions
        txs = data.get("transactions", [])
        signed = [sign_transaction(self._private_key, t["transaction"]) for t in txs]

        # 3. Submit
        submit = self._http.post(
            "/payment/submit-tx",
            json={"signed_txs": signed, "chain": "bsc"},
        )
        submit_data = _extract_data(submit)
        tx_hashes = submit_data if isinstance(submit_data, list) else submit_data.get("tx_hashes", [])

        return DepositResult(
            tx_hashes=tx_hashes if isinstance(tx_hashes, list) else [],
            summary=submit.get("summary", f"Deposited {amount_usdt} USDT"),
            raw=submit_data if isinstance(submit_data, dict) else {"results": submit_data},
        )

    def deposit_to_polymarket(self, amount_usdt: float) -> DepositResult:
        """Deposit USDT from BSC to Polymarket trading balance.

        Full flow: prepare-transfer -> sign txs -> submit-tx.
        """
        # 1. Prepare
        prep = self._http.post("/deposit/prepare-transfer", json={"amount_usdt": amount_usdt}, paid=True)
        data = _extract_data(prep)

        # 2. Sign all transactions
        txs = data.get("transactions", [])
        signed = [sign_transaction(self._private_key, t["transaction"]) for t in txs]

        # 3. Submit
        submit = self._http.post(
            "/payment/submit-tx",
            json={"signed_txs": signed, "chain": "bsc"},
        )
        submit_data = _extract_data(submit)
        tx_hashes = submit_data if isinstance(submit_data, list) else submit_data.get("tx_hashes", [])

        return DepositResult(
            tx_hashes=tx_hashes if isinstance(tx_hashes, list) else [],
            summary=submit.get("summary", f"Deposited {amount_usdt} USDT to Polymarket"),
            raw=submit_data if isinstance(submit_data, dict) else {"results": submit_data},
        )

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        tag: str | None = None,
        category: str | None = None,
        limit: int = 10,
        offset: int = 0,
        closed: bool = False,
    ) -> list[Market]:
        """Search Polymarket events."""
        params: dict = {"query": query, "limit": limit, "offset": offset, "closed": closed}
        if tag:
            params["tag"] = tag
        if category:
            params["category"] = category

        resp = self._http.get("/markets/search", params=params, paid=True)
        data = _extract_data(resp)
        events = data if isinstance(data, list) else data.get("events", [])
        return [_parse_market(e) for e in events]

    def browse(
        self,
        category: str | None = None,
        mood: str | None = None,
        limit: int = 10,
        offset: int = 0,
        closed: bool = False,
    ) -> list[Market]:
        """Browse Polymarket events by category or mood."""
        params: dict = {"limit": limit, "offset": offset, "closed": closed}
        if category:
            params["category"] = category
        if mood:
            params["mood"] = mood

        resp = self._http.get("/markets/browse", params=params, paid=True)
        data = _extract_data(resp)
        events = data if isinstance(data, list) else data.get("events", [])
        return [_parse_market(e) for e in events]

    def get_event(self, event_id: str) -> Market:
        """Get a single event by ID."""
        resp = self._http.get(f"/markets/events/{event_id}", paid=True)
        d = _extract_data(resp)
        return _parse_market(d)

    def get_market(self, market_id: str) -> dict:
        """Get a single market by ID (raw dict)."""
        resp = self._http.get(f"/markets/{market_id}", paid=True)
        return _extract_data(resp)

    def search_history(
        self,
        query: str | None = None,
        category: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[HistoricalEvent]:
        """Search closed Polymarket events from local history DB."""
        params: dict = {"limit": limit, "offset": offset}
        if query:
            params["query"] = query
        if category:
            params["category"] = category
        resp = self._http.get("/markets/history", params=params, paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("events", [])
        return [
            HistoricalEvent(
                event_id=e.get("event_id", e.get("id", "")),
                title=e.get("title", ""),
                category=e.get("category"),
                volume=_parse_volume(e.get("volume")),
                resolution=e.get("resolution"),
                closed_time=e.get("closed_time"),
                raw=e,
            )
            for e in items
        ]

    def sync_history(self) -> dict:
        """Trigger background sync of closed events (free, auth only)."""
        resp = self._http.post("/markets/history/sync")
        return _extract_data(resp)

    def get_orderbook(self, token_id: str) -> Orderbook:
        """Get orderbook for a token."""
        resp = self._http.get(f"/orderbook/{token_id}", paid=True)
        d = _extract_data(resp)
        return Orderbook(
            token_id=d.get("token_id", token_id),
            bids=d.get("bids", []),
            asks=d.get("asks", []),
            best_bid=d.get("best_bid"),
            best_ask=d.get("best_ask"),
            spread=d.get("spread"),
            midpoint=d.get("midpoint"),
            raw=d,
        )

    def get_price(self, token_id: str) -> Price:
        """Get price summary for a token."""
        resp = self._http.get(f"/prices/{token_id}", paid=True)
        d = _extract_data(resp)
        return Price(
            token_id=d.get("token_id", token_id),
            best_bid=d.get("best_bid"),
            best_ask=d.get("best_ask"),
            midpoint=d.get("midpoint"),
            spread=d.get("spread"),
            last_trade_price=d.get("last_trade_price"),
            raw=d,
        )

    def find_tradeable(
        self,
        query: str | None = None,
        category: str | None = None,
        mood: str = "trending",
        price_range: tuple[float, float] = (0.10, 0.90),
        limit: int = 10,
    ) -> tuple[Market, dict, Orderbook]:
        """Find a liquid, tradeable market with one call.

        Searches/browses markets, finds the highest-volume outcome with an
        active orderbook in the given price range.

        Returns ``(market, outcome, orderbook)`` where outcome is the dict
        from ``market.outcomes`` (has ``token_id``, ``price``, etc.).

        Raises ``AgentCrabError`` if no tradeable market is found.
        """
        from ._exceptions import AgentCrabError

        # Search or browse
        if query:
            markets = self.search(query, category=category, limit=limit)
        else:
            markets = self.browse(category=category, mood=mood, limit=limit)

        lo, hi = price_range
        best: tuple[Market, dict, Orderbook] | None = None
        best_vol = -1.0

        for m in markets:
            vol = m.volume or 0.0
            for o in m.outcomes:
                if not isinstance(o, dict) or not o.get("token_id"):
                    continue
                p = o.get("price")
                if p is None:
                    continue
                try:
                    pf = float(p)
                except (ValueError, TypeError):
                    continue
                if not (lo <= pf <= hi):
                    continue
                if vol <= best_vol:
                    continue
                # Verify orderbook has liquidity
                try:
                    ob = self.get_orderbook(o["token_id"])
                    if ob.best_bid and ob.best_ask:
                        best = (m, o, ob)
                        best_vol = vol
                except Exception:
                    continue

        if best is None:
            raise AgentCrabError("No tradeable market found matching criteria.", error_code="NOT_FOUND")
        return best

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> list[Position]:
        """Get your Polymarket positions (server derives Safe from EOA)."""
        resp = self._http.get("/positions", paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("positions", [])
        return [
            Position(
                token_id=p.get("token_id", ""),
                outcome=p.get("outcome", ""),
                size=p.get("size", "0"),
                question=p.get("question"),
                market_slug=p.get("market_slug"),
                avg_price=p.get("avg_price"),
                current_price=p.get("current_price"),
                pnl=p.get("pnl"),
                pnl_percent=p.get("pnl_percent"),
                raw=p,
            )
            for p in items
        ]

    def get_trades(self, limit: int = 20, offset: int = 0) -> list[Trade]:
        """Get your recent trades."""
        resp = self._http.get("/positions/trades", params={"limit": limit, "offset": offset}, paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("trades", [])
        return [
            Trade(
                side=t.get("side", ""),
                size=t.get("size", "0"),
                price=t.get("price", "0"),
                trade_id=t.get("trade_id"),
                market_slug=t.get("market_slug"),
                outcome=t.get("outcome"),
                timestamp=t.get("timestamp"),
                raw=t,
            )
            for t in items
        ]

    def get_activity(self, limit: int = 50, offset: int = 0) -> list[Activity]:
        """Get your on-chain activity (trades, splits, merges, redemptions)."""
        resp = self._http.get("/positions/activity", params={"limit": limit, "offset": offset}, paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("activity", [])
        return [
            Activity(
                type=a.get("type", ""),
                amount=str(a.get("amount", "0")),
                timestamp=str(a["timestamp"]) if a.get("timestamp") is not None else None,
                raw=a,
            )
            for a in items
        ]

    # ------------------------------------------------------------------
    # Other Traders
    # ------------------------------------------------------------------

    def get_trader_positions(self, address: str) -> list[Position]:
        """Get any trader's Polymarket positions."""
        resp = self._http.get(f"/traders/{address}/positions", paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("positions", [])
        return [
            Position(
                token_id=p.get("token_id", ""),
                outcome=p.get("outcome", ""),
                size=p.get("size", "0"),
                question=p.get("question"),
                market_slug=p.get("market_slug"),
                avg_price=p.get("avg_price"),
                current_price=p.get("current_price"),
                pnl=p.get("pnl"),
                pnl_percent=p.get("pnl_percent"),
                raw=p,
            )
            for p in items
        ]

    def get_trader_trades(self, address: str, limit: int = 50, offset: int = 0) -> list[Trade]:
        """Get any trader's recent trades."""
        resp = self._http.get(f"/traders/{address}/trades", params={"limit": limit, "offset": offset}, paid=True)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("trades", [])
        return [
            Trade(
                side=t.get("side", ""),
                size=t.get("size", "0"),
                price=t.get("price", "0"),
                trade_id=t.get("trade_id"),
                market_slug=t.get("market_slug"),
                outcome=t.get("outcome"),
                timestamp=t.get("timestamp"),
                raw=t,
            )
            for t in items
        ]

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    def get_leaderboard(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Get Polymarket leaderboard."""
        resp = self._http.get("/traders/leaderboard", params={"limit": limit, "offset": offset}, paid=True)
        data = _extract_data(resp)
        return data if isinstance(data, list) else data.get("leaderboard", [])

    def get_category_leaderboard(
        self,
        category: str,
        sort_by: str = "pnl",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Get category-specific leaderboard (e.g. 'crypto', 'sports.nba')."""
        resp = self._http.get(
            "/traders/categories/leaderboard",
            params={"category": category, "sort_by": sort_by, "limit": limit, "offset": offset},
            paid=True,
        )
        return _extract_data(resp)

    def get_trader_category_profile(self, address: str, category: str | None = None) -> dict:
        """Get a trader's per-category breakdown with optional positions."""
        params = {"category": category} if category else None
        resp = self._http.get(f"/traders/categories/{address}/profile", params=params, paid=True)
        return _extract_data(resp)

    def get_category_stats(self, category: str) -> dict:
        """Get aggregate stats for a category (total_traders, avg_pnl, etc.)."""
        resp = self._http.get("/traders/categories/stats", params={"category": category}, paid=True)
        return _extract_data(resp)

    # ------------------------------------------------------------------
    # Trading Setup
    # ------------------------------------------------------------------

    def set_credentials(self, api_key: str, secret: str, passphrase: str) -> None:
        """Manually set L2 trading credentials (if you already have them)."""
        self._l2_creds = {
            "api_key": api_key,
            "secret": secret,
            "passphrase": passphrase,
        }

    def setup_trading(self) -> SetupResult:
        """One-call trading setup: Safe deploy + approvals + L2 credentials.

        Idempotent — skips steps already completed. Tries server-cached
        credentials first; if cached, Safe and approvals are already done,
        so we skip all on-chain checks (saves 2 API roundtrips).
        """
        steps: list[str] = []

        # Step 0: Try cached credentials first (free).
        # If cached, Safe + approvals are guaranteed complete — early return.
        cached = self._fetch_cached_credentials()
        if cached:
            self._l2_creds = cached
            return SetupResult(
                safe_address="",  # already deployed, address not needed
                api_key=cached["api_key"],
                secret=cached["secret"],
                passphrase=cached["passphrase"],
                steps_completed=["credentials_cached"],
                raw=cached,
            )

        # Step 1: Deploy Safe (if needed)
        prep_safe = self._http.post("/trading/prepare-deploy-safe")
        safe_data = _extract_data(prep_safe)
        safe_address = safe_data.get("safe_address", "")

        if not safe_data.get("already_deployed"):
            typed_data = safe_data["typed_data"]
            sig = sign_typed_data(self._private_key, typed_data)
            self._http.post(
                "/trading/submit-deploy-safe",
                json={"signature": sig},
                paid=True,
            )
            steps.append("safe_deployed")
        else:
            steps.append("safe_already_deployed")

        # Step 2: Prepare enable (approvals + CLOB auth)
        prep_enable = self._http.post("/trading/prepare-enable")
        enable_data = _extract_data(prep_enable)

        # Step 3: Submit approvals (if needed)
        if enable_data.get("approvals_needed") and enable_data.get("approval_data"):
            approval_data = enable_data["approval_data"]
            safe_tx_hash = approval_data["hash"]
            sig = sign_safe_tx_hash(self._private_key, safe_tx_hash)
            self._http.post(
                "/trading/submit-approvals",
                json={"signature": sig, "approval_data": approval_data},
                paid=True,
            )
            steps.append("approvals_submitted")
        else:
            steps.append("approvals_already_set")

        # Step 4: Derive new credentials
        clob_typed_data = enable_data["clob_typed_data"]
        timestamp = clob_typed_data["message"]["timestamp"]
        sig = sign_typed_data(self._private_key, clob_typed_data)
        creds_resp = self._http.post(
            "/trading/submit-credentials",
            json={"signature": sig, "timestamp": timestamp},
            paid=True,
        )
        creds_data = _extract_data(creds_resp)
        api_key = creds_data["api_key"]
        secret = creds_data["secret"]
        passphrase = creds_data["passphrase"]
        steps.append("credentials_derived")

        # Store for future trading calls
        self._l2_creds = {
            "api_key": api_key,
            "secret": secret,
            "passphrase": passphrase,
        }

        return SetupResult(
            safe_address=safe_address,
            api_key=api_key,
            secret=secret,
            passphrase=passphrase,
            steps_completed=steps,
            raw={"api_key": api_key, "secret": secret, "passphrase": passphrase},
        )

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------

    def _fetch_cached_credentials(self) -> dict | None:
        """Try to fetch cached L2 credentials from the server (free)."""
        try:
            resp = self._http.get("/trading/credentials")
            data = _extract_data(resp)
            if data and data.get("api_key"):
                return data
        except Exception:
            pass
        return None

    def _require_l2(self) -> dict:
        if not self._l2_creds:
            # Try server cache before raising
            cached = self._fetch_cached_credentials()
            if cached:
                self._l2_creds = cached
            else:
                raise SetupRequired()
        return self._l2_creds

    def refresh_balance(self) -> dict:
        """Tell the CLOB to refresh its cached balance/allowances.

        Call after depositing USDC.e to Polymarket (wait 1-2 min for relay first).
        Also called automatically during ``setup_trading()``.
        """
        creds = self._require_l2()
        resp = self._http.post("/trading/refresh-balance", l2_creds=creds)
        return _extract_data(resp)

    def buy(
        self,
        token_id: str,
        size: float,
        price: float,
        order_type: str = "GTC",
    ) -> OrderResult:
        """Buy shares on Polymarket.

        Full flow: prepare-order -> sign EIP-712 -> submit-order.
        Auto-calls ``setup_trading()`` if credentials are missing.
        """
        return self._place_order(token_id, "BUY", size, price, order_type)

    def sell(
        self,
        token_id: str,
        size: float,
        price: float,
        order_type: str = "GTC",
    ) -> OrderResult:
        """Sell shares on Polymarket.

        Full flow: prepare-order -> sign EIP-712 -> submit-order.
        Auto-calls ``setup_trading()`` if credentials are missing.
        """
        return self._place_order(token_id, "SELL", size, price, order_type)

    def _place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float,
        order_type: str,
    ) -> OrderResult:
        from ._exceptions import OrderError

        # Client-side validation — fail fast before wasting an API call
        if not (0.001 <= price <= 0.999):
            raise OrderError(
                message=f"Price must be between 0.001 and 0.999, got {price}.",
                error_code="INVALID_PRICE",
            )
        if size <= 0:
            raise OrderError(
                message=f"Order size must be positive, got {size}.",
                error_code="INVALID_SIZE",
            )

        # Auto setup_trading() if credentials are missing
        try:
            creds = self._require_l2()
        except SetupRequired:
            self.setup_trading()
            creds = self._require_l2()

        # 1. Prepare order (free, auth only)
        prep = self._http.post(
            "/trading/prepare-order",
            json={
                "token_id": token_id,
                "side": side,
                "size": size,
                "price": price,
                "order_type": order_type,
            },
        )
        data = _extract_data(prep)

        # 2. Sign EIP-712 typed data
        typed_data = data["typed_data"]
        sig = sign_typed_data(self._private_key, typed_data)

        # 3. Submit order (paid, needs L2 creds)
        submit = self._http.post(
            "/trading/submit-order",
            json={
                "signature": sig,
                "clob_order": data["clob_order"],
                "order_type": order_type,
            },
            paid=True,
            l2_creds=creds,
        )
        d = _extract_data(submit)

        return OrderResult(
            order_id=d.get("order_id", ""),
            status=d.get("status", "unknown"),
            success=d.get("success", False),
            taking_amount=d.get("taking_amount"),
            making_amount=d.get("making_amount"),
            tx_hash=d.get("tx_hash"),
            polygonscan_url=d.get("polygonscan_url"),
            error=d.get("error"),
            raw=d,
        )

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a single open order."""
        creds = self._require_l2()
        resp = self._http.delete(f"/trading/order/{order_id}", paid=True, l2_creds=creds)
        return _extract_data(resp)

    def cancel_all_orders(self) -> dict:
        """Cancel all open orders."""
        creds = self._require_l2()
        resp = self._http.delete("/trading/orders", paid=True, l2_creds=creds)
        return _extract_data(resp)

    def get_open_orders(self, market: str | None = None) -> list[dict]:
        """Get your open orders on Polymarket."""
        creds = self._require_l2()
        params = {"market": market} if market else None
        resp = self._http.get("/trading/orders", params=params, paid=True, l2_creds=creds)
        data = _extract_data(resp)
        return data if isinstance(data, list) else data.get("orders", []) if isinstance(data, dict) else []

    def batch_order(self, orders: list[dict]) -> BatchOrderResult:
        """Place multiple orders at once.

        Each order dict: {token_id, side, size, price, order_type?}.
        Full flow: prepare-batch-order -> sign all -> submit-batch-order.
        Auto-calls ``setup_trading()`` if credentials are missing.
        """
        try:
            creds = self._require_l2()
        except SetupRequired:
            self.setup_trading()
            creds = self._require_l2()

        # 1. Prepare batch
        prep = self._http.post(
            "/trading/prepare-batch-order",
            json={"orders": orders},
        )
        data = _extract_data(prep)

        # 2. Sign each prepared order
        prepared_orders = data.get("orders", [])
        signed_items = []
        for item in prepared_orders:
            typed_data = item["typed_data"]
            sig = sign_typed_data(self._private_key, typed_data)
            signed_items.append({
                "signature": sig,
                "clob_order": item["clob_order"],
                "order_type": orders[item["index"]].get("order_type", "GTC") if item.get("index") is not None else "GTC",
            })

        if not signed_items:
            return BatchOrderResult(
                results=[],
                success_count=0,
                fail_count=len(orders),
                raw=data,
            )

        # 3. Submit batch
        submit = self._http.post(
            "/trading/submit-batch-order",
            json={"orders": signed_items},
            paid=True,
            l2_creds=creds,
        )
        d = _extract_data(submit)

        results = d.get("results", [])
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count

        return BatchOrderResult(
            results=results,
            total_charged_usdt=d.get("total_charged_usdt", 0.0),
            success_count=success_count,
            fail_count=fail_count,
            raw=d,
        )

    # ------------------------------------------------------------------
    # Triggers (Stop Loss / Take Profit)
    # ------------------------------------------------------------------

    def _create_trigger(
        self,
        token_id: str,
        trigger_type: str,
        trigger_price: float,
        exit_side: str,
        size: float,
        exit_price: float,
        expires_in_hours: float | None = None,
    ) -> TriggerResult:
        """Internal: prepare + sign + create a trigger.
        Auto-calls ``setup_trading()`` if credentials are missing.
        """
        try:
            creds = self._require_l2()
        except SetupRequired:
            self.setup_trading()
            creds = self._require_l2()

        # 1. Prepare trigger order
        prep = self._http.post(
            "/trading/triggers/prepare",
            json={
                "token_id": token_id,
                "trigger_type": trigger_type,
                "trigger_price": trigger_price,
                "exit_side": exit_side,
                "size": size,
                "exit_price": exit_price,
                "expires_in_hours": expires_in_hours,
            },
        )
        data = _extract_data(prep)

        # 2. Sign EIP-712 typed data
        typed_data = data["typed_data"]
        sig = sign_typed_data(self._private_key, typed_data)

        # 3. Create trigger
        create = self._http.post(
            "/trading/triggers/create",
            json={
                "signature": sig,
                "clob_order": data["clob_order"],
                "order_type": data.get("order_type", "GTC"),
                "token_id": token_id,
                "trigger_type": trigger_type,
                "trigger_price": trigger_price,
                "exit_side": exit_side,
                "size": size,
                "exit_price": exit_price,
                "market_question": data.get("market", {}).get("question"),
                "market_outcome": data.get("market", {}).get("outcome"),
                "expires_in_hours": expires_in_hours,
            },
            paid=True,
            l2_creds=creds,
        )
        d = _extract_data(create)
        return TriggerResult(
            trigger_id=d.get("trigger_id", ""),
            status=d.get("status", "active"),
            token_id=token_id,
            trigger_type=trigger_type,
            trigger_price=str(trigger_price),
            exit_side=exit_side,
            raw=d,
        )

    def set_stop_loss(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
        exit_price: float,
        exit_side: str = "SELL",
        expires_in_hours: float | None = None,
    ) -> TriggerResult:
        """Set a stop loss trigger. When price hits trigger_price, sells at exit_price."""
        return self._create_trigger(
            token_id, "stop_loss", trigger_price, exit_side, size, exit_price, expires_in_hours,
        )

    def set_take_profit(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
        exit_price: float,
        exit_side: str = "SELL",
        expires_in_hours: float | None = None,
    ) -> TriggerResult:
        """Set a take profit trigger. When price hits trigger_price, sells at exit_price."""
        return self._create_trigger(
            token_id, "take_profit", trigger_price, exit_side, size, exit_price, expires_in_hours,
        )

    def get_triggers(self, status: str | None = None, token_id: str | None = None) -> list[Trigger]:
        """Get your triggers (optionally filtered by status and/or token_id)."""
        params: dict = {}
        if status:
            params["status"] = status
        if token_id:
            params["token_id"] = token_id
        params = params or None
        resp = self._http.get("/trading/triggers", params=params)
        data = _extract_data(resp)
        items = data if isinstance(data, list) else data.get("triggers", [])
        return [
            Trigger(
                trigger_id=t.get("id", ""),
                token_id=t.get("token_id", ""),
                trigger_type=t.get("trigger_type", ""),
                trigger_price=t.get("trigger_price", ""),
                exit_side=t.get("exit_side", ""),
                status=t.get("status", ""),
                size=t.get("size"),
                price=t.get("price"),
                market_question=t.get("market_question"),
                market_outcome=t.get("market_outcome"),
                created_at=t.get("created_at"),
                triggered_at=t.get("triggered_at"),
                expires_at=t.get("expires_at"),
                result_order_id=t.get("result_order_id"),
                result_status=t.get("result_status"),
                result_error=t.get("result_error"),
                raw=t,
            )
            for t in items
        ]

    def cancel_trigger(self, trigger_id: str) -> dict:
        """Cancel a single trigger."""
        resp = self._http.delete(f"/trading/triggers/{trigger_id}")
        return _extract_data(resp)

    def cancel_all_triggers(self, token_id: str | None = None) -> dict:
        """Cancel all triggers (optionally filtered by token_id)."""
        params = {"token_id": token_id} if token_id else None
        resp = self._http.delete("/trading/triggers", params=params)
        return _extract_data(resp)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_market(d: dict) -> Market:
    """Parse a server event/market dict into a Market dataclass.

    Server formats:
    - Slim (search/browse): {candidates: [{name, chance, price, token_id, condition_id}, ...]}
    - Full (events/markets): {markets: [{question, condition_id, outcomes, ...}, ...]}
    """
    condition_id = d.get("condition_id")

    # Try "candidates" first (slim server response)
    candidates = d.get("candidates")
    if candidates and isinstance(candidates, list):
        outcomes = [
            {
                "outcome": c.get("name", ""),
                "price": c.get("price") if c.get("price") is not None else _chance_to_float(c.get("chance")),
                "token_id": c.get("token_id"),
                "condition_id": c.get("condition_id"),
            }
            for c in candidates
        ]
    else:
        # Fallback: full Gamma-style response with nested markets
        raw_markets = d.get("markets", d.get("outcomes", []))
        if raw_markets and isinstance(raw_markets, list) and isinstance(raw_markets[0], dict) and "outcomes" in raw_markets[0]:
            outcomes: list[dict] = []
            for m in raw_markets:
                q = m.get("question", "")
                m_cid = m.get("condition_id")
                for o in m.get("outcomes", []):
                    entry = dict(o) if isinstance(o, dict) else {"outcome": str(o)}
                    if "price" not in entry and "chance" in entry:
                        entry["price"] = _chance_to_float(entry.pop("chance"))
                    if "name" in entry and "outcome" not in entry:
                        entry["outcome"] = entry.pop("name")
                    if q:
                        entry["market_question"] = q
                    if m_cid:
                        entry["condition_id"] = m_cid
                    outcomes.append(entry)
        else:
            outcomes = raw_markets

    # Parse volume: handle both numeric and formatted string ("$738,665,116")
    volume = _parse_volume(d.get("volume"))

    return Market(
        event_id=d.get("event_id", d.get("id", "")),
        title=d.get("title", d.get("question", "")),
        outcomes=outcomes,
        slug=d.get("slug", d.get("market_slug")),
        volume=volume,
        end_date=d.get("end_date"),
        tags=d.get("tags"),
        image=d.get("image"),
        condition_id=condition_id,
        raw=d,
    )


def _chance_to_float(chance) -> float | None:
    """Convert '65.2%' or 0.652 to float 0.652."""
    if chance is None:
        return None
    if isinstance(chance, (int, float)):
        return float(chance)
    s = str(chance).strip().rstrip("%")
    try:
        return float(s) / 100.0
    except (ValueError, TypeError):
        return None


def _parse_volume(v) -> float | None:
    """Parse volume: handles numeric, '$738,665,116', or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
