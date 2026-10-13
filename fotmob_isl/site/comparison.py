"""Precomputed, JSON-safe data for the offline comparison homepage."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from datetime import datetime, timezone
from pathlib import Path
import csv

import pandas as pd

from ..xg_model import match_xpts
from .data import MatchBundle
from .team_colors import TEAM_PALETTE, color_for

TABLE_COLUMNS = [
    "Pos", "Team", "P", "Pts", "xPts", "Pts-xPts", "GF", "xGF",
    "GA", "xGA", "GD", "xGD",
]


def _number(value, default=0.0) -> float:
    value = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(value) else float(value)


def _result(home_score: float, away_score: float) -> tuple[str, str]:
    if home_score > away_score:
        return "W", "L"
    if home_score < away_score:
        return "L", "W"
    return "D", "D"


def _stat(bundle: MatchBundle, side: str, keys: tuple[str, ...]) -> float:
    if "match_id" not in bundle.team_stats.columns:
        return 0.0
    for key in keys:
        value = bundle.stat(side, key)
        if pd.notna(value):
            return _number(value)
    return 0.0


def build_comparison_data(
    bundles: list[MatchBundle],
    logo_paths: dict[str, str] | None = None,
) -> dict:
    logo_paths = logo_paths or {}
    teams: dict[str, dict] = {}
    matches: list[dict] = []
    pair_matches: defaultdict[str, list[dict]] = defaultdict(list)

    def team_record(name: str) -> dict:
        if name not in teams:
            palette = color_for(name)
            teams[name] = {
                "name": name, "slug": _slug(name), "logo": logo_paths.get(name),
                "color": palette["color"], "on_color": palette["on_color"],
                "matches": 0, "wins": 0, "draws": 0, "losses": 0,
                "points": 0.0, "xpoints": 0.0, "gf": 0.0, "xgf": 0.0,
                "ga": 0.0, "xga": 0.0, "shots": 0.0, "possession": 0.0,
                "fouls": 0.0, "yellows": 0.0, "form": [],
            }
        return teams[name]

    for name in TEAM_PALETTE:
        team_record(name)
    for bundle in bundles:
        home_score = _number(bundle.match.get("home_score"))
        away_score = _number(bundle.match.get("away_score"))
        if pd.isna(pd.to_numeric(bundle.match.get("home_score"), errors="coerce")):
            continue
        home, away = bundle.home_name, bundle.away_name
        home_team, away_team = team_record(home), team_record(away)
        shots = bundle.shots[bundle.shots["match_id"].astype(str) == bundle.match_id].to_dict("records")
        xpts = match_xpts(shots, bundle.match.get("home_team_id"), bundle.match.get("away_team_id"))
        home_id, away_id = str(bundle.match.get("home_team_id")), str(bundle.match.get("away_team_id"))
        home_xg = sum(_number(row.get("xg")) for row in shots if row.get("team_id") and not bool(row.get("is_own_goal")) and str(row.get("team_id")) == home_id)
        away_xg = sum(_number(row.get("xg")) for row in shots if row.get("team_id") and not bool(row.get("is_own_goal")) and str(row.get("team_id")) == away_id)
        goal_rows = [row for row in shots if str(row.get("event_type", "")).lower() == "goal"]
        home_goals = sum(str(row.get("credited_team_id")) == home_id for row in goal_rows)
        away_goals = sum(str(row.get("credited_team_id")) == away_id for row in goal_rows)
        if not goal_rows:
            home_goals, away_goals = home_score, away_score
        home_result, away_result = _result(home_score, away_score)
        for record, side, result, gf, ga, xgf, xga in (
            (home_team, "home", home_result, home_goals, away_goals, home_xg, away_xg),
            (away_team, "away", away_result, away_goals, home_goals, away_xg, home_xg),
        ):
            record["matches"] += 1
            record["wins"] += result == "W"
            record["draws"] += result == "D"
            record["losses"] += result == "L"
            record["points"] += 3 if result == "W" else 1 if result == "D" else 0
            record["xpoints"] += xpts[side]
            record["gf"] += gf
            record["xgf"] += xgf
            record["ga"] += ga
            record["xga"] += xga
            record["shots"] += len(bundle.shots_for(side))
            record["possession"] += _stat(bundle, side, ("BallPossesion", "possession"))
            record["fouls"] += _stat(bundle, side, ("fouls",))
            record["yellows"] += _stat(bundle, side, ("yellow_cards",))
            record["form"].append({"result": result, "xgd": round(xgf - xga, 3)})
        row = {
            "id": bundle.match_id, "date": str(bundle.match.get("match_date_utc") or ""),
            "home": home, "away": away, "home_score": home_score, "away_score": away_score,
            "home_xg": round(home_xg, 3), "away_xg": round(away_xg, 3),
            "home_result": home_result, "away_result": away_result,
        }
        matches.append(row)
        pair_matches["|".join(sorted((home, away)))].append(row)

    for record in teams.values():
        record["possession"] = record["possession"] / record["matches"] if record["matches"] else 0
        record["form"] = record["form"][-5:]
        record["gd"] = record["gf"] - record["ga"]
        record["xgd"] = record["xgf"] - record["xga"]
        record["points"] = round(record["points"], 3)
        record["xpoints"] = round(record["xpoints"], 3)
        record["points_delta"] = round(record["points"] - record["xpoints"], 3)
        for key in ("gf", "xgf", "ga", "xga", "gd", "xgd", "shots", "fouls", "yellows"):
            record[key] = round(record[key], 3)

    for first, second in combinations(sorted(teams), 2):
        pair_matches.setdefault("|".join((first, second)), [])

    expected = sorted(teams.values(), key=lambda row: (-row["xpoints"], -row["xgd"], -row["xgf"], row["name"]))
    actual = sorted(teams.values(), key=lambda row: (-row["points"], -row["gd"], -row["gf"], row["name"]))
    actual_rank = {row["name"]: index for index, row in enumerate(actual, 1)}
    table = []
    for index, row in enumerate(expected, 1):
        table.append({
            "Pos": index, "Team": row["name"], "P": row["matches"], "Pts": row["points"],
            "xPts": row["xpoints"], "Pts-xPts": row["points_delta"], "GF": row["gf"],
            "xGF": row["xgf"], "GA": row["ga"], "xGA": row["xga"], "GD": row["gd"], "xGD": row["xgd"],
            "actual_rank": actual_rank[row["name"]],
        })
    latest = max(matches, key=lambda row: row["date"]) if matches else None
    return {
        "teams": teams, "table": table, "matches": sorted(matches, key=lambda row: row["date"], reverse=True),
        "head_to_head": dict(pair_matches), "latest": latest,
        "table_columns": TABLE_COLUMNS, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_expected_table_csv(path: Path, table: list[dict], generated_at: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLE_COLUMNS)
        writer.writeheader()
        writer.writerows({column: row[column] for column in TABLE_COLUMNS} for row in table)
    return path


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "team"


expected_table = build_comparison_data


def parse_comparison_hash(value: str) -> tuple[str | None, str | None]:
    """Parse the shareable #a=club-slug&b=club-slug form without browser APIs."""
    values = {}
    for part in value.lstrip("#").split("&"):
        if "=" in part:
            key, item = part.split("=", 1)
            if key in {"a", "b"}:
                values[key] = item
    return values.get("a"), values.get("b")
