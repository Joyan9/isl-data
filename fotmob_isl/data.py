"""Shared typed loading for the four extracted CSV tables."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


NUMERIC_COLUMNS = {
    "match_id", "league_id", "league_season_id", "home_team_id", "away_team_id",
    "team_id", "player_id", "shot_id", "credited_team_id", "referee_id",
    "home_score", "away_score", "value_num", "value_pct", "value_total",
    "minute", "minute_added", "x", "y", "xg", "xgot", "blocked_x", "blocked_y",
    "goal_crossed_y", "goal_crossed_z", "on_goal_x", "on_goal_y",
}
BOOL_COLUMNS = {"is_on_target", "is_blocked", "is_own_goal", "is_from_inside_box"}


@dataclass(frozen=True)
class LoadedData:
    matches: pd.DataFrame
    team_stats: pd.DataFrame
    shots: pd.DataFrame
    players: pd.DataFrame


def _convert(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in NUMERIC_COLUMNS.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in {
        "match_id", "league_id", "league_season_id", "home_team_id", "away_team_id",
        "team_id", "player_id", "shot_id", "credited_team_id", "referee_id",
    }.intersection(frame.columns):
        frame[column] = frame[column].astype("Int64")
    for column in BOOL_COLUMNS.intersection(frame.columns):
        frame[column] = frame[column].map(
            lambda value: str(value).strip().lower() in {"1", "true", "yes", "y", "t"}
            if pd.notna(value) else False
        )
    return frame


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return _convert(pd.read_csv(path, dtype=object))


def load_data(data_dir: Path) -> LoadedData:
    """Read and normalize all four extracted tables exactly once."""
    return LoadedData(
        matches=_read(data_dir / "matches.csv"),
        team_stats=_read(data_dir / "team_match_stats.csv"),
        shots=_read(data_dir / "shots.csv"),
        players=_read(data_dir / "player_match_stats.csv"),
    )
