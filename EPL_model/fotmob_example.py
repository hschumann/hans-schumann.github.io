#!/usr/bin/env python3
"""Starter script for the fotmob-api library."""

from __future__ import annotations

from datetime import date

from fotmob_api import FotmobAPI

# Premier League on FotMob
PREMIER_LEAGUE_ID = 47


def print_todays_matches(client: FotmobAPI, country_code: str = "ENG") -> None:
    """Print a sample of today's fixtures."""
    matches = client.get_matches(ccode=country_code)
    leagues = matches.get("leagues", [])

    print(f"\nToday's matches ({len(leagues)} leagues)\n")
    shown = 0
    for league in leagues:
        for match in league.get("matches", []):
            home = match["home"]["name"]
            away = match["away"]["name"]
            score = match.get("status", {}).get("scoreStr", "-")
            print(f"  {league['name']}: {home} {score} {away}")
            shown += 1
            if shown >= 10:
                return


def print_premier_league_table(client: FotmobAPI) -> None:
    """Print the current Premier League table."""
    table = client.get_league_table(league_id=PREMIER_LEAGUE_ID)
    rows = table[0]["data"]["table"]["all"]

    print("\nPremier League table (top 10)\n")
    for team in rows[:10]:
        print(f"  {team['idx']:>2}. {team['name']:<24} {team['pts']} pts")


def print_popular_leagues(client: FotmobAPI) -> None:
    """Print FotMob's popular leagues."""
    leagues = client.get_league_all()
    popular = leagues.get("popular", [])

    print("\nPopular leagues\n")
    for league in popular[:8]:
        print(f"  {league['id']:>6}  {league['name']}")


def main() -> None:
    client = FotmobAPI()

    print("FotMob API ready")
    print(f"Date: {date.today().isoformat()}")

    print_popular_leagues(client)
    print_todays_matches(client)
    print_premier_league_table(client)

    print("\nNext steps:")
    print("  client.get_match(match_id=...)")
    print("  client.get_match_details(match_id=...)")
    print("  client.get_player_data_simple(player_id=954)  # Mohamed Salah")
    print("  client.get_fixtures(id=47, season='2025/2026')")


if __name__ == "__main__":
    main()
