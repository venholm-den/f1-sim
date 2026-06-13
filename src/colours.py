from __future__ import annotations

from typing import Any

import fastf1.plotting


FALLBACK_TEAM_COLOURS = {
    "Mercedes": "#00D2BE",
    "Ferrari": "#DC0000",
    "Red Bull Racing": "#1E5BC6",
    "Red Bull Rac": "#1E5BC6",
    "McLaren": "#FF8700",
    "Williams": "#005AFF",
    "Racing Bulls": "#6692FF",
    "Racing Bull": "#6692FF",
    "Aston Martin": "#229971",
    "Aston Marti": "#229971",
    "Alpine": "#FF87BC",
    "Haas": "#B6BABD",
    "Haas F1 Team": "#B6BABD",
    "Haas F1 Tea": "#B6BABD",
    "Audi": "#9B0000",
    "Cadillac": "#6C6E70",
}

DEFAULT_TEXT_COLOUR = "#F2F2F2"


def get_team_colour(
    team: Any,
    session: Any | None = None,
    fallback: str = DEFAULT_TEXT_COLOUR,
) -> str:
    team_name = str(team).strip()

    if not team_name or team_name.lower() in {"nan", "none"}:
        return fallback

    if session is not None:
        try:
            colour = fastf1.plotting.get_team_color(
                team_name,
                session=session,
            )

            if colour:
                return str(colour)
        except Exception:
            pass

    if team_name in FALLBACK_TEAM_COLOURS:
        return FALLBACK_TEAM_COLOURS[team_name]

    lowered = team_name.lower()

    for known_team, colour in FALLBACK_TEAM_COLOURS.items():
        known_lower = known_team.lower()

        if known_lower in lowered or lowered in known_lower:
            return colour

    return fallback