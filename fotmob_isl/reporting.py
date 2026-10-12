from __future__ import annotations

from pathlib import Path

import pandas as pd


def _as_float(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value):
    f = _as_float(value)
    if f is None:
        return None
    return int(f)


def _bool_like(value):
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def _fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _stat_value(frame: pd.DataFrame, side: str, stat_key: str, period: str = "All") -> float | None:
    if frame.empty:
        return None
    subset = frame[(frame["side"] == side) & (frame["period"] == period) & (frame["stat_key"] == stat_key)]
    if subset.empty:
        return None
    return _as_float(subset.iloc[0].get("value_num"))


def _safe_name(frame: pd.DataFrame, team_id: str | int | None, default: str = "Unknown") -> str:
    if team_id is None:
        return default
    team_id = str(team_id)
    subset = frame[frame["team_id"].astype(str) == team_id]
    if subset.empty:
        return default
    return str(subset.iloc[0].get("team_name") or default)


def build_match_report(match_row: dict, team_rows: pd.DataFrame, shots: pd.DataFrame, players: pd.DataFrame) -> str:
    match_id = str(match_row.get("match_id", "unknown"))
    home_name = str(match_row.get("home_team_name") or "Home")
    away_name = str(match_row.get("away_team_name") or "Away")
    home_score = _as_int(match_row.get("home_score")) or 0
    away_score = _as_int(match_row.get("away_score")) or 0
    venue = match_row.get("venue_name") or "Unknown venue"
    weather = match_row.get("weather_description") or "N/A"
    referee = match_row.get("referee_name") or "Unknown"

    home_team_rows = team_rows[(team_rows["match_id"].astype(str) == match_id) & (team_rows["side"] == "home") & (team_rows["period"] == "All")].copy()
    away_team_rows = team_rows[(team_rows["match_id"].astype(str) == match_id) & (team_rows["side"] == "away") & (team_rows["period"] == "All")].copy()

    home_xg = _stat_value(home_team_rows, "home", "expected_goals")
    away_xg = _stat_value(away_team_rows, "away", "expected_goals")
    home_shots = shots[(shots["match_id"].astype(str) == match_id) & (shots["side"] == "home")]
    away_shots = shots[(shots["match_id"].astype(str) == match_id) & (shots["side"] == "away")]
    home_on_target = int((home_shots["is_on_target"].map(_bool_like)).sum()) if not home_shots.empty else 0
    away_on_target = int((away_shots["is_on_target"].map(_bool_like)).sum()) if not away_shots.empty else 0

    scoreline = f"{home_name} {home_score} - {away_score} {away_name}"
    summary = (
        f"{scoreline}\n"
        f"Venue: {venue} | Referee: {referee} | Weather: {weather}\n"
        f"Expected goals: {home_name} {_fmt(home_xg)} - {_fmt(away_xg)} {away_name}"
    )

    score_rows = shots[shots["match_id"].astype(str) == match_id]
    goals = score_rows[score_rows["event_type"].fillna("").str.lower().eq("goal")].copy()
    goal_bullets = []
    if goals.empty:
        goal_bullets.append("No goals recorded in the shot map.")
    else:
        for _, row in goals.iterrows():
            team_name = _safe_name(players, row.get("team_id"), row.get("team_id") or "Unknown team")
            player_name = row.get("player_name") or "Unknown player"
            goal_bullets.append(f"- {player_name} ({team_name})")

    home_passing = _stat_value(home_team_rows, "home", "accurate_passes")
    away_passing = _stat_value(away_team_rows, "away", "accurate_passes")
    home_possession = _stat_value(home_team_rows, "home", "possession")
    away_possession = _stat_value(away_team_rows, "away", "possession")

    report = f"# Match report: {match_id}\n\n"
    report += f"## {scoreline}\n\n"
    report += f"{summary}\n\n"
    report += "## Match snapshot\n\n"
    report += "| Team | Score | xG | Shots | On target | Possession | Accurate passes |\n"
    report += "| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    report += f"| {home_name} | {home_score} | {_fmt(home_xg)} | {len(home_shots)} | {home_on_target} | {_fmt(home_possession)} | {_fmt(home_passing)} |\n"
    report += f"| {away_name} | {away_score} | {_fmt(away_xg)} | {len(away_shots)} | {away_on_target} | {_fmt(away_possession)} | {_fmt(away_passing)} |\n\n"
    report += "## Key events\n\n"
    for item in goal_bullets:
        report += f"{item}\n"
    report += "\n"
    report += "## Tactical read\n\n"
    report += (
        "- Use the team-level and shot-level rows together to explain the game: expected goals show the quality of chances, while the shot map reveals where the match turned.\n"
        "- Cross-check passing volume, possession and shot output to identify whether a result was driven by efficiency or a structural edge.\n"
        "- Player-level rows can be used to highlight the most influential performers, for example the top xG creators or the goalkeeper workload.\n"
    )
    return report.strip() + "\n"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=object)


def write_match_reports(data_dir: Path, output_dir: Path, match_ids: list[int] | None = None) -> list[Path]:
    matches = _read_csv(data_dir / "matches.csv")
    if matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")

    team_rows = _read_csv(data_dir / "team_match_stats.csv")
    shots = _read_csv(data_dir / "shots.csv")
    players = _read_csv(data_dir / "player_match_stats.csv")

    if match_ids is None:
        match_ids = [int(x) for x in matches["match_id"].dropna().astype(str)]
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for match_id in match_ids:
        match_row = matches[matches["match_id"].astype(str) == str(match_id)]
        if match_row.empty:
            continue
        report = build_match_report(match_row.iloc[0].to_dict(), team_rows, shots, players)
        path = output_dir / f"{match_id}.md"
        path.write_text(report, encoding="utf-8")
        paths.append(path)
    return paths
