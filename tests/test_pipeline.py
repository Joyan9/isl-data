import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from fotmob_isl import parse
from fotmob_isl.store import save_raw, load_raw, upsert_csv
from fotmob_isl.validate import validate_match

FIXTURE = Path(__file__).parent / "fixtures" / "matchDetails_6361990.json.gz"
BENGALURU, DELHI = 485935, 1086744


@pytest.fixture(scope="module")
def md():
    with gzip.open(FIXTURE, "rb") as f:
        return json.loads(f.read())


def test_meta(md):
    m = parse.match_meta(md)
    assert m["match_id"] == 6361990 and m["league_id"] == 9478 and m["finished"]
    assert m["home"]["id"] == BENGALURU and m["away"]["id"] == DELHI


def test_stat_value_parsing():
    assert parse.parse_stat_value("512 (88%)") == (512, 88, "512 (88%)")
    assert isinstance(parse.parse_stat_value("37")[0], int)
    assert parse.parse_stat_value("2.97") == (2.97, None, "2.97")
    assert parse.parse_stat_value(64) == (64.0, None, "64")
    assert parse.parse_stat_value(None) == (None, None, None)


def _team(md, period="All"):
    rows = parse.parse_team_stats(md)
    return {(r["side"], r["group_key"], r["stat_key"]): r["value_num"]
            for r in rows if r["period"] == period}


def test_xg_breakdown_matches_the_page(md):
    t = _team(md)
    g = "expected_goals"
    expected = {
        "expected_goals": (2.97, 1.85),
        "expected_goals_open_play": (2.52, 1.72),
        "expected_goals_set_play": (0.45, 0.13),
        "expected_goals_non_penalty": (2.97, 1.85),
        "expected_goals_on_target": (1.97, 2.08),
    }
    for key, (home, away) in expected.items():
        assert t[("home", g, key)] == pytest.approx(home)
        assert t[("away", g, key)] == pytest.approx(away)


def test_percentage_stats_split(md):
    rows = [r for r in parse.parse_team_stats(md)
            if r["period"] == "All" and r["stat_key"] == "accurate_passes"
            and r["group_key"] == "passes" and r["side"] == "home"]
    assert rows[0]["value_num"] == 512 and rows[0]["value_pct"] == 88


def test_all_three_periods_present(md):
    assert {r["period"] for r in parse.parse_team_stats(md)} == {"All", "FirstHalf", "SecondHalf"}


def test_shots(md):
    shots = parse.parse_shots(md)
    assert len(shots) == 38
    goals = [s for s in shots if s["event_type"] == "Goal"]
    credited = sorted(s["credited_team_id"] for s in goals)
    assert credited == [BENGALURU] * 3 + [DELHI] * 2          # 3-2, own goal credited to Delhi
    og = [s for s in shots if s["is_own_goal"]]
    assert len(og) == 1 and og[0]["xg"] is None
    assert og[0]["team_id"] == BENGALURU and og[0]["credited_team_id"] == DELHI


def test_shot_sums_reconcile_with_team_totals(md):
    errors, warnings = validate_match(md)
    assert errors == [] and warnings == []


def test_player_stats(md):
    rows = parse.parse_player_stats(md)
    ryan = {r["stat_key"]: r for r in rows
            if r["player_name"] == "Ryan Williams" and r["group_key"] == "top_stats"}
    assert ryan["minutes_played"]["value_num"] == 90
    assert ryan["expected_goals"]["value_num"] == pytest.approx(0.7)
    assert ryan["accurate_passes"]["value_num"] == 20 and ryan["accurate_passes"]["value_total"] == 21
    assert {r["group_key"] for r in rows} >= {"top_stats", "attack", "defense", "duels"}
    assert {r["team_name"] for r in rows} == {"Bengaluru FC", "SC Delhi"}   # same names as team table
    gk = {r["stat_key"] for r in rows if r["player_name"] == "Gurpreet Singh Sandhu"}
    assert {"saves", "goals_prevented", "expected_goals_on_target_faced"} <= gk


@pytest.mark.parametrize("fn,pk", [
    (parse.parse_team_stats, parse.TEAM_STATS_PK),
    (parse.parse_shots, parse.SHOT_PK),
    (parse.parse_player_stats, parse.PLAYER_STATS_PK),
])
def test_primary_keys_are_unique(md, fn, pk):
    df = pd.DataFrame(fn(md))
    assert not df.duplicated(subset=pk).any()


def test_missing_blocks_are_tolerated(md):
    bare = {"general": md["general"], "header": md["header"], "content": {}}
    assert parse.parse_team_stats(bare) == []
    assert parse.parse_shots(bare) == []
    assert parse.parse_player_stats(bare) == []


def test_upsert_is_idempotent_and_replaces_per_match(md, tmp_path):
    rows = parse.parse_shots(md)
    path = tmp_path / "shots.csv"
    upsert_csv(path, rows, parse.SHOT_COLS, parse.SHOT_PK, [6361990])
    first = path.read_text()
    upsert_csv(path, rows, parse.SHOT_COLS, parse.SHOT_PK, [6361990])
    assert path.read_text() == first
    other = [dict(r, match_id=111) for r in rows]
    upsert_csv(path, other, parse.SHOT_COLS, parse.SHOT_PK, [111])
    df = pd.read_csv(path, dtype=str)
    assert df["match_id"].nunique() == 2 and len(df) == 76
    assert list(df.columns) == parse.SHOT_COLS


def test_raw_roundtrip_is_deterministic(md, tmp_path):
    p1 = save_raw(tmp_path / "a", 6361990, md)
    p2 = save_raw(tmp_path / "b", 6361990, md)
    assert p1.read_bytes() == p2.read_bytes()
    assert load_raw(p1) == md
