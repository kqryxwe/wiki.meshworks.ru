"""Planner and parser tests using a fake API client (no network, no token)."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flight_bot.planner import PlanStats, Stop, TripQuery, plan
from flight_bot.query import QueryError, parse_date_window, parse_stop


class FakeClient:
    """day_price returns deterministic fake offers from a price table."""

    currency = "rub"

    def __init__(self, prices):
        # prices: {(origin, dest, "YYYY-MM-DD"): price}
        self.prices = prices
        self.calls = 0

    def day_price(self, origin, destination, day):
        self.calls += 1
        price = self.prices.get((origin, destination, day))
        if price is None:
            return None
        return {
            "price": price,
            "airline": "XX",
            "flight_number": "1",
            "transfers": 0,
            "link": f"/search/{origin}{day.replace('-', '')[6:8]}{destination}1",
        }


def full_price_table(pairs, days, base):
    table = {}
    for origin, dest in pairs:
        for day in days:
            table[(origin, dest, day)] = base
    return table


AUGUST = [f"2026-08-{d:02d}" for d in range(1, 32)]


class PlannerTest(unittest.TestCase):
    def make_query(self, **overrides):
        params = dict(
            origin="SCO",
            stops=[Stop(("IST",), 2, 3), Stop(("TIV", "TGD"), 7, 8)],
            start_from=date(2026, 8, 1),
            start_to=date(2026, 8, 3),
        )
        params.update(overrides)
        return TripQuery(**params)

    def test_finds_cheapest_combo(self):
        pairs = [
            ("SCO", "IST"),
            ("IST", "TIV"), ("IST", "TGD"),
            ("TIV", "SCO"), ("TGD", "SCO"),
        ]
        table = full_price_table(pairs, AUGUST, base=10000)
        # Make one specific combination clearly cheapest:
        # depart Aug 2, 3 nights Istanbul, Podgorica for 7 nights.
        table[("SCO", "IST", "2026-08-02")] = 5000
        table[("IST", "TGD", "2026-08-05")] = 4000
        table[("TGD", "SCO", "2026-08-12")] = 6000

        results = plan(self.make_query(), FakeClient(table), top_n=3)

        self.assertTrue(results)
        best = results[0]
        self.assertEqual(best.total, 15000)
        self.assertEqual([leg.destination for leg in best.legs], ["IST", "TGD", "SCO"])
        self.assertEqual(best.legs[0].depart.isoformat(), "2026-08-02")
        self.assertEqual(best.legs[1].depart.isoformat(), "2026-08-05")
        self.assertEqual(best.legs[2].depart.isoformat(), "2026-08-12")
        # results are sorted ascending by total
        totals = [it.total for it in results]
        self.assertEqual(totals, sorted(totals))

    def test_incomplete_combos_are_skipped(self):
        # Only the outbound leg is priced; no way to continue -> no results.
        table = full_price_table([("SCO", "IST")], AUGUST, base=5000)
        stats = PlanStats()
        results = plan(self.make_query(), FakeClient(table), stats=stats)
        self.assertEqual(results, [])
        self.assertEqual(stats.combos_priced, 0)
        self.assertTrue(any(o == "IST" for o, _, _ in stats.missing_legs))

    def test_no_return_trip_has_one_less_leg(self):
        pairs = [("SCO", "IST"), ("IST", "TIV"), ("IST", "TGD")]
        table = full_price_table(pairs, AUGUST, base=7000)
        results = plan(self.make_query(return_home=False), FakeClient(table), top_n=1)
        self.assertEqual(len(results[0].legs), 2)
        self.assertEqual(results[0].total, 14000)


class ParserTest(unittest.TestCase):
    def test_parse_stop_variants(self):
        stop = parse_stop("tiv,tgd:7-10")
        self.assertEqual(stop.codes, ("TIV", "TGD"))
        self.assertEqual((stop.min_nights, stop.max_nights), (7, 10))
        single = parse_stop("IST:3")
        self.assertEqual((single.min_nights, single.max_nights), (3, 3))

    def test_parse_stop_rejects_garbage(self):
        for bad in ("IST", "IST:", "IST:0", "IST:5-2", "ISTANBUL:3", "IST;3"):
            with self.assertRaises(QueryError, msg=bad):
                parse_stop(bad)

    def test_parse_date_window(self):
        start, end = parse_date_window("2026-08-01..2026-08-15")
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-08-01", "2026-08-15"))
        start, end = parse_date_window("2026-08-01")
        self.assertEqual(start, end)
        with self.assertRaises(QueryError):
            parse_date_window("2026-08-15..2026-08-01")


if __name__ == "__main__":
    unittest.main()
