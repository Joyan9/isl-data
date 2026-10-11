# fotmob-isl

Indian Super League match stats from FotMob -> three CSV tables, committed to this repo by GitHub Actions.

## Tables (`data/`)

| file | grain | primary key |
|---|---|---|
| `team_match_stats.csv` | match x period (`All`/`FirstHalf`/`SecondHalf`) x side x stat | `match_id, period, side, group_key, stat_key` |
| `shots.csv` | one row per shot (shot map: xG, xGOT, coordinates, situation, body part) | `match_id, shot_id` |
| `player_match_stats.csv` | match x player x stat (long format) | `match_id, player_id, group_key, stat_key` |

`data/raw/<match_id>.json.gz` keeps the untouched API response (~30 KB each), so parsing can be re-run
without re-scraping. Join tables on `match_id` and `team_id` / `player_id`.

Things worth knowing when you analyse the data:

- **Own goals** are a row in `shots.csv` with `is_own_goal = True`, `xg`/`xgot` empty, and `team_id` = the team of
  the player who put it in. Use `credited_team_id` for "which team did this goal count for".
- **Player stat groups.** The API only has `top_stats`, `attack`, `defense`, `duels`. The site's *Passes* and
  *Goalkeeping* tabs are regroupings: goalkeeper stats (`saves`, `goals_prevented`,
  `expected_goals_on_target_faced`, ...) sit in `top_stats`. Filter by `stat_key`, not by tab.
- `value_num` is numeric; for "512 (88%)"-style stats `value_num` = 512, `value_pct` = 88 (players use `value_total`).
- Team-level xG vs the sum of shot-level xG can differ slightly (0.012 on the sample match); `validate.py` warns
  above 0.03.

## Usage

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # offline, uses tests/fixtures
python -m fotmob_isl smoke 6361990                    # fetch + parse one match, writes nothing
python -m fotmob_isl ingest --match-ids 6361990 6361991 --skip-existing
```

`ingest` skips unfinished matches and anything outside league 9478, re-ingesting a match replaces its rows, and CSV
output is sorted/deterministic so git diffs only show real changes.

On GitHub: Actions -> *ingest* -> Run workflow -> paste match IDs.

## Not done yet / unverified

1. **Match-ID discovery.** `ingest` needs IDs passed in. The fixtures-list endpoint isn't in the captures yet; once
   it is, a `discover` command + a cron schedule makes this fully automatic.
2. **Runner access.** The API answered 200 inside a logged-in browser tab. Whether it answers a cookie-less
   request from a GitHub runner is untested; the workflow's smoke step is that test. If it gets 401/403 the client
   falls back to parsing `__NEXT_DATA__` from the match page (`https://www.fotmob.com/match/<id>`) -- that URL pattern
   is unverified. Datacenter IPs are sometimes blocked outright.
3. FotMob's terms prohibit automated/systematic access. Keep it low-volume and personal/research, and don't
   republish the raw data.
