"""
runs_above_average_analysis.py

Loads plate appearance data and builds a runs-above-average framework:

  1. Load & validate the PA DataFrame
  2. Build the Run Expectancy (RE) matrix  — 24 base/out states
     RE(state) = average runs scored on a PA starting in that state
  3. Attach RE values to each PA and compute runs above average per PA
  4. Aggregate by batter and pitcher

Runs above average per PA  =  runs_scored  −  RE(state_before)
"""

from pathlib import Path
import json
import pandas as pd
from pybaseball import playerid_reverse_lookup

# Paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent
CSV_PATH   = SCRIPT_DIR / "plate_appearances.csv"
SITE_DIR   = SCRIPT_DIR / "../mlb-runs-above-average"
BATTER_JS_PATH  = SITE_DIR / "leaderboard-data.js"
PITCHER_JS_PATH = SITE_DIR / "pitcher-leaderboard-data.js"

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------

def load_data(path: Path = CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["game_date"])
    print(f"Loaded {len(df):,} plate appearances from '{path}'")
    print(f"Date range: {df['game_date'].min().date()} → {df['game_date'].max().date()}")
    print(f"Columns: {list(df.columns)}\n")
    return df


# ---------------------------------------------------------------------------
# 2. Attach player names
# ---------------------------------------------------------------------------

def attach_player_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replaces integer batter/pitcher MLBAM IDs with 'First Last' name strings.
    Looks up all unique player IDs in one batch call.
    """
    all_ids = list(set(df["batter"].tolist() + df["pitcher"].tolist()))
    lookup = playerid_reverse_lookup(all_ids, key_type="mlbam")

    # Build id → full name map
    lookup["name"] = lookup["name_first"].str.title() + " " + lookup["name_last"].str.title()
    name_map = lookup.set_index("key_mlbam")["name"].to_dict()

    df = df.copy()
    df["batter"]  = df["batter"].map(name_map).fillna(df["batter"].astype(str))
    df["pitcher"] = df["pitcher"].map(name_map).fillna(df["pitcher"].astype(str))
    return df


# ---------------------------------------------------------------------------
# 3. Helper: encode a base/out state as a readable string
# ---------------------------------------------------------------------------

def state_label(outs: int, on_1b: int, on_2b: int, on_3b: int) -> str:
    """Return e.g. '1 | 1-0-1'  (outs | 1b-2b-3b)."""
    return f"{outs} | {on_1b}-{on_2b}-{on_3b}"

def add_state_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add human-readable state labels for before/after."""
    df = df.copy()
    df["state_before"] = [
        state_label(o, b1, b2, b3)
        for o, b1, b2, b3 in zip(df.outs_before, df.on_1b, df.on_2b, df.on_3b)
    ]
    df["state_after"] = [
        state_label(o, b1, b2, b3)
        for o, b1, b2, b3 in zip(df.outs_after, df.on_1b_after, df.on_2b_after, df.on_3b_after)
    ]
    return df


# ---------------------------------------------------------------------------
# 3. Run Expectancy matrix
#    RE(state) = average runs_scored on a PA starting in that state
# ---------------------------------------------------------------------------

def build_re_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a 24-row DataFrame with columns: state_before, re, pa_count.
    RE(state) = mean runs_scored for all PAs starting in that state.
    """
    re = (
        df.groupby("state_before")["runs_scored"]
          .agg(re="mean", pa_count="count")
          .reset_index()
    )
    # Sort nicely: by outs then base config
    re[["outs", "_", "bases"]] = re["state_before"].str.split(" | ", expand=True)
    re = re.sort_values(["outs", "bases"]).drop(columns=["outs", "bases"])
    return re.reset_index(drop=True)


def attach_re(df: pd.DataFrame, re_matrix: pd.DataFrame) -> pd.DataFrame:
    """Map expected runs onto each PA for both the before and after states."""
    re_map = re_matrix.set_index("state_before")["re"].to_dict()
    df = df.copy()
    df["re_before"] = df["state_before"].map(re_map)
    # After state: 3 outs → inning over → RE = 0
    df["re_after"]  = df["state_after"].map(re_map).fillna(0.0)
    return df


# ---------------------------------------------------------------------------
# 4. Two value metrics per plate appearance
#
#   raa       = runs_scored − re_before
#               "did the batter score more runs than average for this situation?"
#
#   re_added  = re_after − re_before
#               "did the batter leave the situation better or worse than they found it?"
# ---------------------------------------------------------------------------

def add_raa(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["raa"]      = df["runs_scored"] - df["re_before"]
    df["re_added"] = df["re_after"]    - df["re_before"]
    return df


# ---------------------------------------------------------------------------
# 5. Aggregate RAA by player
# ---------------------------------------------------------------------------

def batter_raa(df: pd.DataFrame, min_pa: int = 50) -> pd.DataFrame:
    """
    Per-batter summary with at least min_pa PAs.
    Columns:
      team         — most recent team abbreviation (handles mid-season trades)
      raa_sum      — total runs scored above average
      re_added_sum — total run expectancy added (situation improvement)
      total_value  — raa_sum + re_added_sum (combined contribution)
    """
    # Most recent team per batter (last PA in date order)
    most_recent_team = (
        df.sort_values("game_date")
          .groupby("batter")["team"]
          .last()
          .reset_index()
    )

    agg = (
        df.groupby("batter")
          .agg(
              pa              = ("raa",      "count"),
              raa_sum         = ("raa",      "sum"),
              raa_per_pa      = ("raa",      "mean"),
              re_added_sum    = ("re_added", "sum"),
              re_added_per_pa = ("re_added", "mean"),
          )
          .reset_index()
    )
    agg["total_value"] = agg["raa_sum"] + agg["re_added_sum"]
    agg = agg.merge(most_recent_team, on="batter", how="left")

    # Reorder so team sits next to the name
    cols = ["batter", "team", "pa", "raa_sum", "raa_per_pa",
            "re_added_sum", "re_added_per_pa", "total_value"]
    return (
        agg[agg["pa"] >= min_pa][cols]
           .sort_values("total_value", ascending=False)
           .reset_index(drop=True)
    )


def pitcher_raa(df: pd.DataFrame, min_bf: int = 50) -> pd.DataFrame:
    """
    Per-pitcher summary (lower values = better for the pitcher).
    Columns mirror batter_raa, using batters faced (bf).
    """
    team_col = "pitcher_team" if "pitcher_team" in df.columns else "team"
    most_recent_team = (
        df.sort_values("game_date")
          .groupby("pitcher")[team_col]
          .last()
          .reset_index()
          .rename(columns={team_col: "team"})
    )

    agg = (
        df.groupby("pitcher")
          .agg(
              bf              = ("raa",      "count"),
              raa_sum         = ("raa",      "sum"),
              raa_per_bf      = ("raa",      "mean"),
              re_added_sum    = ("re_added", "sum"),
              re_added_per_bf = ("re_added", "mean"),
          )
          .reset_index()
    )
    agg["total_value"] = agg["raa_sum"] + agg["re_added_sum"]
    agg = agg.merge(most_recent_team, on="pitcher", how="left")

    cols = ["pitcher", "team", "bf", "raa_sum", "raa_per_bf",
            "re_added_sum", "re_added_per_bf", "total_value"]
    return (
        agg[agg["bf"] >= min_bf][cols]
           .sort_values("total_value")       # ascending: best pitchers first
           .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# 6. Write leaderboard JS files for the website
# ---------------------------------------------------------------------------

def batters_to_js_rows(batters: pd.DataFrame) -> list:
    rows = []
    for rank, row in enumerate(batters.itertuples(), start=1):
        rows.append({
            "rank": rank,
            "player": row.batter,
            "team": row.team,
            "pa": int(row.pa),
            "raa": round(row.raa_sum, 2),
            "reAdded": round(row.re_added_sum, 2),
            "total": round(row.total_value, 2),
            "valuePerPa": round(row.total_value / row.pa, 4),
        })
    return rows


def pitchers_to_js_rows(pitchers: pd.DataFrame) -> list:
    rows = []
    for rank, row in enumerate(pitchers.itertuples(), start=1):
        rows.append({
            "rank": rank,
            "player": row.pitcher,
            "team": row.team,
            "bf": int(row.bf),
            "raa": round(row.raa_sum, 2),
            "reAdded": round(row.re_added_sum, 2),
            "total": round(row.total_value, 2),
            "valuePerBf": round(row.total_value / row.bf, 4),
        })
    return rows


def write_js_var(rows: list, var_name: str, path: Path) -> None:
    path.write_text(
        f"window.{var_name} = {json.dumps(rows, ensure_ascii=True)};\n",
        encoding="utf-8",
    )
    print(f"✓ Wrote {len(rows)} rows to {path}")


# ---------------------------------------------------------------------------
# Main: run the full pipeline
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pd.set_option("display.float_format", "{:.3f}".format)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 120)

    # ── Load ──────────────────────────────────────────────────────────────
    df = load_data()

    # ── Attach player names ────────────────────────────────────────────────
    print("Looking up player names …")
    df = attach_player_names(df)

    # ── Build state labels ─────────────────────────────────────────────────
    df = add_state_columns(df)

    # ── Run Expectancy matrix ─────────────────────────────────────────────
    re_matrix = build_re_matrix(df)
    print("=== Run Expectancy Matrix ===")
    print(re_matrix.to_string(index=False))
    print()

    # ── Attach RE values and compute RAA ──────────────────────────────────
    df = attach_re(df, re_matrix)
    df = add_raa(df)

    # ── Batter leaderboard ────────────────────────────────────────────────
    batters = batter_raa(df, min_pa=100)
    print("=== Top 15 Batters by RAA ===")
    print(batters.head(15).to_string(index=False))
    print()

    print("=== Bottom 15 Batters by RAA ===")
    print(batters.tail(15).to_string(index=False))
    print()

    # ── Pitcher leaderboard ───────────────────────────────────────────────
    pitchers = pitcher_raa(df, min_bf=100)
    print("=== Top 15 Pitchers by RAA (lowest = best) ===")
    print(pitchers.head(15).to_string(index=False))
    print()

    # ── Quick sanity checks ───────────────────────────────────────────────
    print("=== Sanity Checks ===")
    print(f"Mean RAA per PA     (should be ~0): {df['raa'].mean():.4f}")
    print(f"Mean re_added per PA (should be ~0): {df['re_added'].mean():.4f}")
    print(f"Total runs in data: {df['runs_scored'].sum():,}")
    print(f"RAA range:      [{df['raa'].min():.3f}, {df['raa'].max():.3f}]")
    print(f"re_added range: [{df['re_added'].min():.3f}, {df['re_added'].max():.3f}]")

    # ── Write website leaderboards ────────────────────────────────────────
    write_js_var(batters_to_js_rows(batters), "MLB_RAA_LEADERBOARD", BATTER_JS_PATH)
    write_js_var(pitchers_to_js_rows(pitchers), "MLB_RAA_PITCHERS", PITCHER_JS_PATH)
