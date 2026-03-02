import aiosqlite
import time

from api.config import settings

DB_PATH = settings.db_path


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                wallet_address TEXT PRIMARY KEY,
                total_deposited INTEGER DEFAULT 0,
                total_consumed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                amount INTEGER NOT NULL,
                endpoint TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS used_tx_hashes (
                tx_hash TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS historical_events (
                event_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT,
                start_date TEXT,
                end_date TEXT,
                closed_time TEXT,
                volume REAL,
                resolution TEXT,
                tags TEXT,
                market_count INTEGER DEFAULT 0,
                synced_at REAL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_hist_category ON historical_events(category)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_hist_volume ON historical_events(volume)"
        )

        # === Category Leaderboard Tables ===

        # market_slug → category permanent cache (slugs don't change)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_category_map (
                market_slug TEXT PRIMARY KEY,
                category_path TEXT,
                tags TEXT,
                question TEXT,
                event_id TEXT,
                volume REAL,
                mapped_at REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcm_category ON market_category_map(category_path)"
        )

        # Per-category leaderboard aggregation (rebuilt each sync)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS category_leaderboard (
                address TEXT NOT NULL,
                category_path TEXT NOT NULL,
                display_name TEXT,
                total_positions INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                total_volume REAL DEFAULT 0,
                win_rate REAL,
                best_pnl_market TEXT,
                best_pnl_value REAL,
                synced_at REAL NOT NULL,
                PRIMARY KEY (address, category_path)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_cl_category_pnl ON category_leaderboard(category_path, total_pnl DESC)"
        )

        # Per-trader per-category position snapshots (for drill-down)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trader_category_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                category_path TEXT,
                market_slug TEXT,
                question TEXT,
                outcome TEXT,
                token_id TEXT,
                size TEXT,
                avg_price TEXT,
                current_price TEXT,
                pnl TEXT,
                pnl_percent TEXT,
                synced_at REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tcp_addr_cat ON trader_category_positions(address, category_path)"
        )

        # === L2 Credentials Cache ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS l2_credentials (
                wallet_address TEXT PRIMARY KEY,
                api_key TEXT NOT NULL,
                secret TEXT NOT NULL,
                passphrase TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # === Triggers Table (stop loss / take profit) ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS triggers (
                id TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                token_id TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_price TEXT NOT NULL,
                exit_side TEXT NOT NULL,
                clob_order TEXT NOT NULL,
                signature TEXT NOT NULL,
                order_type TEXT NOT NULL DEFAULT 'GTC',
                l2_api_key TEXT NOT NULL,
                l2_secret TEXT NOT NULL,
                l2_passphrase TEXT NOT NULL,
                size TEXT,
                price TEXT,
                market_question TEXT,
                market_outcome TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                triggered_at REAL,
                submitted_at REAL,
                result_order_id TEXT,
                result_status TEXT,
                result_error TEXT,
                expires_at REAL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_triggers_active ON triggers(status, token_id) WHERE status = 'active'"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_triggers_wallet ON triggers(wallet_address, status)"
        )

        await db.commit()


async def credit_deposit(wallet_address: str, amount: int):
    """Credit a deposit to a wallet's prepaid balance."""
    addr = wallet_address.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO balances (wallet_address, total_deposited, total_consumed)
            VALUES (?, ?, 0)
            ON CONFLICT(wallet_address)
            DO UPDATE SET total_deposited = total_deposited + ?
        """, (addr, amount, amount))
        await db.commit()


async def consume(wallet_address: str, amount: int, endpoint: str) -> bool:
    """Atomically consume from prepaid balance. Returns True if sufficient balance."""
    addr = wallet_address.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """UPDATE balances SET total_consumed = total_consumed + ?
               WHERE wallet_address = ? AND (total_deposited - total_consumed) >= ?""",
            (amount, addr, amount),
        )
        if cursor.rowcount == 0:
            return False

        await db.execute(
            "INSERT INTO usage_log (wallet_address, amount, endpoint, timestamp) VALUES (?, ?, ?, ?)",
            (addr, amount, endpoint, time.time()),
        )
        await db.commit()
        return True


async def is_tx_used(tx_hash: str) -> bool:
    """Check if a transaction hash has already been used for payment."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT 1 FROM used_tx_hashes WHERE tx_hash = ?",
            (tx_hash.lower(),),
        )
        return len(row) > 0


async def mark_tx_used(tx_hash: str, wallet_address: str):
    """Mark a transaction hash as used."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO used_tx_hashes (tx_hash, wallet_address, timestamp) VALUES (?, ?, ?)",
            (tx_hash.lower(), wallet_address.lower(), time.time()),
        )
        await db.commit()


async def get_remaining(wallet_address: str) -> tuple[int, int, int]:
    """Return (total_deposited, total_consumed, remaining) in wei."""
    addr = wallet_address.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT total_deposited, total_consumed FROM balances WHERE wallet_address = ?",
            (addr,),
        )
        if not row:
            return (0, 0, 0)
        deposited, consumed = row[0]
        return (deposited, consumed, deposited - consumed)


def calls_remaining(remaining_wei: int) -> int:
    """Calculate how many API calls the remaining balance can cover."""
    if remaining_wei <= 0:
        return 0
    return remaining_wei // settings.payment_amount_wei


# === L2 Credentials Cache ===


async def save_l2_credentials(
    wallet_address: str, api_key: str, secret: str, passphrase: str,
):
    """Save or update L2 credentials for a wallet."""
    addr = wallet_address.lower()
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO l2_credentials (wallet_address, api_key, secret, passphrase, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(wallet_address)
               DO UPDATE SET api_key = ?, secret = ?, passphrase = ?, updated_at = ?""",
            (addr, api_key, secret, passphrase, now, now,
             api_key, secret, passphrase, now),
        )
        await db.commit()


async def get_l2_credentials(wallet_address: str) -> dict | None:
    """Get cached L2 credentials for a wallet. Returns None if not cached."""
    addr = wallet_address.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT api_key, secret, passphrase FROM l2_credentials WHERE wallet_address = ?",
            (addr,),
        )
        if not rows:
            return None
        api_key, secret, passphrase = rows[0]
        return {"api_key": api_key, "secret": secret, "passphrase": passphrase}
