"""
runs_above_average.py

Collects MLB plate appearance data from Baseball Savant (via pybaseball / Statcast).

Each row = one plate appearance, with:
  - batter, pitcher, game context
  - base/out state BEFORE the PA
  - runs scored DURING the PA
  - base/out state AFTER the PA

Usage:
    python runs_above_average.py
    or import collect_plate_appearances() directly.
"""

from pathlib import Path
import pandas as pd
from pybaseball import statcast, cache
import warnings
warnings.filterwarnings('ignore')

# Paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent

# Cache responses so re-runs don't re-download
cache.enable()

# ---------------------------------------------------------------------------
# Core collection function
# ---------------------------------------------------------------------------

def collect_plate_appearances(start_dt: str, end_dt: str) -> pd.DataFrame:
    """
    Pull Statcast data and return one row per plate appearance.

    Parameters
    ----------
    start_dt : str  e.g. "2026-04-01"
    end_dt   : str  e.g. "2026-07-21"

    Returns
    -------
    pd.DataFrame with columns:
        game_date, game_pk, at_bat_number, inning, inning_topbot,
        batter, pitcher, events,
        outs_before, on_1b, on_2b, on_3b,   ← state at start of PA
        runs_scored,                          ← runs scored during PA
        outs_after, on_1b_after, on_2b_after, on_3b_after  ← state after PA
    """
    print(f"Fetching Statcast data from {start_dt} to {end_dt} …")
    raw = statcast(start_dt=start_dt, end_dt=end_dt)
    print(f"  {len(raw):,} pitches downloaded.")

    # ── 1. Keep only the final pitch of each plate appearance ──────────────
    pa = raw[raw["events"].notna()].copy()
    print(f"  {len(pa):,} plate appearances identified.")

    # ── 2. Sort so PA are in game order ────────────────────────────────────
    pa = (
        pa.sort_values(["game_pk", "at_bat_number"])
          .reset_index(drop=True)
    )

    # ── 3. Runner columns → binary 1/0 ─────────────────────────────────────
    for base in ["on_1b", "on_2b", "on_3b"]:
        pa[base] = pa[base].notna().astype(int)

    # ── 4. Runs scored on this PA ──────────────────────────────────────────
    # post_bat_score − bat_score gives runs that crossed the plate
    pa["runs_scored"] = (pa["post_bat_score"] - pa["bat_score"]).clip(lower=0).astype(int)

    # ── 5. Compute "after" state ────────────────────────────────────────────
    # Strategy: within each half-inning the next PA's starting state IS the
    # current PA's ending state.  For the last PA of a half-inning (inning
    # ends) we set 3 outs and no runners.
    half_inning_key = pa["game_pk"].astype(str) + "_" + pa["inning"].astype(str) + "_" + pa["inning_topbot"]
    pa["_half_inning"] = half_inning_key

    grp = pa.groupby("_half_inning", sort=False)

    pa["outs_after"]  = grp["outs_when_up"].transform(lambda s: s.shift(-1))
    pa["on_1b_after"] = grp["on_1b"].transform(lambda s: s.shift(-1))
    pa["on_2b_after"] = grp["on_2b"].transform(lambda s: s.shift(-1))
    pa["on_3b_after"] = grp["on_3b"].transform(lambda s: s.shift(-1))

    # Last PA of each half-inning → inning over: 3 outs, bases empty
    is_last = pa["outs_after"].isna()
    pa.loc[is_last, ["outs_after", "on_1b_after", "on_2b_after", "on_3b_after"]] = [3, 0, 0, 0]

    for col in ["outs_after", "on_1b_after", "on_2b_after", "on_3b_after"]:
        pa[col] = pa[col].astype(int)

    # ── 6. Batter's and pitcher's team abbreviations ───────────────────────
    # Top of inning → away team bats; Bottom → home team bats
    pa["team"] = pa.apply(
        lambda r: r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"],
        axis=1,
    )
    pa["pitcher_team"] = pa.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Top" else r["away_team"],
        axis=1,
    )

    # ── 7. Rename and select final columns ─────────────────────────────────
    pa = pa.rename(columns={"outs_when_up": "outs_before"})

    result = pa[[
        "game_date", "game_pk", "at_bat_number",
        "inning", "inning_topbot",
        "batter", "pitcher",
        "team",
        "pitcher_team",
        "events",
        # — before —
        "outs_before", "on_1b", "on_2b", "on_3b",
        # — outcome —
        "runs_scored",
        # — after —
        "outs_after", "on_1b_after", "on_2b_after", "on_3b_after",
    ]].reset_index(drop=True)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Adjust date range as needed
    START = "2026-04-01"
    END   = "2026-08-18"

    df = collect_plate_appearances(START, END)

    print("\nSample rows:")
    print(df.head(10).to_string(index=False))
    print(f"\nShape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print(f"Columns: {list(df.columns)}")

    out_path = SCRIPT_DIR / "plate_appearances.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved → {out_path}")
