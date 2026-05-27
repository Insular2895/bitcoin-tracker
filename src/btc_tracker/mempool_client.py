from __future__ import annotations

import requests


class MempoolClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def validate_address(self, address: str) -> bool:
        response = requests.get(f"{self.base_url}/v1/validate-address/{address}", timeout=30)
        response.raise_for_status()
        return bool(response.json().get("isvalid"))

    def address_utxos(self, address: str) -> list[dict]:
        response = requests.get(f"{self.base_url}/address/{address}/utxo", timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"Unexpected mempool.space UTXO response: {data}")
        return data

    def latest_btc_price(self, fiat: str) -> float:
        response = requests.get(f"{self.base_url}/v1/prices", timeout=30)
        response.raise_for_status()
        prices = response.json()
        return float(prices[fiat.upper()])


def normalize_utxo(address: str, utxo: dict) -> dict[str, object]:
    status = utxo.get("status", {})
    return {
        "address": address,
        "txid": str(utxo["txid"]),
        "vout": int(utxo["vout"]),
        "value_sats": int(utxo["value"]),
        "block_time": status.get("block_time"),
        "confirmed": 1 if status.get("confirmed") else 0,
    }
