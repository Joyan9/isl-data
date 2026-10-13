import pandas as pd

from fotmob_isl import parse
from fotmob_isl.analysis import _match_context, _response_text
from fotmob_isl.data import load_data
from fotmob_isl.reporting import build_match_report
from types import SimpleNamespace
import gzip
import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "matchDetails_6361990.json.gz"


def _fixture_data(tmp_path):
    with gzip.open(FIXTURE, "rb") as handle:
        md = json.loads(handle.read())
    match = parse.parse_match_row(md)
    team = parse.parse_team_stats(md)
    shots = parse.parse_shots(md)
    players = parse.parse_player_stats(md)
    pd.DataFrame([match], columns=parse.MATCH_COLS).to_csv(tmp_path / "matches.csv", index=False)
    pd.DataFrame(team, columns=parse.TEAM_STATS_COLS).to_csv(
        tmp_path / "team_match_stats.csv", index=False
    )
    pd.DataFrame(shots, columns=parse.SHOT_COLS).to_csv(tmp_path / "shots.csv", index=False)
    pd.DataFrame(players, columns=parse.PLAYER_STATS_COLS).to_csv(
        tmp_path / "player_match_stats.csv", index=False
    )
    return match, load_data(tmp_path)


def test_build_match_report_handles_basic_match_summary():
    match_row = {
        "match_id": 123,
        "home_team_name": "Bengaluru FC",
        "away_team_name": "SC Delhi",
        "home_score": 2,
        "away_score": 1,
        "venue_name": "Sree Kanteerava Stadium",
        "weather_description": "Clear",
        "referee_name": "Test Ref",
    }
    team_rows = pd.DataFrame([
        {"match_id": 123, "side": "home", "period": "All", "stat_key": "expected_goals", "value_num": 1.8},
        {"match_id": 123, "side": "away", "period": "All", "stat_key": "expected_goals", "value_num": 0.9},
        {"match_id": 123, "side": "home", "period": "All", "stat_key": "accurate_passes", "value_num": 400},
        {"match_id": 123, "side": "away", "period": "All", "stat_key": "accurate_passes", "value_num": 330},
        {"match_id": 123, "side": "home", "period": "All", "stat_key": "possession", "value_num": 56},
        {"match_id": 123, "side": "away", "period": "All", "stat_key": "possession", "value_num": 44},
    ])
    shots = pd.DataFrame([
        {"match_id": 123, "side": "home", "event_type": "Goal", "player_name": "A. Player", "team_id": 1, "is_on_target": True},
        {"match_id": 123, "side": "home", "event_type": "Shot", "player_name": "B. Player", "team_id": 1, "is_on_target": False},
        {"match_id": 123, "side": "away", "event_type": "Goal", "player_name": "C. Player", "team_id": 2, "is_on_target": True},
    ])
    players = pd.DataFrame([
        {"team_id": 1, "team_name": "Bengaluru FC"},
        {"team_id": 2, "team_name": "SC Delhi"},
    ])

    report = build_match_report(match_row, team_rows, shots, players)

    assert "Bengaluru FC 2 - 1 SC Delhi" in report
    assert "Expected goals" in report
    assert "| Bengaluru FC | 2 | 1.8 | 2 | 1 | 56 | 400 |" in report
    assert "A. Player (Bengaluru FC)" in report


def test_fixture_reports_credited_goals_and_excludes_own_goal_from_shots(tmp_path):
    match, loaded = _fixture_data(tmp_path)
    goals = [row for row in loaded.shots.to_dict("records") if row["event_type"] == "Goal"]
    credited = [row["credited_team_id"] for row in goals]
    assert credited.count(match["home_team_id"]) == 3
    assert credited.count(match["away_team_id"]) == 2

    own_goal = next(row for row in goals if row["is_own_goal"])
    assert own_goal["player_name"] == "Menno Koch"
    assert own_goal["credited_team_id"] == match["away_team_id"]

    report = build_match_report(
        match, loaded.team_stats, loaded.shots, loaded.players
    )
    assert "Menno Koch (own goal) (SC Delhi)" in report
    assert "| Bengaluru FC | 3 | 2.97 | 27 |" in report
    assert "| SC Delhi | 2 | 1.85 | 10 |" in report
    assert "| Bengaluru FC | 3 | 2.97 | 27 |" in report
    assert "| SC Delhi | 2 | 1.85 | 10 |" in report


def test_fixture_context_has_truthful_facts(tmp_path):
    match, loaded = _fixture_data(tmp_path)
    context = _match_context(
        match, loaded.team_stats, loaded.shots, loaded.players
    )
    assert "Shots excluding own goals: Bengaluru FC 27; SC Delhi 10." in context["facts"]
    assert "Possession: Bengaluru FC 64%; SC Delhi 36%." in context["facts"]
    assert any("Goal: Menno Koch (own goal) credited to SC Delhi." == fact
               for fact in context["facts"])


def test_incomplete_groq_response_is_rejected_and_bullets_are_cleaned():
    response = SimpleNamespace(
        status="completed",
        incomplete_details=None,
        output_text="- **Good chance.**\n- This bullet is unfinished",
    )
    from fotmob_isl.analysis import _response_text
    assert _response_text(response) == "- Good chance."
    incomplete = SimpleNamespace(
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        output_text="- Never cache this.",
    )
    try:
        _response_text(incomplete)
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete response should fail")
