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
    team = team_rows[
        (team_rows["match_id"].astype(str) == match_id)
        & (team_rows["period"] == "All")
    ]
    shot = shots[shots["match_id"].astype(str) == match_id]
    player = players[players["match_id"].astype(str) == match_id]
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
        side_shots = shot[shot["side"] == side]
        shot_summary[side] = {
            "shots": int(len(side_shots)),
            "on_target": int(side_shots["is_on_target"].map(_as_bool).sum()) if not side_shots.empty else 0,
            "goals": int(side_shots["event_type"].fillna("").str.lower().eq("goal").sum()) if not side_shots.empty else 0,
            "xg": round(_sum_numeric(side_shots.get("xg")), 3),
            "xgot": round(_sum_numeric(side_shots.get("xgot")), 3),
        }

    important = {
        "minutes_played", "goals", "assists", "expected_goals", "expected_assists",
        "total_shots", "saves", "goals_prevented", "rating_title",
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
        key=lambda row: _as_number(row["stats"].get("expected_goals"))
        + _as_number(row["stats"].get("expected_assists"))
        + _as_number(row["stats"].get("goals")) * 2,
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
                "side": _normalise(row.get("side")),
                "is_own_goal": _normalise(row.get("is_own_goal")),
            }
            for _, row in shot[shot["event_type"].fillna("").str.lower().eq("goal")].iterrows()
        ],
        "players": player_summary[:12],
    }


def _as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _sum_numeric(values: Any) -> float:
    if values is None:
        return 0.0
    return sum(_as_number(value) for value in values)


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
        "match. Write for someone who enjoys football but does not know advanced analytics. "
        "Explain xG as the quality of chances, not as a prediction. Use only the supplied FotMob "
        "data. Do not invent events, tactics, players, or causal claims. Mention uncertainty "
        "when data is incomplete. Return 3 to 5 plain-text bullet points, each beginning with '- '. "
        "Do not use a heading, markdown table, or long preamble. Focus on surprising and easy-to-"
        "understand comparisons between result, chances, shots, possession, passing, and players.\n\n"
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


def _escape(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value if value is not None else "")
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _display(value: Any, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value in ("", "n/a"):
        return "—"
    number = _as_number(value)
    shown = str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
    return shown + suffix


def _stat(rows: pd.DataFrame, side: str, key: str) -> Any:
    found = rows[
        (rows["side"] == side)
        & (rows["period"] == "All")
        & (rows["stat_key"] == key)
    ]
    return found.iloc[0]["value_num"] if not found.empty else None


def _chart(label: str, home: Any, away: Any, home_name: str, away_name: str,
           suffix: str = "") -> str:
    def width(value: Any, maximum: float) -> int:
        try:
            return max(4, min(100, int(float(value) / maximum * 100)))
        except (TypeError, ValueError):
            return 4
    maximum = max(_as_number(home), _as_number(away), 1)
    return (
        f"<div class='chart'><div class='chart-title'>{_escape(label)}</div>"
        f"<div class='bar-row'><span class='team-label'>{_escape(home_name)}</span>"
        f"<span class='track'><span class='bar home' style='width:{width(home, maximum)}%'></span></span>"
        f"<strong>{_escape(_display(home, suffix))}</strong></div>"
        f"<div class='bar-row'><span class='team-label'>{_escape(away_name)}</span>"
        f"<span class='track'><span class='bar away' style='width:{width(away, maximum)}%'></span></span>"
        f"<strong>{_escape(_display(away, suffix))}</strong></div></div>"
    )


def _render_insights(text: str) -> str:
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower() == "insights":
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        bullets.append(f"<li>{_escape(line)}</li>")
    if not bullets:
        return "<p class='muted'>Insights are not available for this match yet.</p>"
    return "<ul class='insight-list'>" + "".join(bullets) + "</ul>"


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
        cached = _load_cached(_insight_path(insights_dir, match_id), context_hash(context))
        insight = cached.get("insights", "") if cached else ""
        home_score = _display(match.get("home_score"))
        away_score = _display(match.get("away_score"))
        home_xg = _stat(rows, "home", "expected_goals")
        away_xg = _stat(rows, "away", "expected_goals")
        home_possession = _stat(rows, "home", "BallPossesion")
        away_possession = _stat(rows, "away", "BallPossesion")
        home_shots = _stat(rows, "home", "total_shots")
        away_shots = _stat(rows, "away", "total_shots")
        home_passes = _stat(rows, "home", "accurate_passes")
        away_passes = _stat(rows, "away", "accurate_passes")
        match_date = match.get("match_date_utc") or ""
        venue = match.get("venue_name") or "Venue not available"
        charts = "".join((
            _chart("Chance quality (xG)", home_xg, away_xg, home, away),
            _chart("Shots", home_shots, away_shots, home, away),
            _chart("Ball possession", home_possession, away_possession, home, away, "%"),
            _chart("Accurate passes", home_passes, away_passes, home, away),
        ))
        page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_escape(home)} v {_escape(away)} | ISL Fan Reports</title>
<style>
:root{{--ink:#172033;--muted:#687386;--paper:#fff;--bg:#eef2f7;--blue:#2563eb;--red:#e11d48;--gold:#f59e0b}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#eef2ff,#f8fafc 55%,#fff7ed);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}}main{{max-width:980px;margin:auto;padding:22px 16px 56px}}a{{color:var(--blue);text-decoration:none;font-weight:650}}.back{{display:inline-block;margin-bottom:18px}}.hero{{background:linear-gradient(120deg,#111827,#253b75);color:#fff;border-radius:24px;padding:30px 26px;box-shadow:0 18px 45px #17203325}}.eyebrow{{color:#bfdbfe;text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:800}}h1{{font-size:clamp(28px,5vw,52px);line-height:1.05;margin:12px 0}}.score{{font-size:42px;font-weight:850;letter-spacing:.04em}}.meta{{color:#dbeafe;margin-top:12px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:18px 0}}.card,.panel{{background:var(--paper);border-radius:18px;padding:20px;box-shadow:0 8px 28px #17203312}}.card-label,.chart-title{{color:var(--muted);font-size:13px;font-weight:750;text-transform:uppercase;letter-spacing:.06em}}.metric{{font-size:29px;font-weight:850;margin-top:5px}}.section-title{{font-size:24px;margin:34px 0 12px}}.chart{{padding:16px 0;border-bottom:1px solid #e5e7eb}}.bar-row{{display:grid;grid-template-columns:minmax(90px,1fr) minmax(110px,3fr) 45px;gap:10px;align-items:center;margin-top:12px;font-size:14px}}.team-label{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.track{{background:#e5e7eb;height:12px;border-radius:20px;overflow:hidden}}.bar{{display:block;height:100%;border-radius:20px}}.home{{background:linear-gradient(90deg,#60a5fa,var(--blue))}}.away{{background:linear-gradient(90deg,#fb7185,var(--red))}}.insights{{border-left:5px solid var(--gold)}}.insight-list{{padding-left:22px;margin-bottom:0}}.insight-list li{{margin:10px 0}}.muted{{color:var(--muted)}}.explain{{color:var(--muted);font-size:14px;margin-top:0}}
</style></head><body><main><a class="back" href="../index.html">← All matches</a>
<section class="hero"><div class="eyebrow">Indian Super League · Match { _escape(match_id) }</div><h1>{_escape(home)} <span>vs</span> {_escape(away)}</h1><div class="score">{_escape(home_score)} <span>–</span> {_escape(away_score)}</div><div class="meta">{_escape(match_date)} · {_escape(venue)}</div></section>
<h2 class="section-title">The quick read</h2><div class="grid">
<div class="card"><div class="card-label">Chance quality</div><div class="metric">{_display(home_xg)} – {_display(away_xg)}</div><div class="explain">xG estimates how good the chances were.</div></div>
<div class="card"><div class="card-label">Shots</div><div class="metric">{_display(home_shots)} – {_display(away_shots)}</div><div class="explain">Total attempts by each team.</div></div>
<div class="card"><div class="card-label">Possession</div><div class="metric">{_display(home_possession, "%")} – {_display(away_possession, "%")}</div><div class="explain">Who had more of the ball.</div></div>
<div class="card"><div class="card-label">Accurate passes</div><div class="metric">{_display(home_passes)} – {_display(away_passes)}</div><div class="explain">Completed passes, not a quality score.</div></div></div>
<section class="panel"><h2 class="section-title">Match story in charts</h2>{charts}</section>
<section class="panel insights"><h2 class="section-title">AI fan insights</h2>{_render_insights(insight)}</section>
</main></body></html>"""
        (site_dir / f"{match_id}.html").write_text(page, encoding="utf-8")
        cards.append(f"<a class='match-card' href='{match_id}.html'><span class='date'>{_escape(match.get('match_date_utc') or '')}</span><strong>{_escape(home)}</strong><span class='result'>{_escape(home_score)} – {_escape(away_score)}</span><strong>{_escape(away)}</strong><span class='venue'>{_escape(venue)}</span></a>")
    index = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ISL Fan Reports</title><style>
body{{margin:0;background:linear-gradient(135deg,#111827,#253b75);color:#fff;font:16px system-ui}}main{{max-width:1000px;margin:auto;padding:48px 16px 70px}}h1{{font-size:clamp(38px,8vw,74px);line-height:1;margin:0 0 12px}}.intro{{color:#dbeafe;max-width:600px;margin-bottom:30px}}.matches{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:15px}}.match-card{{display:grid;gap:7px;background:#fff;color:#172033;border-radius:18px;padding:20px;box-shadow:0 14px 35px #0003;transition:transform .2s}}.match-card:hover{{transform:translateY(-4px)}}.date,.venue{{font-size:13px;color:#687386}}.result{{font-size:28px;font-weight:850;color:#2563eb}}</style></head><body><main><div>⚽ ISL FAN REPORTS</div><h1>Matches, made simple.</h1><p class="intro">Friendly match pages with the score, the story behind the numbers, and a few AI-assisted observations. Built for fans, not spreadsheets.</p><div class="matches">{"".join(cards)}</div></main></body></html>"""
    (site_dir / "index.html").write_text(index, encoding="utf-8")
    return len(cards)
