import pandas as pd

from fotmob_isl.reporting import build_match_report


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
