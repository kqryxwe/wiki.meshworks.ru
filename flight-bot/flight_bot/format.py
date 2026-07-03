"""Human-readable rendering of itineraries (plain text, Telegram-friendly)."""

from __future__ import annotations

from typing import List

from .api import booking_link
from .planner import Itinerary, PlanStats

_CURRENCY_SIGNS = {"rub": "₽", "usd": "$", "eur": "€", "kzt": "₸"}


def format_price(amount: float, currency: str) -> str:
    sign = _CURRENCY_SIGNS.get(currency.lower(), currency.upper())
    return f"{amount:,.0f} {sign}".replace(",", " ")


def format_itinerary(itinerary: Itinerary, rank: int, with_links: bool = True) -> str:
    lines = [
        f"#{rank}  TOTAL {format_price(itinerary.total, itinerary.currency)}"
        f"  ({itinerary.start.isoformat()} → {itinerary.end.isoformat()})"
    ]
    for leg in itinerary.legs:
        offer = leg.offer
        airline = offer.get("airline", "??")
        flight = offer.get("flight_number", "")
        transfers = offer.get("transfers", 0)
        transfer_note = "direct" if not transfers else f"{transfers} transfer(s)"
        lines.append(
            f"  {leg.depart.isoformat()}  {leg.origin} → {leg.destination}"
            f"  {format_price(leg.price, itinerary.currency)}"
            f"  {airline}{flight}  {transfer_note}"
        )
        if with_links:
            link = booking_link(offer)
            if link:
                lines.append(f"    {link}")
    return "\n".join(lines)


def format_results(itineraries: List[Itinerary], stats: PlanStats, with_links: bool = True) -> str:
    if not itineraries:
        hints = [
            "No complete itineraries found.",
            f"Combinations checked: {stats.combos_checked}, fully priced: {stats.combos_priced}.",
        ]
        if stats.missing_legs:
            sample = sorted(stats.missing_legs)[:5]
            hints.append("No cached price for e.g.: " + "; ".join(
                f"{o}→{d} on {day}" for o, d, day in sample
            ))
            hints.append(
                "Try a wider date window, other nearby airports, or drop --direct."
            )
        return "\n".join(hints)

    blocks = [
        format_itinerary(it, rank, with_links=with_links)
        for rank, it in enumerate(itineraries, start=1)
    ]
    footer = (
        f"({stats.combos_priced} of {stats.combos_checked} combinations had prices; "
        "prices come from the Aviasales cache — verify on the booking page)"
    )
    return "\n\n".join(blocks) + "\n\n" + footer
