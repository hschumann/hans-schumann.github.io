# NBA ATS mean-reversion model

Same public-overreaction idea as the NFL ATS project, adapted for a multi-game week:

1. For each finished game, store the closing home spread and compute each team’s margin against the spread (ATS).
2. A team’s **score** is its **average ATS margin over the trailing 7 days**.
3. For today’s slate, rank matchups by `|home_7d − away_7d|` and bet the **underperformer** (lower 7-day ATS average).
4. Email the **top 3** absolute differences each morning to `hansschumann24@gmail.com`.

## Data sources

| Need | Source |
|------|--------|
| Upcoming spreads | ESPN scoreboard (DraftKings lines) |
| Closing lines for finished games | ESPN game summary `pickcenter` |
| Final scores | ESPN scoreboard |
| Optional book preference | [The Odds API](https://the-odds-api.com) (`ODDS_API_KEY`) |
| Morning alert | Gmail SMTP |

Spreads are snapshotted while games are scheduled, then frozen at tipoff. Finished games missing a stored line are backfilled from ESPN’s summary closing line.

## Setup

```bash
cd NBA_model
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Gmail app password

1. Turn on [2-Step Verification](https://myaccount.google.com/signinoptions/two-step)
2. Create an [App Password](https://myaccount.google.com/apppasswords) (select Mail / Other)
3. Put that 16-character password in `.env` as `SMTP_PASSWORD` (spaces optional)

```bash
SMTP_USER=hansschumann24@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_TO=hansschumann24@gmail.com
```

## Commands

```bash
# Full daily job: sync ESPN, compute picks, send email
python3 scripts/run_daily.py

# Sync + picks without emailing
python3 scripts/run_daily.py --no-email

# Print email body only
python3 scripts/run_daily.py --dry-run

# Force a test email even with zero picks
python3 scripts/run_daily.py --email-always

# Backfill recent scoreboards / closing lines
python3 scripts/backfill.py --days 14

# Picks from current DB only
python3 scripts/show_picks.py
```

Artifacts land in `data/`:

- `nba_ats.db` — SQLite store of games + daily picks
- `games.csv` — flat export
- `latest_picks.json` — this morning’s top bets

## GitHub Actions

Workflow: `.github/workflows/nba-ats-daily.yml` (≈8am ET).

Add repository secrets:

- `SMTP_USER` — `hansschumann24@gmail.com`
- `SMTP_PASSWORD` — Gmail app password
- `ODDS_API_KEY` (optional)

`EMAIL_TO` is hardcoded to `hansschumann24@gmail.com` in the workflow.

The job commits updated `NBA_model/data/*` so history survives across runs.

## Theory note

NFL used last week’s single ATS margin. NBA uses a **7-day average** so teams that played more often are comparable. The bet is still the side that recently underperformed relative to the spread, on the assumption the public overweights that sample.
