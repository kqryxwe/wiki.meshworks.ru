"""Client for the Aviasales (Travelpayouts) data API.

Uses the free "prices for dates" cache API, so no scraping is involved:
https://travelpayouts.github.io/slate/#prices-for-the-selected-dates

You need a free API token from https://www.travelpayouts.com/
(register, create an "API" project, copy the token). Pass it via the
TRAVELPAYOUTS_TOKEN environment variable or the --token CLI flag.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional

import requests

API_BASE = "https://api.travelpayouts.com/aviasales/v3"
SITE_BASE = "https://www.aviasales.ru"


class ApiError(RuntimeError):
    pass


class AviasalesClient:
    """Thin caching client around the grouped_prices endpoint.

    One HTTP request per (origin, destination, month) triple returns the
    cheapest cached offer for every day of that month, which keeps the
    number of requests small even for wide search windows.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        currency: str = "rub",
        market: str = "ru",
        direct_only: bool = False,
        timeout: float = 20.0,
        retries: int = 3,
    ) -> None:
        self.token = token or os.environ.get("TRAVELPAYOUTS_TOKEN", "")
        if not self.token:
            raise ApiError(
                "API token is missing. Get a free token at https://www.travelpayouts.com/ "
                "and set TRAVELPAYOUTS_TOKEN or pass --token."
            )
        self.currency = currency
        self.market = market
        self.direct_only = direct_only
        self.timeout = timeout
        self.retries = retries
        self._session = requests.Session()
        self._session.headers["X-Access-Token"] = self.token
        # (origin, dest, "YYYY-MM") -> {"YYYY-MM-DD": offer dict}
        self._cache: Dict[tuple, Dict[str, dict]] = {}

    def month_prices(self, origin: str, destination: str, month: str) -> Dict[str, dict]:
        """Return {ISO date: cheapest offer} for every day of `month` (YYYY-MM)."""
        key = (origin, destination, month)
        if key in self._cache:
            return self._cache[key]

        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": month,
            "group_by": "departure_at",
            "currency": self.currency,
            "market": self.market,
            "direct": "true" if self.direct_only else "false",
            "token": self.token,
        }
        data = self._get(f"{API_BASE}/grouped_prices", params)
        prices = data.get("data") or {}
        self._cache[key] = prices
        return prices

    def day_price(self, origin: str, destination: str, date: str) -> Optional[dict]:
        """Cheapest cached offer for one specific departure date (YYYY-MM-DD), or None."""
        return self.month_prices(origin, destination, date[:7]).get(date)

    def _get(self, url: str, params: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                if payload.get("success") is False:
                    raise ApiError(f"API error: {payload.get('error', 'unknown')}")
                return payload
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise ApiError(f"Request to {url} failed after {self.retries} attempts: {last_error}")


def booking_link(offer: dict) -> str:
    """Absolute aviasales.ru search link for an offer returned by the API."""
    link = offer.get("link", "")
    return SITE_BASE + link if link.startswith("/") else link
