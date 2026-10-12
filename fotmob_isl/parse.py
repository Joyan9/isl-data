"""Pure functions: FotMob matchDetails JSON -> rows for the three output tables.

Everything is looked up by key/title, never by list position, and every block is optional
(matches without xG coverage simply produce no shot / player rows).
"""
from __future__ import annotations

import re
from typing import Any

TEAM_STATS_COLS = [
    "match_id", "league_season_id", "round", "match_date_utc", "period", "team_id",
    "team_name", "side", "group_key", "stat_key", "stat_title", "value_num", "value_pct",
    "value_raw",
]
TEAM_STATS_PK = ["match_id", "period", "side", "group_key", "stat_key"]

SHOT_COLS = [
    "match_id", "shot_id", "team_id", "side", "player_id", "player_name", "minute",
    "minute_added", "period", "event_type", "situation", "shot_type", "x", "y",
    "is_on_target", "is_blocked", "is_own_goal", "is_from_inside_box", "xg", "xgot",
    "credited_team_id", "blocked_x", "blocked_y", "goal_crossed_y", "goal_crossed_z",
    "on_goal_x", "on_goal_y", "keeper_id",
]
SHOT_PK = ["match_id", "shot_id"]

PLAYER_STATS_COLS = [
    "match_id", "player_id", "player_name", "team_id", "team_name", "is_goalkeeper",
    "shirt_number", "usual_position", "group_key", "group_title", "stat_key", "stat_title",
    "value_num", "value_total", "value_type",
]
PLAYER_STATS_PK = ["match_id", "player_id", "group_key", "stat_key"]

_PCT = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*\((\d+(?:\.\d+)?)%\)\s*$")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _num(x: Any) -> int | float:
    f = float(x)
    return int(f) if f.is_integer() else f


def parse_stat_value(raw: Any) -> tuple[int | float | None, int | float | None, str | None]:
    """'512 (88%)' -> (512, 88, raw); '2.97' -> (2.97, None, raw); 64 -> (64, None, '64')."""
    if raw is None:
        return None, None, None
    if isinstance(raw, (bool, int, float)):
        return _num(raw), None, str(raw)
    s = str(raw)
    m = _PCT.match(s)
    if m:
        return _num(m.group(1)), _num(m.group(2)), s
    try:
        return _num(s), None, s
    except ValueError:
        return None, None, s


def match_meta(md: dict) -> dict:
    g = md["general"]
    return {
        "match_id": int(g["matchId"]),
        "league_id": g.get("parentLeagueId"),
        "league_season_id": g.get("leagueId"),
        "round": g.get("leagueRoundName") or g.get("matchRound"),
        "match_date_utc": g.get("matchTimeUTCDate"),
        "finished": bool(g.get("finished")),
        "home": g["homeTeam"],
        "away": g["awayTeam"],
    }


def parse_team_stats(md: dict) -> list[dict]:
    meta = match_meta(md)
    periods = (((md.get("content") or {}).get("stats")) or {}).get("Periods") or {}
    rows: list[dict] = []
    for period, block in periods.items():
        for group in block.get("stats") or []:
            for stat in group.get("stats") or []:
                if stat.get("type") == "title":
                    continue
                values = stat.get("stats") or [None, None]
                for side, raw in zip(("home", "away"), values):
                    if raw is None:
                        continue
                    team = meta[side]
                    num, pct, raw_s = parse_stat_value(raw)
                    rows.append({
                        "match_id": meta["match_id"],
                        "league_season_id": meta["league_season_id"],
                        "round": meta["round"],
                        "match_date_utc": meta["match_date_utc"],
                        "period": period,
                        "team_id": team["id"],
                        "team_name": team["name"],
                        "side": side,
                        "group_key": group.get("key"),
                        "stat_key": stat.get("key") or _slug(stat.get("title") or ""),
                        "stat_title": stat.get("title"),
                        "value_num": num,
                        "value_pct": pct,
                        "value_raw": raw_s,
                    })
    return rows


def parse_shots(md: dict) -> list[dict]:
    """One row per shot. Own goals: team_id is the team of the player who scored it, xg/xgot
    are null, and credited_team_id is the *other* team (the one the goal counts for)."""
    meta = match_meta(md)
    home, away = meta["home"]["id"], meta["away"]["id"]
    side_of = {home: "home", away: "away"}
    other = {home: away, away: home}
    shots = (((md.get("content") or {}).get("shotmap")) or {}).get("shots") or []
    rows = []
    for s in shots:
        team_id = s.get("teamId")
        own_goal = bool(s.get("isOwnGoal"))
        credited = None
        if s.get("eventType") == "Goal":
            credited = other.get(team_id) if own_goal else team_id
        on_goal = s.get("onGoalShot") or {}
        rows.append({
            "match_id": meta["match_id"],
            "shot_id": s.get("id"),
            "team_id": team_id,
            "side": side_of.get(team_id),
            "player_id": s.get("playerId"),
            "player_name": s.get("playerName"),
            "minute": s.get("min"),
            "minute_added": s.get("minAdded"),
            "period": s.get("period"),
            "event_type": s.get("eventType"),
            "situation": s.get("situation"),
            "shot_type": s.get("shotType"),
            "x": s.get("x"),
            "y": s.get("y"),
            "is_on_target": s.get("isOnTarget"),
            "is_blocked": s.get("isBlocked"),
            "is_own_goal": own_goal,
            "is_from_inside_box": s.get("isFromInsideBox"),
            "xg": s.get("expectedGoals"),
            "xgot": s.get("expectedGoalsOnTarget"),
            "credited_team_id": credited,
            "blocked_x": s.get("blockedX"),
            "blocked_y": s.get("blockedY"),
            "goal_crossed_y": s.get("goalCrossedY"),
            "goal_crossed_z": s.get("goalCrossedZ"),
            "on_goal_x": on_goal.get("x"),
            "on_goal_y": on_goal.get("y"),
            "keeper_id": s.get("keeperId"),
        })
    return rows


def parse_player_stats(md: dict) -> list[dict]:
    """Long format: one row per player x stat. Players with no stats (unused subs) are skipped."""
    meta = match_meta(md)
    team_names = {meta["home"]["id"]: meta["home"]["name"], meta["away"]["id"]: meta["away"]["name"]}
    players = ((md.get("content") or {}).get("playerStats")) or {}
    rows = []
    for pid, p in players.items():
        for group in p.get("stats") or []:
            for title, entry in (group.get("stats") or {}).items():
                stat = entry.get("stat") or {}
                value = stat.get("value")
                if isinstance(value, bool):
                    value = int(value)
                rows.append({
                    "match_id": meta["match_id"],
                    "player_id": p.get("id") or int(pid),
                    "player_name": p.get("name"),
                    "team_id": p.get("teamId"),
                    "team_name": team_names.get(p.get("teamId"), p.get("teamName")),
                    "is_goalkeeper": p.get("isGoalkeeper"),
                    "shirt_number": p.get("shirtNumber"),
                    "usual_position": p.get("usualPosition"),
                    "group_key": group.get("key"),
                    "group_title": group.get("title"),
                    "stat_key": entry.get("key") or _slug(title),
                    "stat_title": title,
                    "value_num": value,
                    "value_total": stat.get("total"),
                    "value_type": stat.get("type"),
                })
    return rows


# ----------------------------------------------------------------------------------------------
# matches.csv: one row per match (venue, referee, weather, insights, fan vote)
# ----------------------------------------------------------------------------------------------
import json  # noqa: E402

MATCH_COLS = [
    "match_id", "league_season_id", "round", "match_date_utc",
    "home_team_id", "home_team_name", "home_score", "away_team_id", "away_team_name", "away_score",
    "venue_name", "venue_city", "venue_country", "venue_capacity", "venue_surface",
    "venue_lat", "venue_long", "attendance",
    "referee_id", "referee_name", "referee_country", "referee_matches",
    "referee_yellow_per_match", "referee_yellow_total", "referee_yellow_league_avg",
    "referee_fouls_per_match", "referee_fouls_total", "referee_fouls_league_avg",
    "referee_red_total", "referee_penalties_total",
    "weather_temp_c", "weather_description", "weather_humidity", "weather_wind_speed",
    "weather_wind_dir", "weather_precipitation", "weather_updated_utc",
    "insights_json", "fan_vote_home", "fan_vote_draw", "fan_vote_away", "fetched_at_utc",
]
MATCH_PK = ["match_id"]


def _fan_vote(vote: dict | None) -> tuple[int | None, int | None, int | None]:
    for poll in (vote or {}).get("Votes") or []:
        if poll.get("Name") == "1x2" and len(poll.get("Votes") or []) == 3:
            h, d, a = poll["Votes"]
            return h, d, a
    return None, None, None


def parse_match_row(md: dict) -> dict:
    """Referee numbers are FotMob's running totals *as of the fetch* (see fetched_at_utc), not as of
    kick-off. For rigorous referee comparisons, build baselines from this repo's own per-match data."""
    meta = match_meta(md)
    content = md.get("content") or {}
    facts = content.get("matchFacts") or {}
    info = facts.get("infoBox") or {}
    stadium = info.get("Stadium") or {}
    ref = info.get("Referee") or {}
    weather = content.get("weather") or {}
    pipeline = md.get("_pipeline") or {}

    scores = {t.get("id"): t.get("score") for t in (md.get("header") or {}).get("teams") or []}
    ref_stats = {}
    for st in ref.get("stats") or []:
        ref_stats[(st.get("type"), st.get("valueType"))] = st

    def per_match(kind: str, field: str):
        return (ref_stats.get((kind, "perMatch")) or {}).get(field)

    def total(kind: str):
        st = ref_stats.get((kind, "total"))
        return st.get("value") if st else None

    insights = [{"team_id": i.get("teamId"), "text": i.get("text")}
                for i in facts.get("insights") or []]
    vh, vd, va = _fan_vote(pipeline.get("vote"))
    attendance = info.get("Attendance")
    if isinstance(attendance, dict):
        attendance = attendance.get("value") or attendance.get("attendance")

    return {
        "match_id": meta["match_id"],
        "league_season_id": meta["league_season_id"],
        "round": meta["round"],
        "match_date_utc": meta["match_date_utc"],
        "home_team_id": meta["home"]["id"], "home_team_name": meta["home"]["name"],
        "home_score": scores.get(meta["home"]["id"]),
        "away_team_id": meta["away"]["id"], "away_team_name": meta["away"]["name"],
        "away_score": scores.get(meta["away"]["id"]),
        "venue_name": stadium.get("name"), "venue_city": stadium.get("city"),
        "venue_country": stadium.get("country"), "venue_capacity": stadium.get("capacity"),
        "venue_surface": stadium.get("surface"),
        "venue_lat": stadium.get("lat"), "venue_long": stadium.get("long"),
        "attendance": attendance,
        "referee_id": ref.get("id"), "referee_name": ref.get("text"),
        "referee_country": ref.get("country"), "referee_matches": total("matches"),
        "referee_yellow_per_match": per_match("yellowCards", "value"),
        "referee_yellow_total": per_match("yellowCards", "total"),
        "referee_yellow_league_avg": per_match("yellowCards", "average"),
        "referee_fouls_per_match": per_match("fouls", "value"),
        "referee_fouls_total": per_match("fouls", "total"),
        "referee_fouls_league_avg": per_match("fouls", "average"),
        "referee_red_total": total("redCards"), "referee_penalties_total": total("penalties"),
        "weather_temp_c": weather.get("temperature"),
        "weather_description": weather.get("description"),
        "weather_humidity": weather.get("relativeHumidity"),
        "weather_wind_speed": weather.get("windSpeed"),
        "weather_wind_dir": weather.get("windDirectionCardinal"),
        "weather_precipitation": weather.get("precipitation"),
        "weather_updated_utc": weather.get("lastUpdated"),
        "insights_json": json.dumps(insights, ensure_ascii=False) if insights else None,
        "fan_vote_home": vh, "fan_vote_draw": vd, "fan_vote_away": va,
        "fetched_at_utc": pipeline.get("fetched_at"),
    }


def parse_fixtures(props: dict) -> list[dict]:
    """League page pageProps -> [{match_id, finished, cancelled, utc_time, home, away}]."""
    out = []
    for m in ((props.get("fixtures") or {}).get("allMatches")) or []:
        st = m.get("status") or {}
        out.append({
            "match_id": int(m["id"]),
            "finished": bool(st.get("finished")),
            "cancelled": bool(st.get("cancelled")),
            "utc_time": st.get("utcTime"),
            "home": (m.get("home") or {}).get("name"),
            "away": (m.get("away") or {}).get("name"),
        })
    return out
