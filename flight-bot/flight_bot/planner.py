"""Itinerary planner: combines one-way legs into the cheapest multi-city trips.

The trip is described as an origin, an ordered list of stops (each with one
or more alternative airports and a min..max range of nights) and a window of
possible departure dates. The planner enumerates every combination of
departure date, stay lengths and airport alternatives, prices each leg with
the cached API data and returns the cheapest complete itineraries.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Sequence

from .api import AviasalesClient


@dataclass(frozen=True)
class Stop:
    """One stopover: alternative IATA codes and how many nights to stay."""

    codes: Sequence[str]
    min_nights: int
    max_nights: int

    def __post_init__(self) -> None:
        if not self.codes:
            raise ValueError("Stop needs at least one IATA code")
        if not (0 < self.min_nights <= self.max_nights):
            raise ValueError(f"Bad nights range {self.min_nights}-{self.max_nights}")


@dataclass(frozen=True)
class TripQuery:
    origin: str
    stops: Sequence[Stop]
    start_from: date
    start_to: date
    return_home: bool = True

    def __post_init__(self) -> None:
        if not self.stops:
            raise ValueError("Trip needs at least one stop")
        if self.start_from > self.start_to:
            raise ValueError("start_from is after start_to")


@dataclass(frozen=True)
class Leg:
    origin: str
    destination: str
    depart: date
    price: float
    offer: dict


@dataclass(frozen=True)
class Itinerary:
    legs: Sequence[Leg]
    total: float
    currency: str

    @property
    def start(self) -> date:
        return self.legs[0].depart

    @property
    def end(self) -> date:
        return self.legs[-1].depart


@dataclass
class PlanStats:
    combos_checked: int = 0
    combos_priced: int = 0
    missing_legs: set = field(default_factory=set)


def plan(
    query: TripQuery,
    client: AviasalesClient,
    top_n: int = 5,
    max_combos: int = 20000,
    stats: Optional[PlanStats] = None,
) -> List[Itinerary]:
    """Return up to `top_n` cheapest itineraries, sorted by total price."""
    stats = stats if stats is not None else PlanStats()
    start_dates = _date_range(query.start_from, query.start_to)
    stay_choices = [range(s.min_nights, s.max_nights + 1) for s in query.stops]
    airport_choices = [list(s.codes) for s in query.stops]

    # heap of (-total, counter, itinerary) keeps the N cheapest seen so far
    best: list = []
    counter = itertools.count()

    for start in start_dates:
        for stays in itertools.product(*stay_choices):
            for airports in itertools.product(*airport_choices):
                stats.combos_checked += 1
                if stats.combos_checked > max_combos:
                    return _collect(best)
                itinerary = _price_combo(query, client, start, stays, airports, stats)
                if itinerary is None:
                    continue
                stats.combos_priced += 1
                item = (-itinerary.total, next(counter), itinerary)
                if len(best) < top_n:
                    heapq.heappush(best, item)
                elif itinerary.total < -best[0][0]:
                    heapq.heapreplace(best, item)

    return _collect(best)


def _price_combo(
    query: TripQuery,
    client: AviasalesClient,
    start: date,
    stays: Sequence[int],
    airports: Sequence[str],
    stats: PlanStats,
) -> Optional[Itinerary]:
    points = [query.origin, *airports]
    if query.return_home:
        points.append(query.origin)

    legs: List[Leg] = []
    depart = start
    for i in range(len(points) - 1):
        origin, destination = points[i], points[i + 1]
        offer = client.day_price(origin, destination, depart.isoformat())
        if offer is None or "price" not in offer:
            stats.missing_legs.add((origin, destination, depart.isoformat()))
            return None
        legs.append(Leg(origin, destination, depart, float(offer["price"]), offer))
        if i < len(stays):
            depart = depart + timedelta(days=stays[i])

    total = sum(leg.price for leg in legs)
    return Itinerary(legs=legs, total=total, currency=client.currency)


def _date_range(start: date, end: date) -> List[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _collect(heap: list) -> List[Itinerary]:
    return sorted((item[2] for item in heap), key=lambda it: it.total)
