from __future__ import annotations

import argparse
import sys

import requests
from rich.console import Console
from rich.prompt import Prompt

from .binance_client import (
    BinanceClient,
    iter_time_windows,
    normalize_convert_trade,
    normalize_crypto_deposit,
    normalize_crypto_withdrawal,
    normalize_fiat_order,
    normalize_trade,
)
from .config import load_settings
from .db import Database
from .mempool_client import MempoolClient, normalize_utxo
from .reporting import build_summary, current_month_start_ms, export_buys_csv, export_ledger_csv, parse_date_start_ms

console = Console()


def print_report(summary, fiat: str) -> None:
    lines = [
        f"Rapport BTC depuis {summary.period_start_label}",
        "",
        f"Dépôts EUR réussis    : {summary.fiat_deposits_count}",
        f"Montant brut déposé   : {summary.fiat_deposit_gross:,.2f} {fiat}",
        f"Frais fiat            : {summary.fiat_deposit_fees:,.2f} {fiat}",
        f"Frais total           : {summary.total_fees_quote:,.2f} {fiat}",
        f"Montant net crédité   : {summary.fiat_deposit_net:,.2f} {fiat}",
        f"Remboursé net         : {summary.fiat_refunded_net:,.2f} {fiat}",
        "",
        f"Conversions BTC       : {summary.convert_buys_count}",
        f"Converti en BTC       : {summary.invested_quote:,.2f} {fiat}",
        f"BTC acheté            : {summary.btc_bought:.8f} BTC",
        "",
        f"BTC envoyé            : {summary.btc_withdrawal_amount:.8f} BTC",
        f"Frais retrait BTC     : {summary.btc_withdrawal_fees:.8f} BTC",
        f"Montant BTC entrée    : {summary.btc_entered_wallet:.8f} BTC",
        f"BTC wallet multisig   : {summary.wallet_btc:.8f} BTC",
        "",
        f"Valeur actuelle       : {summary.current_value:,.2f} {fiat}",
        f"Current PNL vs dépôts : {summary.current_pnl_vs_deposits:,.2f} {fiat}",
    ]
    console.print("\n".join(lines))


def print_pnl(summary, fiat: str) -> None:
    console.print(
        "\n".join(
            [
                f"PNL depuis {summary.period_start_label}",
                "",
                f"Montant brut déposé   : {summary.fiat_deposit_gross:,.2f} {fiat}",
                f"Valeur actuelle       : {summary.current_value:,.2f} {fiat}",
                f"Current PNL vs dépôts : {summary.current_pnl_vs_deposits:,.2f} {fiat}",
            ],
        ),
    )


def print_fees(summary, fiat: str) -> None:
    console.print(
        "\n".join(
            [
                f"Frais depuis {summary.period_start_label}",
                "",
                f"Frais fiat            : {summary.fiat_deposit_fees:,.2f} {fiat}",
                f"Frais retrait BTC     : {summary.btc_withdrawal_fees:.8f} BTC",
                f"Frais retrait au coût : {summary.btc_withdrawal_fees_quote:,.2f} {fiat}",
                f"Frais total           : {summary.total_fees_quote:,.2f} {fiat}",
            ],
        ),
    )


def sync_binance_all(settings, db: Database, symbols: list[str], days: int) -> None:
    client = BinanceClient(settings.binance_api_key, settings.binance_api_secret)

    for symbol in symbols:
        trades = client.my_trades(symbol)
        for trade in trades:
            db.upsert_trade(normalize_trade(symbol, trade))

    account = client.account()
    for balance in account.get("balances", []):
        asset = str(balance["asset"]).upper()
        free = float(balance["free"])
        locked = float(balance["locked"])
        if free or locked or asset == "BTC":
            db.upsert_exchange_balance("binance", asset, free, locked)

    for transaction_type, label in [(0, "deposit"), (1, "withdraw")]:
        data = client.fiat_orders(transaction_type, *next(iter_time_windows(days, days)))
        for order in data.get("data", []):
            db.upsert_fiat_order(normalize_fiat_order(label, order))

    for start_ms, end_ms in iter_time_windows(days, 89):
        for deposit in client.crypto_deposits(start_ms, end_ms):
            db.upsert_crypto_deposit(normalize_crypto_deposit(deposit))
        for withdrawal in client.crypto_withdrawals(start_ms, end_ms):
            db.upsert_crypto_withdrawal(normalize_crypto_withdrawal(withdrawal))

    for start_ms, end_ms in iter_time_windows(days, 30):
        try:
            data = client.convert_trade_flow(start_ms, end_ms)
        except requests.HTTPError as exc:
            console.print(f"[yellow]Convert history unavailable:[/yellow] {exc.response.status_code} {exc.response.text}")
            break
        for convert in data.get("list", []):
            db.upsert_convert_trade(normalize_convert_trade(convert))


def sync_wallets(settings, db: Database) -> None:
    client = MempoolClient(settings.mempool_api_base)
    for address in settings.btc_watch_addresses:
        db.add_wallet(address, "env-watch")

    for wallet in db.list_wallets():
        for utxo in client.address_utxos(wallet["address"]):
            db.upsert_utxo(normalize_utxo(wallet["address"], utxo))


def generate_report(settings, db: Database, fiat: str, start_ms: int, spot_price: float | None) -> tuple[object, object, object]:
    effective_spot_price = spot_price or MempoolClient(settings.mempool_api_base).latest_btc_price(fiat)
    summary = build_summary(db, effective_spot_price, fiat, start_ms)
    csv_path = export_buys_csv(db, settings.export_dir, fiat, effective_spot_price, start_ms)
    ledger_path = export_ledger_csv(db, settings.export_dir, start_ms)
    return summary, csv_path, ledger_path


def command_init(args: argparse.Namespace) -> int:
    settings = load_settings()
    Database(settings.db_path).init()
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]Database initialized:[/green] {settings.db_path}")
    return 0


def command_wallet_add(args: argparse.Namespace) -> int:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init()
    client = MempoolClient(settings.mempool_api_base)
    if not client.validate_address(args.address):
        console.print(f"[red]Invalid BTC address:[/red] {args.address}")
        return 2
    db.add_wallet(args.address, args.label)
    console.print(f"[green]Wallet added:[/green] {args.address}")
    return 0


def command_sync_binance(args: argparse.Namespace) -> int:
    settings = load_settings()
    if not settings.binance_api_key or not settings.binance_api_secret:
        console.print("[red]Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env[/red]")
        return 2

    db = Database(settings.db_path)
    db.init()
    client = BinanceClient(settings.binance_api_key, settings.binance_api_secret)
    symbols = args.symbols or settings.binance_symbols
    inserted = 0

    for symbol in symbols:
        trades = client.my_trades(symbol)
        for trade in trades:
            if db.upsert_trade(normalize_trade(symbol, trade)):
                inserted += 1
        console.print(f"[cyan]{symbol}[/cyan]: {len(trades)} trades read")

    account = client.account()
    for balance in account.get("balances", []):
        asset = str(balance["asset"]).upper()
        free = float(balance["free"])
        locked = float(balance["locked"])
        if free or locked or asset == "BTC":
            db.upsert_exchange_balance("binance", asset, free, locked)

    console.print(f"[green]Inserted new trades:[/green] {inserted}")
    console.print("[green]Binance Spot balances updated.[/green]")
    return 0


def command_sync_binance_all(args: argparse.Namespace) -> int:
    settings = load_settings()
    if not settings.binance_api_key or not settings.binance_api_secret:
        console.print("[red]Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env[/red]")
        return 2

    db = Database(settings.db_path)
    db.init()
    symbols = args.symbols or settings.binance_symbols
    days = args.days
    client = BinanceClient(settings.binance_api_key, settings.binance_api_secret)

    spot_inserted = 0
    for symbol in symbols:
        trades = client.my_trades(symbol)
        for trade in trades:
            if db.upsert_trade(normalize_trade(symbol, trade)):
                spot_inserted += 1
        console.print(f"[cyan]{symbol}[/cyan]: {len(trades)} spot trades read")

    account = client.account()
    for balance in account.get("balances", []):
        asset = str(balance["asset"]).upper()
        free = float(balance["free"])
        locked = float(balance["locked"])
        if free or locked or asset == "BTC":
            db.upsert_exchange_balance("binance", asset, free, locked)

    fiat_inserted = 0
    for transaction_type, label in [(0, "deposit"), (1, "withdraw")]:
        data = client.fiat_orders(transaction_type, *next(iter_time_windows(days, days)))
        for order in data.get("data", []):
            if db.upsert_fiat_order(normalize_fiat_order(label, order)):
                fiat_inserted += 1
        console.print(f"[cyan]fiat {label}[/cyan]: {len(data.get('data', []))} rows read")

    crypto_deposit_inserted = 0
    crypto_withdrawal_inserted = 0
    for start_ms, end_ms in iter_time_windows(days, 89):
        deposits = client.crypto_deposits(start_ms, end_ms)
        withdrawals = client.crypto_withdrawals(start_ms, end_ms)
        for deposit in deposits:
            if db.upsert_crypto_deposit(normalize_crypto_deposit(deposit)):
                crypto_deposit_inserted += 1
        for withdrawal in withdrawals:
            if db.upsert_crypto_withdrawal(normalize_crypto_withdrawal(withdrawal)):
                crypto_withdrawal_inserted += 1

    convert_inserted = 0
    convert_read = 0
    for start_ms, end_ms in iter_time_windows(days, 30):
        try:
            data = client.convert_trade_flow(start_ms, end_ms)
        except requests.HTTPError as exc:
            console.print(f"[yellow]Convert history unavailable:[/yellow] {exc.response.status_code} {exc.response.text}")
            break
        converts = data.get("list", [])
        convert_read += len(converts)
        for convert in converts:
            if db.upsert_convert_trade(normalize_convert_trade(convert)):
                convert_inserted += 1

    console.print(f"[green]Inserted spot trades:[/green] {spot_inserted}")
    console.print(f"[green]Inserted fiat rows:[/green] {fiat_inserted}")
    console.print(f"[green]Inserted crypto deposits:[/green] {crypto_deposit_inserted}")
    console.print(f"[green]Inserted crypto withdrawals:[/green] {crypto_withdrawal_inserted}")
    console.print(f"[green]Convert rows read/inserted:[/green] {convert_read}/{convert_inserted}")
    return 0


def command_sync_wallets(args: argparse.Namespace) -> int:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init()
    client = MempoolClient(settings.mempool_api_base)
    wallets = db.list_wallets()
    if not wallets:
        console.print("[yellow]No wallet address configured yet.[/yellow]")
        return 0

    stored = 0
    for wallet in wallets:
        utxos = client.address_utxos(wallet["address"])
        for utxo in utxos:
            if db.upsert_utxo(normalize_utxo(wallet["address"], utxo)):
                stored += 1
        console.print(f"[cyan]{wallet['address']}[/cyan]: {len(utxos)} UTXOs")

    console.print(f"[green]Wallet UTXOs stored/updated:[/green] {stored}")
    return 0


def command_report(args: argparse.Namespace) -> int:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init()
    fiat = args.fiat.upper()

    start_ms = parse_date_start_ms(args.from_date) if args.from_date else current_month_start_ms()
    summary, csv_path, ledger_path = generate_report(settings, db, fiat, start_ms, args.spot_price)

    print_report(summary, fiat)
    console.print(f"[green]CSV exported:[/green] {csv_path}")
    console.print(f"[green]Ledger exported:[/green] {ledger_path}")
    console.print("[green]Latest CSVs:[/green] exports/btc_report_latest.csv, exports/btc_ledger_latest.csv")
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    settings = load_settings()
    if not settings.binance_api_key or not settings.binance_api_secret:
        console.print("[red]Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env[/red]")
        return 2

    db = Database(settings.db_path)
    db.init()
    fiat = args.fiat.upper()
    symbols = args.symbols or settings.binance_symbols
    start_ms = parse_date_start_ms(args.from_date) if args.from_date else current_month_start_ms()

    sync_binance_all(settings, db, symbols, args.days)
    sync_wallets(settings, db)
    summary, csv_path, ledger_path = generate_report(settings, db, fiat, start_ms, args.spot_price)

    print_report(summary, fiat)
    console.print(f"[green]CSV exported:[/green] {csv_path}")
    console.print(f"[green]Ledger exported:[/green] {ledger_path}")
    console.print("[green]Latest CSVs:[/green] exports/btc_report_latest.csv, exports/btc_ledger_latest.csv")
    return 0


def command_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init()
    fiat = args.fiat.upper()
    start_ms = parse_date_start_ms(args.from_date) if args.from_date else current_month_start_ms()
    symbols = args.symbols or settings.binance_symbols

    console.print(
        "\n".join(
            [
                "BTC Portfolio Tracker",
                "",
                "1. Tout lancer : sync Binance + wallet + rapport + CSV",
                "2. Montrer le PNL",
                "3. Montrer les frais",
                "4. Préparer / mettre à jour les CSV",
                "5. Quitter",
                "",
            ],
        ),
    )
    choice = Prompt.ask("Choisis un chiffre", choices=["1", "2", "3", "4", "5"], default="1")
    if choice == "5":
        console.print("Ok, rien lancé.")
        return 0

    should_sync = choice in {"1", "4"}
    if should_sync:
        if not settings.binance_api_key or not settings.binance_api_secret:
            console.print("[red]Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env[/red]")
            return 2
        sync_binance_all(settings, db, symbols, args.days)
        sync_wallets(settings, db)

    summary, csv_path, ledger_path = generate_report(settings, db, fiat, start_ms, args.spot_price)

    if choice == "1":
        print_report(summary, fiat)
    elif choice == "2":
        print_pnl(summary, fiat)
    elif choice == "3":
        print_fees(summary, fiat)
    elif choice == "4":
        console.print("CSV mis à jour.")

    console.print(f"[green]CSV:[/green] {csv_path}")
    console.print(f"[green]Ledger:[/green] {ledger_path}")
    console.print("[green]Latest:[/green] exports/btc_report_latest.csv, exports/btc_ledger_latest.csv")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btc-tracker")
    subparsers = parser.add_subparsers(required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local database")
    init_parser.set_defaults(func=command_init)

    wallet_parser = subparsers.add_parser("wallet", help="Manage watch-only wallets")
    wallet_subparsers = wallet_parser.add_subparsers(required=True)
    wallet_add = wallet_subparsers.add_parser("add", help="Add a BTC address")
    wallet_add.add_argument("address")
    wallet_add.add_argument("--label")
    wallet_add.set_defaults(func=command_wallet_add)

    sync_parser = subparsers.add_parser("sync", help="Sync external sources")
    sync_subparsers = sync_parser.add_subparsers(required=True)
    sync_binance = sync_subparsers.add_parser("binance", help="Sync Binance Spot trades")
    sync_binance.add_argument("--symbols", nargs="+")
    sync_binance.set_defaults(func=command_sync_binance)
    sync_binance_all = sync_subparsers.add_parser("binance-all", help="Sync Binance Spot, fiat, convert, crypto deposits and withdrawals")
    sync_binance_all.add_argument("--symbols", nargs="+")
    sync_binance_all.add_argument("--days", type=int, default=365)
    sync_binance_all.set_defaults(func=command_sync_binance_all)
    sync_wallets = sync_subparsers.add_parser("wallets", help="Sync watch-only BTC UTXOs")
    sync_wallets.set_defaults(func=command_sync_wallets)

    report_parser = subparsers.add_parser("report", help="Generate CSV report")
    report_parser.add_argument("--fiat", default="EUR")
    report_parser.add_argument("--from-date", help="Start date YYYY-MM-DD. Defaults to first day of current month.")
    report_parser.add_argument("--spot-price", type=float)
    report_parser.set_defaults(func=command_report)

    refresh_parser = subparsers.add_parser("refresh", help="Sync Binance, sync wallets, and print the current period report")
    refresh_parser.add_argument("--fiat", default="EUR")
    refresh_parser.add_argument("--from-date", help="Start date YYYY-MM-DD. Defaults to first day of current month.")
    refresh_parser.add_argument("--symbols", nargs="+")
    refresh_parser.add_argument("--days", type=int, default=365)
    refresh_parser.add_argument("--spot-price", type=float)
    refresh_parser.set_defaults(func=command_refresh)

    run_parser = subparsers.add_parser("run", help="Open an interactive numbered menu")
    run_parser.add_argument("--fiat", default="EUR")
    run_parser.add_argument("--from-date", help="Start date YYYY-MM-DD. Defaults to first day of current month.")
    run_parser.add_argument("--symbols", nargs="+")
    run_parser.add_argument("--days", type=int, default=365)
    run_parser.add_argument("--spot-price", type=float)
    run_parser.set_defaults(func=command_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
