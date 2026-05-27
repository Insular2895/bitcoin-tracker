from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    order_id TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    side TEXT NOT NULL,
    price_quote REAL NOT NULL,
    qty_btc REAL NOT NULL,
    quote_qty REAL NOT NULL,
    fee_amount REAL NOT NULL,
    fee_asset TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, exchange, symbol, trade_id)
);

CREATE TABLE IF NOT EXISTS wallet_addresses (
    address TEXT PRIMARY KEY,
    label TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallet_utxos (
    address TEXT NOT NULL,
    txid TEXT NOT NULL,
    vout INTEGER NOT NULL,
    value_sats INTEGER NOT NULL,
    block_time INTEGER,
    confirmed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(address, txid, vout)
);

CREATE TABLE IF NOT EXISTS exchange_balances (
    exchange TEXT NOT NULL,
    asset TEXT NOT NULL,
    free REAL NOT NULL,
    locked REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(exchange, asset)
);

CREATE TABLE IF NOT EXISTS fiat_orders (
    source TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    amount REAL NOT NULL,
    fee REAL NOT NULL,
    status TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, transaction_type, external_id)
);

CREATE TABLE IF NOT EXISTS crypto_deposits (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    coin TEXT NOT NULL,
    network TEXT NOT NULL,
    amount REAL NOT NULL,
    address TEXT NOT NULL,
    txid TEXT NOT NULL,
    status TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, external_id)
);

CREATE TABLE IF NOT EXISTS crypto_withdrawals (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    coin TEXT NOT NULL,
    network TEXT NOT NULL,
    amount REAL NOT NULL,
    fee REAL NOT NULL,
    address TEXT NOT NULL,
    txid TEXT NOT NULL,
    status TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, external_id)
);

CREATE TABLE IF NOT EXISTS convert_trades (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    from_asset TEXT NOT NULL,
    from_amount REAL NOT NULL,
    to_asset TEXT NOT NULL,
    to_amount REAL NOT NULL,
    ratio REAL NOT NULL,
    inverse_ratio REAL NOT NULL,
    status TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, external_id)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_trade(self, trade: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO trades (
                    source, exchange, symbol, order_id, trade_id, time_ms, side,
                    price_quote, qty_btc, quote_qty, fee_amount, fee_asset, raw_json
                )
                VALUES (
                    :source, :exchange, :symbol, :order_id, :trade_id, :time_ms, :side,
                    :price_quote, :qty_btc, :quote_qty, :fee_amount, :fee_asset, :raw_json
                )
                """,
                trade,
            )
            return cursor.rowcount > 0

    def add_wallet(self, address: str, label: str | None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO wallet_addresses(address, label)
                VALUES (?, ?)
                ON CONFLICT(address) DO UPDATE SET label = excluded.label
                """,
                (address, label),
            )

    def list_wallets(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute("SELECT address, label FROM wallet_addresses ORDER BY created_at"))

    def upsert_utxo(self, utxo: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR REPLACE INTO wallet_utxos (
                    address, txid, vout, value_sats, block_time, confirmed
                )
                VALUES (
                    :address, :txid, :vout, :value_sats, :block_time, :confirmed
                )
                """,
                utxo,
            )
            return cursor.rowcount > 0

    def upsert_exchange_balance(self, exchange: str, asset: str, free: float, locked: float) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO exchange_balances(exchange, asset, free, locked, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(exchange, asset)
                DO UPDATE SET
                    free = excluded.free,
                    locked = excluded.locked,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (exchange, asset.upper(), free, locked),
            )

    def upsert_fiat_order(self, order: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO fiat_orders (
                    source, transaction_type, external_id, asset, amount, fee, status, time_ms, raw_json
                )
                VALUES (
                    :source, :transaction_type, :external_id, :asset, :amount, :fee, :status, :time_ms, :raw_json
                )
                """,
                order,
            )
            return cursor.rowcount > 0

    def upsert_crypto_deposit(self, deposit: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO crypto_deposits (
                    source, external_id, coin, network, amount, address, txid, status, time_ms, raw_json
                )
                VALUES (
                    :source, :external_id, :coin, :network, :amount, :address, :txid, :status, :time_ms, :raw_json
                )
                """,
                deposit,
            )
            return cursor.rowcount > 0

    def upsert_crypto_withdrawal(self, withdrawal: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO crypto_withdrawals (
                    source, external_id, coin, network, amount, fee, address, txid, status, time_ms, raw_json
                )
                VALUES (
                    :source, :external_id, :coin, :network, :amount, :fee, :address, :txid, :status, :time_ms, :raw_json
                )
                """,
                withdrawal,
            )
            return cursor.rowcount > 0

    def upsert_convert_trade(self, convert: dict[str, Any]) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO convert_trades (
                    source, external_id, from_asset, from_amount, to_asset, to_amount,
                    ratio, inverse_ratio, status, time_ms, raw_json
                )
                VALUES (
                    :source, :external_id, :from_asset, :from_amount, :to_asset, :to_amount,
                    :ratio, :inverse_ratio, :status, :time_ms, :raw_json
                )
                """,
                convert,
            )
            return cursor.rowcount > 0

    def buy_trades(self, start_ms: int | None = None) -> list[sqlite3.Row]:
        params: list[int] = []
        start_filter = ""
        if start_ms is not None:
            start_filter = "AND time_ms >= ?"
            params.append(start_ms)
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT *
                    FROM trades
                    WHERE side = 'BUY'
                      {start_filter}
                    ORDER BY time_ms ASC, id ASC
                    """,
                    params,
                ),
            )

    def btc_convert_buys(self, quote_asset: str, start_ms: int | None = None) -> list[sqlite3.Row]:
        params: list[object] = [quote_asset.upper()]
        start_filter = ""
        if start_ms is not None:
            start_filter = "AND time_ms >= ?"
            params.append(start_ms)
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT *
                    FROM convert_trades
                    WHERE to_asset = 'BTC'
                      AND from_asset = ?
                      AND upper(status) = 'SUCCESS'
                      {start_filter}
                    ORDER BY time_ms ASC
                    """,
                    params,
                ),
            )

    def fiat_deposits(self, asset: str, start_ms: int | None = None) -> list[sqlite3.Row]:
        params: list[object] = [asset.upper()]
        start_filter = ""
        if start_ms is not None:
            start_filter = "AND time_ms >= ?"
            params.append(start_ms)
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT *
                    FROM fiat_orders
                    WHERE transaction_type = 'deposit'
                      AND asset = ?
                      {start_filter}
                    ORDER BY time_ms ASC
                    """,
                    params,
                ),
            )

    def btc_withdrawals(self, start_ms: int | None = None) -> list[sqlite3.Row]:
        params: list[int] = []
        start_filter = ""
        if start_ms is not None:
            start_filter = "AND time_ms >= ?"
            params.append(start_ms)
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT *
                    FROM crypto_withdrawals
                    WHERE coin = 'BTC'
                      {start_filter}
                    ORDER BY time_ms ASC
                    """,
                    params,
                ),
            )

    def total_wallet_sats(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COALESCE(SUM(value_sats), 0) AS total FROM wallet_utxos").fetchone()
            return int(row["total"])

    def exchange_asset_total(self, asset: str) -> float:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(free + locked), 0) AS total
                FROM exchange_balances
                WHERE asset = ?
                """,
                (asset.upper(),),
            ).fetchone()
            return float(row["total"])

    def table_count(self, table_name: str) -> int:
        allowed = {
            "trades",
            "fiat_orders",
            "crypto_deposits",
            "crypto_withdrawals",
            "convert_trades",
            "wallet_utxos",
        }
        if table_name not in allowed:
            raise ValueError(f"Unsupported table: {table_name}")
        with self.connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
            return int(row["count"])

    def ledger_rows(self, start_ms: int | None = None) -> list[sqlite3.Row]:
        params: list[int] = []
        start_filter = ""
        if start_ms is not None:
            start_filter = "WHERE time_ms >= ?"
            params.append(start_ms)
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT *
                    FROM (
                    SELECT time_ms, 'fiat_' || transaction_type AS event_type, asset, amount, fee,
                           '' AS counter_asset, 0.0 AS counter_amount, '' AS address, '' AS txid, status,
                           source, external_id
                    FROM fiat_orders
                    UNION ALL
                    SELECT time_ms, 'spot_trade_' || lower(side) AS event_type, 'BTC' AS asset, qty_btc AS amount,
                           fee_amount AS fee, replace(symbol, 'BTC', '') AS counter_asset, quote_qty AS counter_amount,
                           '' AS address, '' AS txid, side AS status, exchange AS source, trade_id AS external_id
                    FROM trades
                    UNION ALL
                    SELECT time_ms, 'convert' AS event_type, to_asset AS asset, to_amount AS amount,
                           0.0 AS fee, from_asset AS counter_asset, from_amount AS counter_amount,
                           '' AS address, '' AS txid, status, source, external_id
                    FROM convert_trades
                    UNION ALL
                    SELECT time_ms, 'crypto_deposit' AS event_type, coin AS asset, amount, 0.0 AS fee,
                           '' AS counter_asset, 0.0 AS counter_amount, address, txid, status, source, external_id
                    FROM crypto_deposits
                    UNION ALL
                    SELECT time_ms, 'crypto_withdrawal' AS event_type, coin AS asset, amount, fee,
                           '' AS counter_asset, 0.0 AS counter_amount, address, txid, status, source, external_id
                    FROM crypto_withdrawals
                    )
                    {start_filter}
                    ORDER BY time_ms ASC
                    """,
                    params,
                ),
            )
