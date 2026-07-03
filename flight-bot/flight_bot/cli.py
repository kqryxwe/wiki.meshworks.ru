"""Command-line interface.

Example — Aktau, a few days in Istanbul, then a beach week in Montenegro
(Tivat or Podgorica, whichever is cheaper), then back home:

    python -m flight_bot \
        --origin SCO \
        --stop IST:2-4 \
        --stop TIV,TGD:7-10 \
        --dates 2026-08-01..2026-08-15 \
        --top 5
"""

from __future__ import annotations

import argparse
import sys

from .api import ApiError, AviasalesClient
from .format import format_results
from .planner import PlanStats, TripQuery, plan
from .query import QueryError, parse_date_window, parse_iata, parse_stop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flight_bot",
        description="Find the cheapest multi-city itineraries via the Aviasales data API.",
    )
    parser.add_argument("--origin", required=True, help="Home airport/city IATA code, e.g. SCO")
    parser.add_argument(
        "--stop",
        action="append",
        required=True,
        metavar="CODES:NIGHTS",
        help="Stopover, repeatable and in order: IST:2-4 or TIV,TGD:7-10",
    )
    parser.add_argument(
        "--dates",
        required=True,
        metavar="FROM[..TO]",
        help="Departure date window, e.g. 2026-08-01..2026-08-15",
    )
    parser.add_argument("--no-return", action="store_true", help="Do not fly back to the origin")
    parser.add_argument("--direct", action="store_true", help="Direct flights only")
    parser.add_argument("--currency", default="rub", help="Currency: rub, usd, eur, kzt (default rub)")
    parser.add_argument("--top", type=int, default=5, help="How many itineraries to show (default 5)")
    parser.add_argument("--no-links", action="store_true", help="Hide booking links")
    parser.add_argument("--token", default=None, help="Travelpayouts API token (or TRAVELPAYOUTS_TOKEN env)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start_from, start_to = parse_date_window(args.dates)
        query = TripQuery(
            origin=parse_iata(args.origin),
            stops=[parse_stop(stop) for stop in args.stop],
            start_from=start_from,
            start_to=start_to,
            return_home=not args.no_return,
        )
        client = AviasalesClient(
            token=args.token,
            currency=args.currency.lower(),
            direct_only=args.direct,
        )
        stats = PlanStats()
        results = plan(query, client, top_n=args.top, stats=stats)
    except (QueryError, ValueError) as exc:
        print(f"Query error: {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1

    print(format_results(results, stats, with_links=not args.no_links))
    return 0 if results else 3


if __name__ == "__main__":
    sys.exit(main())
