import pandas as pd
import csv

from fotmob_isl.site.comparison import (
    TABLE_COLUMNS,
    build_comparison_data,
    parse_comparison_hash,
    write_expected_table_csv,
)
from fotmob_isl.site.data import MatchBundle
from fotmob_isl.xg_model import match_xpts


def _bundle(shots, home_score=0, away_score=1):
    match = {
        "match_id": 1, "home_team_id": 10, "away_team_id": 20,
        "home_team_name": "Bengaluru FC", "away_team_name": "SC Delhi",
        "home_score": home_score, "away_score": away_score,
        "match_date_utc": "2026-01-01T00:00:00Z",
    }
    return MatchBundle(
        match, pd.DataFrame(), pd.DataFrame(shots), pd.DataFrame(),
        "Bengaluru FC", "SC Delhi", "#111111", "#eeeeee", "#ffffff", "#000000",
    )


def test_xpts_sum_and_empty_distribution():
    result = match_xpts([], 10, 20)
    assert result["home"] == result["away"] == 1
    result = match_xpts([{"team_id": 10, "xg": 1.0}, {"team_id": 20, "xg": 0.0}], 10, 20)
    assert result["home"] == 3 and result["away"] == 0


def test_table_credits_own_goal_to_benefitting_team():
    data = build_comparison_data([_bundle([
        {"match_id": 1, "team_id": 10, "side": "home", "event_type": "Goal",
         "credited_team_id": 20, "xg": None, "is_own_goal": True},
    ])])
    rows = {row["Team"]: row for row in data["table"]}
    assert rows["SC Delhi"]["GF"] == 1
    assert rows["Bengaluru FC"]["GF"] == 0


def test_unplayed_teams_are_ranked_last():
    data = build_comparison_data([_bundle([{
        "match_id": 1, "team_id": 10, "side": "home", "xg": None,
        "is_own_goal": False, "event_type": "Miss", "credited_team_id": None,
    }])])
    rows = {row["Team"]: row for row in data["table"]}
    assert rows["East Bengal FC"]["P"] == 0
    played = [row for row in data["table"] if row["P"] > 0]
    assert all(row["P"] == 0 for row in data["table"][len(played):])
    assert rows["East Bengal FC"]["actual_rank"] > len(played)


def test_csv_columns_and_hash_parser(tmp_path):
    data = build_comparison_data([])
    path = write_expected_table_csv(tmp_path / "expected.csv", data["table"], data["generated_at"])
    assert list(pd.read_csv(path).columns) == TABLE_COLUMNS
    assert parse_comparison_hash("#a=bengaluru-fc&b=sc-delhi") == ("bengaluru-fc", "sc-delhi")
    assert parse_comparison_hash("") == (None, None)


def test_csv_formats_counts_and_expected_values(tmp_path):
    data = build_comparison_data([_bundle([
        {"match_id": 1, "team_id": 10, "side": "home", "event_type": "Miss",
         "credited_team_id": None, "xg": 0.543, "is_own_goal": False},
    ])])
    path = write_expected_table_csv(tmp_path / "expected.csv", data["table"], data["generated_at"])
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["Pts"] == "0"
    assert rows[0]["xGF"] == "0.54"
    assert rows[0]["xPts"] == "2.09"
