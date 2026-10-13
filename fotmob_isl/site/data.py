from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ..data import LoadedData, load_data
from .team_colors import color_for

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class MatchBundle:
    match: dict
    team_stats: pd.DataFrame
    shots: pd.DataFrame
    players: pd.DataFrame
    home_name: str
    away_name: str
    home_color: str
    away_color: str
    home_on_color: str
    away_on_color: str

    @property
    def match_id(self) -> str:
        return str(self.match["match_id"])

    def stat(self, side: str, key: str | tuple[str, ...]):
        keys = (key,) if isinstance(key, str) else key
        rows = self.team_stats[
            (self.team_stats["match_id"].astype(str) == self.match_id)
            & (self.team_stats["side"] == side)
            & (self.team_stats["period"] == "All")
            & (self.team_stats["stat_key"].isin(keys))
        ]
        return rows.iloc[0]["value_num"] if not rows.empty else None

    def shots_for(self, side: str) -> pd.DataFrame:
        shots = self.shots[self.shots["match_id"].astype(str) == self.match_id]
        return shots[(shots["side"] == side) & ~shots["is_own_goal"]]

    def team_rows(self, side: str) -> pd.DataFrame:
        return self.team_stats[
            (self.team_stats["match_id"].astype(str) == self.match_id)
            & (self.team_stats["side"] == side)
            & (self.team_stats["period"] == "All")
        ]

    def scorers(self, side: str) -> list[dict]:
        return [goal for goal in self.goals() if goal["side"] == side]

    def tape(self) -> list[dict]:
        groups = {
            "Attack": ("expected_goals", "total_shots", "ShotsOnTarget", "touches_opp_box"),
            "Passing": ("accurate_passes", "passes", "accurate_crosses"),
            "Defending": ("matchstats.headers.tackles", "interceptions", "clearances", "keeper_saves"),
            "Discipline": ("fouls", "yellow_cards", "red_cards"),
        }
        titles = {str(row.stat_key): str(row.stat_title) for _, row in self.team_stats.iterrows()}
        result = []
        for group, keys in groups.items():
            for key in keys:
                home, away = self.stat("home", key), self.stat("away", key)
                if pd.isna(home) and pd.isna(away):
                    continue
                result.append({"group": group, "title": titles.get(key, key), "home": home, "away": away})
        return result

    def referee(self) -> dict:
        match = self.match
        def clean(value):
            value = pd.to_numeric(value, errors="coerce")
            return None if pd.isna(value) else value
        def total(key):
            values = [pd.to_numeric(self.stat(side, key), errors="coerce") for side in ("home", "away")]
            return sum(value for value in values if pd.notna(value)) or None
        fouls, yellow, red = total("fouls"), total("yellow_cards"), total("red_cards")
        return {"name": match.get("referee_name"), "fouls": fouls, "yellow": yellow, "red": red,
                "fouls_avg": match.get("referee_fouls_per_match"),
                "yellow_avg": match.get("referee_yellow_per_match"),
                "red_avg": clean(pd.to_numeric(match.get("referee_red_total"), errors="coerce")
                            / pd.to_numeric(match.get("referee_matches"), errors="coerce")),
                "fouls_league": match.get("referee_fouls_league_avg"),
                "yellow_league": match.get("referee_yellow_league_avg"),
                "cards_per_foul": (yellow + red) / fouls if fouls and yellow is not None and red is not None else None}

    def poll(self) -> dict | None:
        values = {key: pd.to_numeric(self.match.get(key), errors="coerce")
                  for key in ("fan_vote_home", "fan_vote_draw", "fan_vote_away")}
        return values if all(pd.notna(value) for value in values.values()) else None

    def goals(self) -> list[dict]:
        shots = self.shots[self.shots["match_id"].astype(str) == self.match_id]
        goals = shots[shots["event_type"].fillna("").str.lower().eq("goal")]
        home_id = str(self.match.get("home_team_id", ""))
        away_id = str(self.match.get("away_team_id", ""))
        result = []
        for _, row in goals.iterrows():
            credited_id = str(row.get("credited_team_id", ""))
            side = "home" if credited_id == home_id else "away" if credited_id == away_id else row.get("side", "")
            team_name = self.home_name if side == "home" else self.away_name
            label = str(row.get("player_name") or "Unknown player")
            if bool(row.get("is_own_goal")):
                label += " (own goal)"
            result.append({
                "minute": row.get("minute"),
                "label": label,
                "team_name": team_name,
                "side": side,
            })
        return result

    def kickoff_ist(self) -> str:
        raw = self.match.get("match_date_utc")
        if not raw:
            return "Kickoff unavailable"
        value = pd.to_datetime(raw, utc=True).to_pydatetime().astimezone(IST)
        return value.strftime("%a %-d %b %Y · %H:%M IST")

    def score(self, side: str) -> str:
        value = self.match.get("home_score" if side == "home" else "away_score")
        return "—" if pd.isna(value) else str(int(value))


def build_match_bundle(loaded: LoadedData, match: dict, colors: dict[str, str]) -> MatchBundle:
    home = str(match.get("home_team_name") or "Home")
    away = str(match.get("away_team_name") or "Away")
    home_palette, away_palette = color_for(home), color_for(away)
    return MatchBundle(
        match=match,
        team_stats=loaded.team_stats,
        shots=loaded.shots,
        players=loaded.players,
        home_name=home,
        away_name=away,
        home_color=home_palette["color"],
        away_color=away_palette["color"],
        home_on_color=home_palette["on_color"],
        away_on_color=away_palette["on_color"],
    )


def load_match_bundles(data_dir: Path, colors: dict[str, str]) -> list[MatchBundle]:
    loaded = load_data(data_dir)
    if loaded.matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")
    return [
        build_match_bundle(loaded, row, colors)
        for row in loaded.matches.to_dict("records")
    ]
