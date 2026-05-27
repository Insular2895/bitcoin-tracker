from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import requests


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.binance.com") -> None:
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.base_url = base_url.rstrip("/")

    def _signed_get(self, path: str, params: dict[str, str | int]) -> object:
        params = {
            **params,
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        query = urlencode(params)
        signature = hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()
        url = f"{self.base_url}{path}?{query}&signature={signature}"
        response = requests.get(url, headers={"X-MBX-APIKEY": self.api_key}, timeout=30)
        response.raise_for_status()
        return response.json()

    def _signed_get_list(self, path: str, params: dict[str, str | int]) -> list[dict]:
        data = self._signed_get(path, params)
        if not isinstance(data, list):
            raise ValueError(f"Unexpected Binance response for {path}: {data}")
        return data

    def _signed_get_dict(self, path: str, params: dict[str, str | int]) -> dict:
        data = self._signed_get(path, params)
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected Binance response for {path}: {data}")
        return data

    def my_trades(self, symbol: str, limit: int = 1000) -> list[dict]:
        return self._signed_get_list("/api/v3/myTrades", {"symbol": symbol.upper(), "limit": limit})

    def account(self) -> dict:
        return self._signed_get_dict("/api/v3/account", {})

    def ticker_price(self, symbol: str) -> float:
        response = requests.get(f"{self.base_url}/api/v3/ticker/price", params={"symbol": symbol.upper()}, timeout=30)
        response.raise_for_status()
        return float(response.json()["price"])

    def fiat_orders(self, transaction_type: int, start_ms: int, end_ms: int) -> dict:
        return self._signed_get_dict(
            "/sapi/v1/fiat/orders",
            {
                "transactionType": transaction_type,
                "beginTime": start_ms,
                "endTime": end_ms,
                "page": 1,
                "rows": 500,
            },
        )

    def crypto_deposits(self, start_ms: int, end_ms: int, coin: str | None = None) -> list[dict]:
        params: dict[str, str | int] = {"startTime": start_ms, "endTime": end_ms, "limit": 1000}
        if coin:
            params["coin"] = coin.upper()
        return self._signed_get_list("/sapi/v1/capital/deposit/hisrec", params)

    def crypto_withdrawals(self, start_ms: int, end_ms: int, coin: str | None = None) -> list[dict]:
        params: dict[str, str | int] = {"startTime": start_ms, "endTime": end_ms, "limit": 1000}
        if coin:
            params["coin"] = coin.upper()
        return self._signed_get_list("/sapi/v1/capital/withdraw/history", params)

    def convert_trade_flow(self, start_ms: int, end_ms: int) -> dict:
        return self._signed_get_dict(
            "/sapi/v1/convert/tradeFlow",
            {"startTime": start_ms, "endTime": end_ms, "limit": 1000},
        )


def iter_time_windows(days_back: int, max_days: int) -> Iterator[tuple[int, int]]:
    end = datetime.now(UTC)
    start = end - timedelta(days=days_back)
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=max_days), end)
        yield int(cursor.timestamp() * 1000), int(window_end.timestamp() * 1000)
        cursor = window_end


def normalize_trade(symbol: str, trade: dict) -> dict[str, object]:
    qty = float(trade["qty"])
    commission = float(trade["commission"])
    commission_asset = str(trade["commissionAsset"]).upper()
    side = "BUY" if trade["isBuyer"] else "SELL"

    qty_btc = qty
    if side == "BUY" and commission_asset == "BTC":
        qty_btc = qty - commission

    return {
        "source": "api",
        "exchange": "binance",
        "symbol": symbol.upper(),
        "order_id": str(trade["orderId"]),
        "trade_id": str(trade["id"]),
        "time_ms": int(trade["time"]),
        "side": side,
        "price_quote": float(trade["price"]),
        "qty_btc": qty_btc,
        "quote_qty": float(trade["quoteQty"]),
        "fee_amount": commission,
        "fee_asset": commission_asset,
        "raw_json": json.dumps(trade, sort_keys=True),
    }


def normalize_fiat_order(transaction_type: str, order: dict) -> dict[str, object]:
    return {
        "source": "binance",
        "transaction_type": transaction_type,
        "external_id": str(order.get("orderNo") or order.get("orderId") or order),
        "asset": str(order.get("fiatCurrency", "")).upper(),
        "amount": float(order.get("amount") or 0),
        "fee": float(order.get("totalFee") or 0),
        "status": str(order.get("status", "")),
        "time_ms": int(order.get("updateTime") or order.get("createTime") or 0),
        "raw_json": json.dumps(order, sort_keys=True),
    }


def normalize_crypto_deposit(deposit: dict) -> dict[str, object]:
    return {
        "source": "binance",
        "external_id": str(deposit.get("id") or deposit.get("txId") or deposit),
        "coin": str(deposit.get("coin", "")).upper(),
        "network": str(deposit.get("network", "")),
        "amount": float(deposit.get("amount") or 0),
        "address": str(deposit.get("address", "")),
        "txid": str(deposit.get("txId", "")),
        "status": str(deposit.get("status", "")),
        "time_ms": int(deposit.get("completeTime") or deposit.get("insertTime") or 0),
        "raw_json": json.dumps(deposit, sort_keys=True),
    }


def normalize_crypto_withdrawal(withdrawal: dict) -> dict[str, object]:
    return {
        "source": "binance",
        "external_id": str(withdrawal.get("id") or withdrawal.get("txId") or withdrawal),
        "coin": str(withdrawal.get("coin", "")).upper(),
        "network": str(withdrawal.get("network", "")),
        "amount": float(withdrawal.get("amount") or 0),
        "fee": float(withdrawal.get("transactionFee") or 0),
        "address": str(withdrawal.get("address", "")),
        "txid": str(withdrawal.get("txId", "")),
        "status": str(withdrawal.get("status", "")),
        "time_ms": _parse_binance_time(withdrawal.get("completeTime") or withdrawal.get("applyTime")),
        "raw_json": json.dumps(withdrawal, sort_keys=True),
    }


def normalize_convert_trade(convert: dict) -> dict[str, object]:
    return {
        "source": "binance",
        "external_id": str(convert.get("orderId") or convert.get("quoteId") or convert),
        "from_asset": str(convert.get("fromAsset", "")).upper(),
        "from_amount": float(convert.get("fromAmount") or 0),
        "to_asset": str(convert.get("toAsset", "")).upper(),
        "to_amount": float(convert.get("toAmount") or 0),
        "ratio": float(convert.get("ratio") or 0),
        "inverse_ratio": float(convert.get("inverseRatio") or 0),
        "status": str(convert.get("orderStatus", "")),
        "time_ms": int(convert.get("createTime") or 0),
        "raw_json": json.dumps(convert, sort_keys=True),
    }


def _parse_binance_time(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp() * 1000)
        except ValueError:
            return 0
    return 0
