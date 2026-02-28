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
