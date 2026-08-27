"""Normalize team names across FotMob and Football-Data.co.uk."""

from __future__ import annotations

ALIASES: dict[str, str] = {
    "Nottm Forest": "Nott'm Forest",
    "Nottingham Forest": "Nott'm Forest",
    "Man United": "Man United",
    "Manchester United": "Man United",
    "Man City": "Man City",
    "Manchester City": "Man City",
    "Newcastle United": "Newcastle",
    "Tottenham Hotspur": "Tottenham",
    "Wolverhampton Wanderers": "Wolves",
    "West Ham United": "West Ham",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Ipswich Town": "Ipswich",
    "Leicester City": "Leicester",
}


def normalize_team_name(name: str) -> str:
    cleaned = (name or "").strip()
    return ALIASES.get(cleaned, cleaned)
