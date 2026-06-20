"""
設定檔 - 支援 Demo Mode
"""
import os
from typing import Optional


class Settings:
    """應用程式設定"""
    
    def __init__(self):
        self.demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
        self.binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
        self.binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
        self.coinglass_api_key: str = os.getenv("COINGLASS_API_KEY", "")
        self.testnet: bool = os.getenv("TESTNET", "true").lower() == "true"
        self.on_dev: bool = os.getenv("ON_DEV", "true").lower() == "true"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
