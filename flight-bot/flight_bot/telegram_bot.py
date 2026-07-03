"""Minimal Telegram bot (long polling, no extra dependencies beyond requests).

Run:
    export TRAVELPAYOUTS_TOKEN=...   # travelpayouts.com API token
    export TELEGRAM_BOT_TOKEN=...    # token from @BotFather
    python -m flight_bot.telegram_bot

Chat command format:

    /search SCO IST:2-4 TIV,TGD:7-10 2026-08-01..2026-08-15

i.e. /search ORIGIN STOP [STOP ...] DATE_WINDOW
"""

from __future__ import annotations

import html
import logging
import os
import sys

import requests

from .api import ApiError, AviasalesClient
from .format import format_results
from .planner import PlanStats, TripQuery, plan
from .query import QueryError, parse_date_window, parse_iata, parse_stop

log = logging.getLogger("flight_bot.telegram")

HELP_TEXT = (
    "Я ищу самые дешёвые маршруты с остановками через кэш цен Aviasales.\n\n"
    "Формат запроса:\n"
    "/search ОТКУДА ОСТАНОВКА [ОСТАНОВКА ...] ДАТЫ\n\n"
    "Остановка: КОДЫ:НОЧИ, например IST:2-4 (Стамбул на 2–4 ночи) "
    "или TIV,TGD:7-10 (Тиват или Подгорица на 7–10 ночей).\n"
    "Даты — окно вылета: 2026-08-01..2026-08-15\n\n"
    "Пример:\n"
    "/search SCO IST:2-4 TIV,TGD:7-10 2026-08-01..2026-08-15"
)


def handle_search(args: list[str], client: AviasalesClient) -> str:
    if len(args) < 3:
        return HELP_TEXT
    try:
        origin = parse_iata(args[0])
        start_from, start_to = parse_date_window(args[-1])
        stops = [parse_stop(part) for part in args[1:-1]]
        query = TripQuery(
            origin=origin, stops=stops, start_from=start_from, start_to=start_to
        )
        stats = PlanStats()
        results = plan(query, client, top_n=3, stats=stats)
        return format_results(results, stats)
    except (QueryError, ValueError) as exc:
        return f"Ошибка в запросе: {exc}\n\n{HELP_TEXT}"
    except ApiError as exc:
        return f"Ошибка API: {exc}"


class TelegramBot:
    def __init__(self, bot_token: str, client: AviasalesClient) -> None:
        self.api = f"https://api.telegram.org/bot{bot_token}"
        self.client = client
        self.session = requests.Session()

    def run_forever(self) -> None:
        offset = 0
        log.info("Bot started, long-polling for updates")
        while True:
            try:
                response = self.session.get(
                    f"{self.api}/getUpdates",
                    params={"offset": offset, "timeout": 50},
                    timeout=60,
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = update["update_id"] + 1
                    self._handle_update(update)
            except requests.RequestException as exc:
                log.warning("Polling error, retrying: %s", exc)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        if not chat_id or not text:
            return
        parts = text.split()
        command = parts[0].split("@")[0].lower()
        if command in ("/start", "/help"):
            reply = HELP_TEXT
        elif command == "/search":
            self._send(chat_id, "Ищу варианты, это может занять минуту…")
            reply = handle_search(parts[1:], self.client)
        else:
            reply = HELP_TEXT
        self._send(chat_id, reply)

    def _send(self, chat_id: int, text: str) -> None:
        # Telegram limits messages to 4096 chars; split on blank lines if needed.
        chunks, current = [], ""
        for block in text.split("\n\n"):
            candidate = (current + "\n\n" + block).strip()
            if len(candidate) > 3900 and current:
                chunks.append(current)
                current = block
            else:
                current = candidate
        if current:
            chunks.append(current)
        for chunk in chunks:
            try:
                self.session.post(
                    f"{self.api}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": html.unescape(chunk),
                        "disable_web_page_preview": True,
                    },
                    timeout=30,
                )
            except requests.RequestException as exc:
                log.warning("sendMessage failed: %s", exc)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print("Set TELEGRAM_BOT_TOKEN (token from @BotFather)", file=sys.stderr)
        return 2
    try:
        client = AviasalesClient()
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    TelegramBot(bot_token, client).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
