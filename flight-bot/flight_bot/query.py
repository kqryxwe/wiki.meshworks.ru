"""Parsing of the compact trip syntax shared by the CLI and the Telegram bot.

A stop looks like  CODES:MIN-MAX  where CODES is one or more IATA codes
separated by commas and MIN-MAX is the range of nights, e.g.:

    IST:3          Istanbul, exactly 3 nights
    IST,SAW:2-4    Istanbul (either airport), 2 to 4 nights
    TIV,TGD:7-10   Montenegro (Tivat or Podgorica), 7 to 10 nights

A date window is either one date or  FROM..TO :

    2026-08-01
    2026-08-01..2026-08-15
"""

from __future__ import annotations

import re
from datetime import date
from typing import Tuple

from .planner import Stop

_STOP_RE = re.compile(r"^([A-Za-z]{3}(?:,[A-Za-z]{3})*):(\d+)(?:-(\d+))?$")
_IATA_RE = re.compile(r"^[A-Za-z]{3}$")


class QueryError(ValueError):
    pass


def parse_stop(text: str) -> Stop:
    match = _STOP_RE.match(text.strip())
    if not match:
        raise QueryError(
            f"Bad stop '{text}'. Expected CODES:NIGHTS, e.g. IST:3-5 or TIV,TGD:7-10"
        )
    codes = tuple(code.upper() for code in match.group(1).split(","))
    min_nights = int(match.group(2))
    max_nights = int(match.group(3) or match.group(2))
    if not (0 < min_nights <= max_nights):
        raise QueryError(f"Bad nights range in '{text}'")
    return Stop(codes=codes, min_nights=min_nights, max_nights=max_nights)


def parse_iata(text: str) -> str:
    code = text.strip().upper()
    if not _IATA_RE.match(code):
        raise QueryError(f"'{text}' is not a 3-letter IATA code")
    return code


def parse_date_window(text: str) -> Tuple[date, date]:
    parts = text.strip().split("..")
    try:
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1]) if len(parts) > 1 else start
    except (ValueError, IndexError) as exc:
        raise QueryError(
            f"Bad date window '{text}'. Expected YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD"
        ) from exc
    if end < start:
        raise QueryError(f"Date window '{text}' ends before it starts")
    return start, end
