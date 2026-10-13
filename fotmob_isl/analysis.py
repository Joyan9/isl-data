"""Cached Groq insight generation for match reports."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from .data import load_data
from .stat_keys import BALL_POSSESSION, EXPECTED_GOALS, TOTAL_SHOTS


def _normalise(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _match_context(match: dict, team_rows: pd.DataFrame, shots: pd.DataFrame,
                   players: pd.DataFrame) -> dict[str, Any]:
    match_id = str(match["match_id"])
    team = team_rows[
        (team_rows["match_id"].astype(str) == match_id)
        & (team_rows["period"] == "All")
    ]
    shot = shots[shots["match_id"].astype(str) == match_id]
    if "is_own_goal" not in shot:
        shot = shot.assign(is_own_goal=False)
    if "is_on_target" not in shot:
        shot = shot.assign(is_on_target=False)
    player = players[players["match_id"].astype(str) == match_id]
    valid_shots = shot[~shot["is_own_goal"]]
    home_id = str(match.get("home_team_id", ""))
    away_id = str(match.get("away_team_id", ""))

    def credited_side(row: pd.Series) -> str:
        credited_id = str(row.get("credited_team_id", ""))
        return "home" if credited_id == home_id else "away" if credited_id == away_id else str(row.get("side", ""))
    selected_match = {
        key: _normalise(match.get(key))
        for key in (
            "match_id", "round", "match_date_utc", "home_team_name", "away_team_name",
            "home_score", "away_score", "venue_name", "referee_name",
        )
    }
    stats: dict[str, dict[str, Any]] = {}
    for side in ("home", "away"):
        side_rows = team[team["side"] == side]
        stats[side] = {
            str(row["stat_key"]): _normalise(row["value_num"])
            for _, row in side_rows.iterrows()
            if pd.notna(row.get("stat_key"))
        }

    shot_summary = {}
    for side in ("home", "away"):
        side_shots = valid_shots[valid_shots["side"] == side]
        shot_summary[side] = {
            "shots": int(len(side_shots)),
            "on_target": int(side_shots["is_on_target"].sum()) if not side_shots.empty else 0,
            "goals": int(sum(credited_side(row) == side for _, row in shot[shot["event_type"].fillna("").str.lower().eq("goal")].iterrows())),
            "xg": round(pd.to_numeric(side_shots.get("xg"), errors="coerce").sum(), 3),
            "xgot": round(pd.to_numeric(side_shots.get("xgot"), errors="coerce").sum(), 3),
        }

    important = {
        "minutes_played", "goals", "assists", EXPECTED_GOALS, "expected_assists",
        TOTAL_SHOTS, "saves", "goals_prevented", "rating_title",
    }
    player_summary = []
    if not player.empty:
        relevant = player[player["stat_key"].isin(important)]
        for (team_id, player_id, player_name), group in relevant.groupby(
            ["team_id", "player_id", "player_name"], dropna=False
        ):
            values = {
                str(row["stat_key"]): _normalise(row["value_num"])
                for _, row in group.iterrows()
            }
            if any(values.get(key) not in (None, "", 0, "0", 0.0) for key in important - {"minutes_played"}):
                player_summary.append({
                    "team_id": _normalise(team_id),
                    "player_id": _normalise(player_id),
                    "player_name": _normalise(player_name),
                    "stats": values,
                })
    player_summary.sort(
        key=lambda row: sum(
            (
                float(value) * multiplier
                if pd.notna(value) else 0
            )
            for key, multiplier in (
                (EXPECTED_GOALS, 1), ("expected_assists", 1), ("goals", 2)
            )
            for value in [pd.to_numeric(row["stats"].get(key), errors="coerce")]
        ),
        reverse=True,
    )
    return {
        "match": selected_match,
        "team_stats_all_period": stats,
        "shot_summary": shot_summary,
        "goals": [
            {
                "minute": _normalise(row.get("minute")),
                "player_name": _normalise(row.get("player_name")),
                "side": credited_side(row),
                "is_own_goal": bool(row.get("is_own_goal")),
            }
            for _, row in shot[shot["event_type"].fillna("").str.lower().eq("goal")].iterrows()
        ],
        "facts": _facts(match, stats, shot_summary, shot, home_id, away_id),
        "players": player_summary[:12],
    }


def _facts(match: dict, stats: dict[str, dict[str, Any]], shot_summary: dict[str, dict[str, Any]],
           shots: pd.DataFrame, home_id: str, away_id: str) -> list[str]:
    home = match.get("home_team_name") or "Home"
    away = match.get("away_team_name") or "Away"
    def fact_value(value: Any) -> str:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number) and float(number).is_integer():
            return str(int(number))
        return str(value)

    facts = [
        f"Final score: {home} {match.get('home_score', 0)}-{match.get('away_score', 0)} {away}.",
        f"Expected goals: {home} {stats['home'].get(EXPECTED_GOALS, 'n/a')}; {away} {stats['away'].get(EXPECTED_GOALS, 'n/a')}.",
        f"Shots excluding own goals: {home} {shot_summary['home']['shots']}; {away} {shot_summary['away']['shots']}.",
        f"Possession: {home} {fact_value(stats['home'].get(BALL_POSSESSION, 'n/a'))}%; {away} {fact_value(stats['away'].get(BALL_POSSESSION, 'n/a'))}%.",
    ]
    for _, row in shots[shots["event_type"].fillna("").str.lower().eq("goal")].iterrows():
        credited = str(row.get("credited_team_id", ""))
        team = home if credited == home_id else away if credited == away_id else row.get("side", "unknown")
        suffix = " (own goal)" if bool(row.get("is_own_goal")) else ""
        facts.append(f"Goal: {row.get('player_name', 'Unknown player')}{suffix} credited to {team}.")
    return facts


def context_hash(context: dict[str, Any]) -> str:
    payload = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _insight_path(insights_dir: Path, match_id: str) -> Path:
    return insights_dir / f"{match_id}.json"


def _load_cached(path: Path, source_hash: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if cached.get("status") == "ok" and cached.get("source_hash") == source_hash:
        return cached
    return None


def _response_text(response: Any) -> str:
    if getattr(response, "status", "completed") != "completed":
        raise ValueError(f"Groq response status was {getattr(response, 'status', None)!r}")
    if getattr(response, "incomplete_details", None):
        raise ValueError(f"Groq response was incomplete: {response.incomplete_details}")
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        lines = []
        for line in text.splitlines():
            cleaned = re.sub(r"[*_]", "", line.strip())
            if cleaned:
                lines.append(cleaned)
        while lines and lines[-1].rstrip()[-1:] not in ".!?":
            lines.pop()
        if not lines:
            raise ValueError("Groq response contained no complete insight bullets")
        return "\n".join(lines)
    raise ValueError("Groq response did not contain output_text")


def _prompt(context: dict[str, Any]) -> str:
    return (
        "You are writing a short, entertaining football fan analysis for an Indian Super League "
        "match. Write for someone who enjoys football but does not know advanced analytics. "
        "Explain xG as the quality of chances, not as a prediction. Use only the supplied FotMob "
        "data. Do not invent events, tactics, players, or causal claims. The supplied facts list "
        "is the source of truth: do not say that any fact or data is missing. Return 3 to 5 "
        "plain-text bullet points, each beginning with '- '. "
        "Do not use a heading, markdown table, or long preamble. Focus on surprising and easy-to-"
        "understand comparisons between result, chances, shots, possession, passing, and players.\n\n"
        "Match context JSON:\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )


def _request_insight(client: OpenAI, model: str, context: dict[str, Any]) -> str:
    response = client.responses.create(
        model=model, input=_prompt(context), max_output_tokens=1500
    )
    return _response_text(response)


def generate_insights(data_dir: Path, insights_dir: Path, max_calls: int = 3,
                      model: str = "openai/gpt-oss-20b", delay_seconds: float = 2.0,
                      force: bool = False) -> dict[str, int]:
    """Generate at most max_calls new insights, never spending a call on a valid cache."""
    load_dotenv()
    loaded = load_data(data_dir)
    matches = loaded.matches
    if matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")
    team_rows, shots, players = loaded.team_stats, loaded.shots, loaded.players
    if team_rows.empty:
        team_rows = pd.DataFrame(columns=["match_id", "side", "period", "stat_key", "value_num"])
    if shots.empty:
        shots = pd.DataFrame(columns=["match_id", "side", "event_type", "player_name", "team_id", "is_on_target"])
    if players.empty:
        players = pd.DataFrame(columns=["match_id", "team_id", "team_name"])
    insights_dir.mkdir(parents=True, exist_ok=True)

    stats = {"cached": 0, "generated": 0, "skipped_budget": 0, "failed": 0}
    pending: list[tuple[dict, dict[str, Any], str, Path]] = []
    for match in matches.to_dict("records"):
        match_id = str(match["match_id"])
        context = _match_context(match, team_rows, shots, players)
        source_hash = context_hash(context)
        path = _insight_path(insights_dir, match_id)
        if not force and _load_cached(path, source_hash):
            stats["cached"] += 1
            continue
        pending.append((match, context, source_hash, path))

    if max_calls < 0:
        raise ValueError("max_calls must be non-negative")
    api_key = os.environ.get("GROQ_API_KEY")
    if pending and max_calls and not api_key:
        raise RuntimeError("GROQ_API_KEY is required to generate new insights")
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1") if api_key else None

    for index, (match, context, source_hash, path) in enumerate(pending):
        if index >= max_calls:
            stats["skipped_budget"] += 1
            continue
        match_id = str(match["match_id"])
        try:
            assert client is not None
            text = _request_insight(client, model, context)
        except Exception as exc:
            stats["failed"] += 1
            print(f"{match_id}: GROQ request failed ({type(exc).__name__}: {exc})")
            failure = {
                "match_id": match_id,
                "status": "failed",
                "source_hash": source_hash,
                "error": f"{type(exc).__name__}: {exc}",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
            continue
        result = {
            "match_id": match_id,
            "status": "ok",
            "model": model,
            "source_hash": source_hash,
            "insights": text,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        stats["generated"] += 1
        if delay_seconds and index + 1 < min(max_calls, len(pending)):
            time.sleep(delay_seconds)
    return stats
