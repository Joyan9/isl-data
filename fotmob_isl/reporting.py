from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data import load_data
from .stat_keys import ACCURATE_PASSES, EXPECTED_GOALS, POSSESSION_KEYS


def _fmt(value):
    if value is None or pd.isna(value):
        return "n/a"
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(number) and float(number).is_integer():
        return str(int(number))
    return str(value)


def _stat_value(frame: pd.DataFrame, side: str, stat_key: str | tuple[str, ...],
                period: str = "All") -> float | None:
    if frame.empty:
        return None
    keys = (stat_key,) if isinstance(stat_key, str) else stat_key
    subset = frame[
        (frame["side"] == side)
        & (frame["period"] == period)
        & (frame["stat_key"].isin(keys))
    ]
    if subset.empty:
        return None
    value = pd.to_numeric(subset.iloc[0].get("value_num"), errors="coerce")
    return None if pd.isna(value) else float(value)


def _safe_name(frame: pd.DataFrame, team_id: str | int | None, default: str = "Unknown") -> str:
    if team_id is None:
        return default
    team_id = str(team_id)
    subset = frame[frame["team_id"].astype(str) == team_id]
    if subset.empty:
        return default
    return str(subset.iloc[0].get("team_name") or default)


def _credited_team(match_row: dict, row: pd.Series) -> tuple[str, str]:
    home_id = str(match_row.get("home_team_id", ""))
    away_id = str(match_row.get("away_team_id", ""))
    credited_id = str(row.get("credited_team_id", ""))
    if credited_id == home_id:
        return "home", str(match_row.get("home_team_name") or "Home")
    if credited_id == away_id:
        return "away", str(match_row.get("away_team_name") or "Away")
    return str(row.get("side") or "unknown"), ""


def build_match_report(match_row: dict, team_rows: pd.DataFrame, shots: pd.DataFrame, players: pd.DataFrame) -> str:
    match_id = str(match_row.get("match_id", "unknown"))
    home_name = str(match_row.get("home_team_name") or "Home")
    away_name = str(match_row.get("away_team_name") or "Away")
    home_score_value = pd.to_numeric(match_row.get("home_score"), errors="coerce")
    away_score_value = pd.to_numeric(match_row.get("away_score"), errors="coerce")
    home_score = int(home_score_value) if pd.notna(home_score_value) else 0
    away_score = int(away_score_value) if pd.notna(away_score_value) else 0
    venue = match_row.get("venue_name") or "Unknown venue"
    weather = match_row.get("weather_description") or "N/A"
    referee = match_row.get("referee_name") or "Unknown"

    home_team_rows = team_rows[(team_rows["match_id"].astype(str) == match_id) & (team_rows["side"] == "home") & (team_rows["period"] == "All")].copy()
    away_team_rows = team_rows[(team_rows["match_id"].astype(str) == match_id) & (team_rows["side"] == "away") & (team_rows["period"] == "All")].copy()

    home_xg = _stat_value(home_team_rows, "home", EXPECTED_GOALS)
    away_xg = _stat_value(away_team_rows, "away", EXPECTED_GOALS)
    match_shots = shots[shots["match_id"].astype(str) == match_id]
    if "is_own_goal" not in match_shots:
        match_shots = match_shots.assign(is_own_goal=False)
    if "is_on_target" not in match_shots:
        match_shots = match_shots.assign(is_on_target=False)
    valid_shots = match_shots[~match_shots["is_own_goal"]]
    home_shots = valid_shots[valid_shots["side"] == "home"]
    away_shots = valid_shots[valid_shots["side"] == "away"]
    home_on_target = int(home_shots["is_on_target"].sum()) if not home_shots.empty else 0
    away_on_target = int(away_shots["is_on_target"].sum()) if not away_shots.empty else 0

    scoreline = f"{home_name} {home_score} - {away_score} {away_name}"
    summary = (
        f"{scoreline}\n"
        f"Venue: {venue} | Referee: {referee} | Weather: {weather}\n"
        f"Expected goals: {home_name} {_fmt(home_xg)} - {_fmt(away_xg)} {away_name}"
    )

    score_rows = match_shots
    goals = score_rows[score_rows["event_type"].fillna("").str.lower().eq("goal")].copy()
    goal_bullets = []
    if goals.empty:
        goal_bullets.append("No goals recorded in the shot map.")
    else:
        for _, row in goals.iterrows():
            _, team_name = _credited_team(match_row, row)
            if not team_name:
                team_name = _safe_name(
                    players, row.get("credited_team_id") or row.get("team_id"), "Unknown team"
                )
            player_name = row.get("player_name") or "Unknown player"
            suffix = " (own goal)" if bool(row.get("is_own_goal")) else ""
            goal_bullets.append(f"- {player_name}{suffix} ({team_name})")

    home_passing = _stat_value(home_team_rows, "home", ACCURATE_PASSES)
    away_passing = _stat_value(away_team_rows, "away", ACCURATE_PASSES)
    home_possession = _stat_value(home_team_rows, "home", POSSESSION_KEYS)
    away_possession = _stat_value(away_team_rows, "away", POSSESSION_KEYS)

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


def write_match_reports(data_dir: Path, output_dir: Path, match_ids: list[int] | None = None) -> list[Path]:
    loaded = load_data(data_dir)
    matches = loaded.matches
    if matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")

    team_rows, shots, players = loaded.team_stats, loaded.shots, loaded.players

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
