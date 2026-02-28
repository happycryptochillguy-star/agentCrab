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

    # Polymarket
    gamma_api_url: str = "https://gamma-api.polymarket.com"

    # Auth
    signature_max_age_seconds: int = 300  # 5 minutes

    # Background scanner
    scanner_interval_seconds: int = 15

    # SQLite
    db_path: str = "agentway.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
