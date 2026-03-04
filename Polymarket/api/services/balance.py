import asyncio
import logging
import os
import stat
import time

import aiosqlite

from api.config import settings

logger = logging.getLogger("agentcrab.balance")

DB_PATH = settings.db_path

# Shared DB connection and write lock for serialized writes.
# WAL mode handles concurrent reads; lock prevents write contention.
_db: aiosqlite.Connection | None = None
_write_lock = asyncio.Lock()
_init_lock = asyncio.Lock()


def _secure_db_file(path: str):
    """Set database file permissions to owner-only (600).
    Prevents other users on the server from reading L2 credentials."""
    try:
        if os.path.exists(path):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        # Also secure WAL and SHM files if they exist
        for suffix in ("-wal", "-shm"):
            wal = path + suffix
            if os.path.exists(wal):
                os.chmod(wal, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best effort — may fail on some filesystems


async def get_db() -> aiosqlite.Connection:
    """Get or create the shared DB connection."""
    global _db
    if _db is not None:
        return _db
    async with _init_lock:
        if _db is None:
            # Use local var — don't assign global until PRAGMAs are done
            conn = await aiosqlite.connect(DB_PATH)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            _secure_db_file(DB_PATH)
            _db = conn
    return _db


async def close_db():
    """Close the shared DB connection. Call on app shutdown."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db():
    """Create tables if they don't exist."""
    db = await get_db()
    async with _write_lock:
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

        # === Points Snapshot (for $CRAB airdrop) ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS points_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                deposit_points INTEGER NOT NULL,
                usage_points INTEGER NOT NULL,
                bonus_points INTEGER NOT NULL DEFAULT 0,
                total_points INTEGER NOT NULL,
                snapshot_at REAL NOT NULL,
                snapshot_name TEXT NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_points_snapshot_name ON points_snapshot(snapshot_name)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_points_snapshot_wallet ON points_snapshot(wallet_address, snapshot_name)"
        )

        # === Used Signatures (replay prevention, persisted across restarts) ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS used_signatures (
                signature TEXT PRIMARY KEY,
                expires_at REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_used_sig_expires ON used_signatures(expires_at)"
        )

        # === Indexes added by audit ===
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_log_wallet ON usage_log(wallet_address)"
        )

        await db.commit()


async def credit_deposit(wallet_address: str, amount: int):
    """Credit a deposit to a wallet's prepaid balance."""
    addr = wallet_address.lower()
    db = await get_db()
    async with _write_lock:
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
    db = await get_db()
    async with _write_lock:
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


async def refund(wallet_address: str, amount: int, endpoint: str):
    """Refund a consumed amount back to the wallet (decrement total_consumed).

    Unlike credit_deposit(), this correctly reverses a consumption without
    inflating total_deposited.
    """
    addr = wallet_address.lower()
    db = await get_db()
    async with _write_lock:
        # Check if refund would clip at zero (indicates a logic bug somewhere)
        cursor = await db.execute(
            "SELECT total_consumed FROM balances WHERE wallet_address = ?",
            (addr,),
        )
        row = await cursor.fetchone()
        if row and row[0] < amount:
            logger.warning(
                "Refund clip: %s refund=%d > consumed=%d on %s — possible over-refund bug",
                addr[:10], amount, row[0], endpoint,
            )
        await db.execute(
            """UPDATE balances SET total_consumed = MAX(0, total_consumed - ?)
               WHERE wallet_address = ?""",
            (amount, addr),
        )
        await db.execute(
            "INSERT INTO usage_log (wallet_address, amount, endpoint, timestamp) VALUES (?, ?, ?, ?)",
            (addr, -amount, f"refund:{endpoint}", time.time()),
        )
        await db.commit()


async def is_tx_used(tx_hash: str) -> bool:
    """Check if a transaction hash has already been used for payment."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT 1 FROM used_tx_hashes WHERE tx_hash = ?",
        (tx_hash.lower(),),
    )
    return len(row) > 0


async def mark_tx_used(tx_hash: str, wallet_address: str):
    """Mark a transaction hash as used."""
    db = await get_db()
    async with _write_lock:
        await db.execute(
            "INSERT OR IGNORE INTO used_tx_hashes (tx_hash, wallet_address, timestamp) VALUES (?, ?, ?)",
            (tx_hash.lower(), wallet_address.lower(), time.time()),
        )
        await db.commit()


async def try_claim_tx_hash(tx_hash: str, wallet_address: str) -> bool:
    """Atomically claim a tx hash. Returns True if successfully claimed (first use).
    Returns False if already used (duplicate). This is TOCTOU-safe because it uses
    a single INSERT with UNIQUE constraint — no separate check-then-insert gap."""
    db = await get_db()
    async with _write_lock:
        try:
            await db.execute(
                "INSERT INTO used_tx_hashes (tx_hash, wallet_address, timestamp) VALUES (?, ?, ?)",
                (tx_hash.lower(), wallet_address.lower(), time.time()),
            )
            await db.commit()
            return True
        except Exception:
            # UNIQUE constraint violation → already used
            return False


async def get_remaining(wallet_address: str) -> tuple[int, int, int]:
    """Return (total_deposited, total_consumed, remaining) in wei."""
    addr = wallet_address.lower()
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT total_deposited, total_consumed FROM balances WHERE wallet_address = ?",
        (addr,),
    )
    if not row:
        return (0, 0, 0)
    deposited, consumed = row[0]
    return (deposited, consumed, deposited - consumed)


# === Signature Replay Prevention (persisted in SQLite) ===


async def try_claim_signature(signature: str, expires_at: float) -> bool:
    """Atomically claim a signature. Returns True if first use, False if replay.

    TOCTOU-safe: uses INSERT with UNIQUE constraint (single atomic operation).
    Persists across restarts. Works across multiple workers.
    """
    db = await get_db()
    async with _write_lock:
        try:
            await db.execute(
                "INSERT INTO used_signatures (signature, expires_at) VALUES (?, ?)",
                (signature.lower(), expires_at),
            )
            await db.commit()
            return True
        except Exception:
            # UNIQUE constraint violation → already used
            return False


async def cleanup_expired_signatures():
    """Remove expired signatures from the database."""
    db = await get_db()
    async with _write_lock:
        await db.execute(
            "DELETE FROM used_signatures WHERE expires_at < ?",
            (time.time(),),
        )
        await db.commit()


def calls_remaining(remaining_wei: int) -> int:
    """Calculate how many API calls the remaining balance can cover."""
    if remaining_wei <= 0:
        return 0
    return remaining_wei // settings.payment_amount_wei


# === L2 Credentials Cache (encrypted at rest) ===


_fernet_cache: dict[str, object] = {}  # key_str -> Fernet instance


def _get_fernet(key: str | None = None):
    """Get (cached) Fernet cipher. Returns None if no key configured."""
    if key is None:
        key = settings.l2_encryption_key
    if not key:
        return None
    if key not in _fernet_cache:
        try:
            from cryptography.fernet import Fernet
            _fernet_cache[key] = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            return None
    return _fernet_cache[key]


def _encrypt(value: str) -> str:
    """Encrypt a string if encryption key is available, otherwise return as-is."""
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    """Decrypt a string if encryption key is available, otherwise return as-is.

    Detects Fernet tokens (prefix 'gAAAAAB') to distinguish encrypted values
    from legacy plaintext. If value IS encrypted but cannot be decrypted,
    raises ValueError instead of returning garbage.
    """
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        # Try old encryption key if configured (supports key rotation)
        old_key = getattr(settings, "l2_encryption_key_old", None)
        if old_key:
            try:
                old_f = _get_fernet(old_key)
                if old_f:
                    return old_f.decrypt(value.encode()).decode()
            except Exception:
                pass
        # If value looks like a Fernet token, it IS encrypted — don't return garbage
        if value.startswith("gAAAAAB"):
            raise ValueError(
                "Cannot decrypt value: encryption key mismatch. "
                "Check L2_ENCRYPTION_KEY (and L2_ENCRYPTION_KEY_OLD for rotation)."
            )
        # Likely stored before encryption was enabled — return raw plaintext
        return value


async def save_l2_credentials(
    wallet_address: str, api_key: str, secret: str, passphrase: str,
):
    """Save or update L2 credentials for a wallet (encrypted at rest)."""
    addr = wallet_address.lower()
    now = time.time()
    enc_key = _encrypt(api_key)
    enc_secret = _encrypt(secret)
    enc_pass = _encrypt(passphrase)
    db = await get_db()
    async with _write_lock:
        await db.execute(
            """INSERT INTO l2_credentials (wallet_address, api_key, secret, passphrase, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(wallet_address)
               DO UPDATE SET api_key = ?, secret = ?, passphrase = ?, updated_at = ?""",
            (addr, enc_key, enc_secret, enc_pass, now, now,
             enc_key, enc_secret, enc_pass, now),
        )
        await db.commit()


async def get_l2_credentials(wallet_address: str) -> dict | None:
    """Get cached L2 credentials for a wallet (decrypted). Returns None if not cached."""
    addr = wallet_address.lower()
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT api_key, secret, passphrase FROM l2_credentials WHERE wallet_address = ?",
        (addr,),
    )
    if not rows:
        return None
    api_key, secret, passphrase = rows[0]
    return {
        "api_key": _decrypt(api_key),
        "secret": _decrypt(secret),
        "passphrase": _decrypt(passphrase),
    }
