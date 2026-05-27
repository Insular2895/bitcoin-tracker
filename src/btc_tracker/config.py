from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    binance_api_key: str
    binance_api_secret: str
    binance_symbols: list[str]
    btc_watch_addresses: list[str]
    db_path: Path
    export_dir: Path
    mempool_api_base: str


def load_settings() -> Settings:
    load_dotenv()

    symbols = os.getenv("BINANCE_SYMBOLS", "BTCEUR,BTCUSDT")
    watch_addresses = os.getenv("BTC_WATCH_ADDRESSES", "")
    return Settings(
        binance_api_key=os.getenv("BINANCE_API_KEY", ""),
        binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
        binance_symbols=[symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()],
        btc_watch_addresses=[address.strip() for address in watch_addresses.split(",") if address.strip()],
        db_path=Path(os.getenv("TRACKER_DB", "data/portfolio.sqlite")),
        export_dir=Path(os.getenv("EXPORT_DIR", "exports")),
        mempool_api_base=os.getenv("MEMPOOL_API_BASE", "https://mempool.space/api").rstrip("/"),
    )
