"""Cached Groq insights and static match-site generation."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from .reporting import build_match_report


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=object)


def _normalise(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _match_context(match: dict, team_rows: pd.DataFrame, shots: pd.DataFrame,
                   players: pd.DataFrame) -> dict[str, Any]:
    match_id = str(match["match_id"])
    team = team_rows[team_rows["match_id"].astype(str) == match_id]
    shot = shots[shots["match_id"].astype(str) == match_id]
    player = players[players["match_id"].astype(str) == match_id]
    return {
        "match": {key: _normalise(value) for key, value in match.items()},
        "team_stats": [{key: _normalise(value) for key, value in row.items()}
                       for row in team.to_dict("records")],
        "shots": [{key: _normalise(value) for key, value in row.items()}
                  for row in shot.to_dict("records")],
        "player_stats": [{key: _normalise(value) for key, value in row.items()}
                         for row in player.to_dict("records")],
    }


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
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise ValueError("Groq response did not contain output_text")


def _prompt(context: dict[str, Any]) -> str:
    return (
        "You are writing a short, entertaining football fan analysis for an Indian Super League "
        "match. Use only the supplied FotMob data. Do not invent events, tactics, players, or "
        "causal claims. Mention uncertainty when the data is incomplete. Return 3 to 5 concise "
        "bullet points under the heading 'Insights'. Focus on surprising or useful comparisons "
        "between result, xG, shots, possession, passing, and player contributions.\n\n"
        "Match context JSON:\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )


def _request_insight(client: OpenAI, model: str, context: dict[str, Any]) -> str:
    response = client.responses.create(model=model, input=_prompt(context))
    return _response_text(response)


def generate_insights(data_dir: Path, insights_dir: Path, max_calls: int = 3,
                      model: str = "openai/gpt-oss-20b", delay_seconds: float = 2.0,
                      force: bool = False) -> dict[str, int]:
    """Generate at most max_calls new insights, never spending a call on a valid cache."""
    load_dotenv()
    matches = _read_csv(data_dir / "matches.csv")
    if matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")
    team_rows = _read_csv(data_dir / "team_match_stats.csv")
    shots = _read_csv(data_dir / "shots.csv")
    players = _read_csv(data_dir / "player_match_stats.csv")
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


def _escape(value: Any) -> str:
    text = str(value if value is not None else "")
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _chart(label: str, home: Any, away: Any, home_name: str, away_name: str) -> str:
    def width(value: Any) -> int:
        try:
            return max(2, min(360, int(float(value) * 3.6)))
        except (TypeError, ValueError):
            return 2
    return (
        f"<div class='chart'><strong>{_escape(label)}</strong>"
        f"<div>{_escape(home_name)} <span class='bar home' style='width:{width(home)}px'></span> {_escape(home)}</div>"
        f"<div>{_escape(away_name)} <span class='bar away' style='width:{width(away)}px'></span> {_escape(away)}</div></div>"
    )


def build_site(data_dir: Path, insights_dir: Path, site_dir: Path) -> int:
    matches = _read_csv(data_dir / "matches.csv")
    if matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")
    team_rows = _read_csv(data_dir / "team_match_stats.csv")
    shots = _read_csv(data_dir / "shots.csv")
    players = _read_csv(data_dir / "player_match_stats.csv")
    if team_rows.empty:
        team_rows = pd.DataFrame(columns=["match_id", "side", "period", "stat_key", "value_num"])
    if shots.empty:
        shots = pd.DataFrame(columns=["match_id", "side", "event_type", "player_name", "team_id", "is_on_target"])
    if players.empty:
        players = pd.DataFrame(columns=["match_id", "team_id", "team_name"])
    site_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for match in matches.to_dict("records"):
        match_id = str(match["match_id"])
        context = _match_context(match, team_rows, shots, players)
        home = str(match.get("home_team_name") or "Home")
        away = str(match.get("away_team_name") or "Away")
        rows = team_rows[team_rows["match_id"].astype(str) == match_id]
        def stat(side: str, key: str) -> str:
            found = rows[(rows["side"] == side) & (rows["period"] == "All") & (rows["stat_key"] == key)]
            return str(found.iloc[0]["value_num"]) if not found.empty else "n/a"
        cached = _load_cached(_insight_path(insights_dir, match_id), context_hash(context))
        insight = cached.get("insights", "Insights are not available for this match yet.") if cached else "Insights are not available for this match yet."
        body = build_match_report(match, team_rows, shots, players)
        charts = "".join((
            _chart("Expected goals", stat("home", "expected_goals"), stat("away", "expected_goals"), home, away),
            _chart("Shots", stat("home", "total_shots"), stat("away", "total_shots"), home, away),
            _chart("Possession", stat("home", "BallPossesion"), stat("away", "BallPossesion"), home, away),
        ))
        page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{_escape(home)} v {_escape(away)}</title>
<style>body{{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;background:#f7f7f7;color:#222}}main{{background:white;padding:2rem;border-radius:12px}}pre{{white-space:pre-wrap}}.chart{{margin:1rem 0;line-height:2.2}}.bar{{display:inline-block;height:1rem;vertical-align:middle;border-radius:4px;margin:0 .5rem}}.home{{background:#2563eb}}.away{{background:#dc2626}}</style></head>
<body><main><a href="../index.html">All matches</a><pre>{_escape(body)}</pre><h2>AI fan insights</h2><p>{_escape(insight)}</p>{charts}</main></body></html>"""
        (site_dir / f"{match_id}.html").write_text(page, encoding="utf-8")
        cards.append(f"<li><a href='{match_id}.html'>{_escape(home)} { _escape(match.get('home_score', '')) } - { _escape(match.get('away_score', '')) } {_escape(away)}</a></li>")
    index = "<!doctype html><html><head><meta charset='utf-8'><title>ISL fan reports</title></head><body><h1>ISL fan reports</h1><ul>" + "".join(cards) + "</ul></body></html>"
    (site_dir / "index.html").write_text(index, encoding="utf-8")
    return len(cards)
