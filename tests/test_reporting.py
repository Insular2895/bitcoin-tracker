from __future__ import annotations

from btc_tracker.db import Database
from btc_tracker.reporting import build_summary


def test_build_summary_uses_wallet_balance_for_current_value(tmp_path):
    db = Database(tmp_path / "test.sqlite")
    db.init()
    db.upsert_trade(
        {
            "source": "api",
            "exchange": "binance",
            "symbol": "BTCEUR",
            "order_id": "1",
            "trade_id": "10",
            "time_ms": 1,
            "side": "BUY",
            "price_quote": 50_000.0,
            "qty_btc": 0.01,
            "quote_qty": 500.0,
            "fee_amount": 0.0,
            "fee_asset": "EUR",
            "raw_json": "{}",
        },
    )
    db.upsert_utxo(
        {
            "address": "bc1test",
            "txid": "tx",
            "vout": 0,
            "value_sats": 1_000_000,
            "block_time": 1,
            "confirmed": 1,
        },
    )

    summary = build_summary(db, 60_000.0, start_ms=0)

    assert summary.invested_quote == 500.0
    assert summary.btc_bought == 0.01
    assert summary.wallet_btc == 0.01
    assert summary.current_value == 600.0
    assert summary.current_pnl_vs_conversions == 100.0
