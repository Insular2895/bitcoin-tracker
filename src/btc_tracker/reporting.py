from __future__ import annotations

import csv
from shutil import copyfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import Database


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    return "[masked]"


@dataclass(frozen=True)
class ReportSummary:
    period_start_ms: int
    period_start_label: str
    buys_count: int
    convert_buys_count: int
    fiat_deposits_count: int
    fiat_deposit_net: float
    fiat_deposit_fees: float
    fiat_deposit_gross: float
    fiat_refunded_net: float
    btc_withdrawal_amount: float
    btc_withdrawal_fees: float
    btc_entered_wallet: float
    btc_withdrawal_fees_quote: float
    total_fees_quote: float
    invested_quote: float
    btc_bought: float
    average_cost: float
    wallet_btc: float
    exchange_btc: float
    total_btc: float
    spot_price: float
    current_value: float
    current_pnl_vs_deposits: float
    current_pnl_vs_conversions: float


def current_month_start_ms(tz_name: str = "Europe/Paris") -> int:
    now = datetime.now(ZoneInfo(tz_name))
    start = datetime(now.year, now.month, 1, tzinfo=ZoneInfo(tz_name))
    return int(start.timestamp() * 1000)


def parse_date_start_ms(value: str, tz_name: str = "Europe/Paris") -> int:
    date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=ZoneInfo(tz_name))
    return int(date.timestamp() * 1000)


def build_summary(db: Database, spot_price: float, fiat: str = "EUR", start_ms: int | None = None) -> ReportSummary:
    period_start_ms = start_ms if start_ms is not None else current_month_start_ms()
    buys = db.buy_trades(period_start_ms)
    convert_buys = db.btc_convert_buys(fiat, period_start_ms)
    fiat_deposits = db.fiat_deposits(fiat, period_start_ms)
    successful_deposits = [row for row in fiat_deposits if str(row["status"]).lower() == "successful"]
    refunded_deposits = [row for row in fiat_deposits if str(row["status"]).lower() == "refunded"]
    btc_withdrawals = db.btc_withdrawals(period_start_ms)

    fiat_deposit_net = sum(float(row["amount"]) for row in successful_deposits)
    fiat_deposit_fees = sum(float(row["fee"]) for row in successful_deposits)
    fiat_deposit_gross = fiat_deposit_net + fiat_deposit_fees
    fiat_refunded_net = sum(float(row["amount"]) for row in refunded_deposits)
    btc_withdrawal_amount = sum(float(row["amount"]) for row in btc_withdrawals)
    btc_withdrawal_fees = sum(float(row["fee"]) for row in btc_withdrawals)
    invested = sum(float(row["quote_qty"]) for row in buys) + sum(float(row["from_amount"]) for row in convert_buys)
    btc_bought = sum(float(row["qty_btc"]) for row in buys) + sum(float(row["to_amount"]) for row in convert_buys)
    wallet_btc = db.total_wallet_sats() / 100_000_000
    exchange_btc = db.exchange_asset_total("BTC")
    total_btc = wallet_btc + exchange_btc
    average_cost = invested / btc_bought if btc_bought else 0.0
    btc_entered_wallet = wallet_btc
    btc_withdrawal_fees_quote = btc_withdrawal_fees * average_cost
    total_fees_quote = fiat_deposit_fees + btc_withdrawal_fees_quote
    current_value = total_btc * spot_price
    current_pnl_vs_deposits = current_value - fiat_deposit_gross
    current_pnl_vs_conversions = current_value - invested
    return ReportSummary(
        period_start_ms=period_start_ms,
        period_start_label=datetime.fromtimestamp(period_start_ms / 1000, ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d"),
        buys_count=len(buys),
        convert_buys_count=len(convert_buys),
        fiat_deposits_count=len(successful_deposits),
        fiat_deposit_net=fiat_deposit_net,
        fiat_deposit_fees=fiat_deposit_fees,
        fiat_deposit_gross=fiat_deposit_gross,
        fiat_refunded_net=fiat_refunded_net,
        btc_withdrawal_amount=btc_withdrawal_amount,
        btc_withdrawal_fees=btc_withdrawal_fees,
        btc_entered_wallet=btc_entered_wallet,
        btc_withdrawal_fees_quote=btc_withdrawal_fees_quote,
        total_fees_quote=total_fees_quote,
        invested_quote=invested,
        btc_bought=btc_bought,
        average_cost=average_cost,
        wallet_btc=wallet_btc,
        exchange_btc=exchange_btc,
        total_btc=total_btc,
        spot_price=spot_price,
        current_value=current_value,
        current_pnl_vs_deposits=current_pnl_vs_deposits,
        current_pnl_vs_conversions=current_pnl_vs_conversions,
    )


def export_buys_csv(db: Database, export_dir: Path, fiat: str, spot_price: float, start_ms: int | None = None) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"btc_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    period_start_ms = start_ms if start_ms is not None else current_month_start_ms()
    rows = db.buy_trades(period_start_ms)
    converts = db.btc_convert_buys(fiat, period_start_ms)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "date_utc",
                "exchange",
                "symbol",
                f"invested_{fiat.upper()}",
                "btc_net",
                f"price_{fiat.upper()}",
                "fee_amount",
                "fee_asset",
                "order_id",
                "trade_id",
            ],
        )
        for row in rows:
            date = datetime.fromtimestamp(int(row["time_ms"]) / 1000, UTC).isoformat()
            writer.writerow(
                [
                    date,
                    row["exchange"],
                    row["symbol"],
                    f"{float(row['quote_qty']):.8f}",
                    f"{float(row['qty_btc']):.12f}",
                    f"{float(row['price_quote']):.8f}",
                    f"{float(row['fee_amount']):.12f}",
                    row["fee_asset"],
                    row["order_id"],
                    row["trade_id"],
                ],
            )

        for row in converts:
            date = datetime.fromtimestamp(int(row["time_ms"]) / 1000, UTC).isoformat()
            writer.writerow(
                [
                    date,
                    row["source"],
                    f"{row['from_asset']}{row['to_asset']}",
                    f"{float(row['from_amount']):.8f}",
                    f"{float(row['to_amount']):.12f}",
                    f"{float(row['ratio']):.8f}",
                    "0.000000000000",
                    "",
                    "",
                    row["external_id"],
                ],
            )

        summary = build_summary(db, spot_price, fiat, period_start_ms)
        writer.writerow([])
        writer.writerow(["summary"])
        writer.writerow(["period_start_utc", summary.period_start_label])
        writer.writerow(["buys_count", summary.buys_count])
        writer.writerow(["convert_buys_count", summary.convert_buys_count])
        writer.writerow(["fiat_deposits_count", summary.fiat_deposits_count])
        writer.writerow([f"fiat_deposit_gross_{fiat.upper()}", f"{summary.fiat_deposit_gross:.8f}"])
        writer.writerow([f"fiat_deposit_fees_{fiat.upper()}", f"{summary.fiat_deposit_fees:.8f}"])
        writer.writerow([f"fiat_deposit_net_{fiat.upper()}", f"{summary.fiat_deposit_net:.8f}"])
        writer.writerow([f"fiat_refunded_net_{fiat.upper()}", f"{summary.fiat_refunded_net:.8f}"])
        writer.writerow([f"invested_{fiat.upper()}", f"{summary.invested_quote:.8f}"])
        writer.writerow(["btc_bought", f"{summary.btc_bought:.12f}"])
        writer.writerow(["btc_withdrawal_amount", f"{summary.btc_withdrawal_amount:.12f}"])
        writer.writerow(["btc_withdrawal_fees", f"{summary.btc_withdrawal_fees:.12f}"])
        writer.writerow([f"btc_withdrawal_fees_{fiat.upper()}_at_cost", f"{summary.btc_withdrawal_fees_quote:.8f}"])
        writer.writerow([f"total_fees_{fiat.upper()}_at_cost", f"{summary.total_fees_quote:.8f}"])
        writer.writerow(["btc_entered_wallet", f"{summary.btc_entered_wallet:.12f}"])
        writer.writerow(["wallet_btc", f"{summary.wallet_btc:.12f}"])
        writer.writerow(["exchange_btc", f"{summary.exchange_btc:.12f}"])
        writer.writerow(["total_btc", f"{summary.total_btc:.12f}"])
        writer.writerow([f"average_cost_{fiat.upper()}", f"{summary.average_cost:.8f}"])
        writer.writerow([f"spot_price_{fiat.upper()}", f"{summary.spot_price:.8f}"])
        writer.writerow([f"current_value_{fiat.upper()}", f"{summary.current_value:.8f}"])
        writer.writerow([f"current_pnl_vs_deposits_{fiat.upper()}", f"{summary.current_pnl_vs_deposits:.8f}"])
        writer.writerow([f"current_pnl_vs_conversions_{fiat.upper()}", f"{summary.current_pnl_vs_conversions:.8f}"])

    copyfile(path, export_dir / "btc_report_latest.csv")
    return path


def export_ledger_csv(db: Database, export_dir: Path, start_ms: int | None = None) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"btc_ledger_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    period_start_ms = start_ms if start_ms is not None else current_month_start_ms()
    rows = db.ledger_rows(period_start_ms)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "date_utc",
                "event_type",
                "asset",
                "amount",
                "fee",
                "counter_asset",
                "counter_amount",
                "address",
                "txid",
                "status",
                "source",
                "external_id",
            ],
        )
        for row in rows:
            date = ""
            if int(row["time_ms"]):
                date = datetime.fromtimestamp(int(row["time_ms"]) / 1000, UTC).isoformat()
            writer.writerow(
                [
                    date,
                    row["event_type"],
                    row["asset"],
                    f"{float(row['amount']):.12f}",
                    f"{float(row['fee']):.12f}",
                    row["counter_asset"],
                    f"{float(row['counter_amount']):.12f}",
                    mask_identifier(str(row["address"])),
                    mask_identifier(str(row["txid"])),
                    row["status"],
                    row["source"],
                    row["external_id"],
                ],
            )

    copyfile(path, export_dir / "btc_ledger_latest.csv")
    return path
