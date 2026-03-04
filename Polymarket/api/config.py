from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # BSC
    bsc_rpc_url: str = "https://bsc-dataseed.binance.org/"
    private_key: str = ""
    contract_address: str = ""

    # USDT on BSC (18 decimals)
    usdt_address: str = "0x55d398326f99059fF775485246999027B3197955"

    # Payment
    payment_amount_wei: int = 10**16  # 0.01 USDT

    # Polymarket (Gamma API)
    gamma_api_url: str = "https://gamma-api.polymarket.com"

    # CLOB API
    clob_api_url: str = "https://clob.polymarket.com"

    # Bridge API (deposits/withdrawals)
    bridge_api_url: str = ""

    # fun.xyz (Polymarket deposit relay)
    fun_xyz_api_url: str = ""
    fun_xyz_api_key: str = ""

    # Data API
    data_api_url: str = "https://data-api.polymarket.com"

    # Polygon (Polymarket settlement chain)
    polygon_rpc_url: str = ""
    polygon_chain_id: int = 137
    polygon_usdc_address: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e

    # Polymarket Builder (relayer for gasless Polygon ops)
    poly_builder_api_key: str = ""
    poly_builder_secret: str = ""
    poly_builder_passphrase: str = ""
    relayer_url: str = ""

    # Proxy for geo-blocked Polymarket APIs (empty = direct)
    polymarket_proxy: str = ""

    # Proxy for geo-blocked Telegram API (empty = direct)
    telegram_proxy: str = ""

    # Auth
    signature_max_age_seconds: int = 300  # 5 minutes

    # SQLite
    db_path: str = "agentcrab.db"

    # Telegram alerts
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Bark push notifications (iOS)
    bark_url: str = ""  # e.g. https://api.day.app/YOUR_KEY

    # Encryption key for L2 credentials at rest (Fernet, base64-encoded 32 bytes)
    # Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    l2_encryption_key: str = ""
    l2_encryption_key_old: str = ""  # Previous key for rotation (decrypt only)

    # Admin
    admin_key: str = ""

    # $CRAB token
    crab_token_address: str = ""  # BSC BEP-20 contract (set after deployment)
    crab_airdrop_address: str = ""  # BSC Merkle airdrop contract

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # SDK version control
    min_sdk_version: str = "0.1.0"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()


def reload_settings() -> dict[str, tuple]:
    """Re-read .env and update the global settings object atomically.

    Collects all changes first, then applies them in a single pass.
    Returns {field_name: (old_value, new_value)} for fields that changed.
    """
    new = Settings()
    changes: dict[str, tuple] = {}
    for field_name in Settings.model_fields:
        old_val = getattr(settings, field_name)
        new_val = getattr(new, field_name)
        if old_val != new_val:
            changes[field_name] = (old_val, new_val)
    # Apply all changes in a single pass (minimizes inconsistency window)
    for field_name, (_, new_val) in changes.items():
        object.__setattr__(settings, field_name, new_val)
    return changes
