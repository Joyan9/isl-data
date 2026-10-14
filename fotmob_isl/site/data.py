from __future__ import annotations

from dataclasses import dataclass, field
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
    all_matches: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False, repr=False)

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
            values = [clean(self.stat(side, key)) for side in ("home", "away")]
            return sum(value for value in values if value is not None) if any(value is not None for value in values) else None

        def classify(observed, expected):
            if observed is None or expected is None:
                return None
            band = 1.28 * expected ** 0.5
            if observed < expected - band:
                return "fewer"
            if observed > expected + band:
                return "more"
            return "usual"

        fouls, yellow, red = total("fouls"), total("yellow_cards"), total("red_cards")
        fouls_avg = clean(match.get("referee_fouls_per_match"))
        yellow_avg = clean(match.get("referee_yellow_per_match"))
        league_fouls = clean(match.get("referee_fouls_league_avg"))
        league_yellow = clean(match.get("referee_yellow_league_avg"))
        cards_per_foul = yellow / fouls if fouls and yellow is not None else None
        referee_cards_per_foul = yellow_avg / fouls_avg if fouls_avg else None
        league_cards_per_foul = league_yellow / league_fouls if league_fouls else None
        whistle = classify(fouls, fouls_avg)
        pocket_expected = fouls * yellow_avg / fouls_avg if fouls and yellow_avg is not None and fouls_avg else None
        pocket = classify(yellow, pocket_expected)
        headline = {
            ("more", "more"): "Strict night", ("more", "usual"): "Busy whistle",
            ("more", "fewer"): "Lots of fouls, few cards", ("usual", "more"): "Card-happy night",
            ("usual", "usual"): "Business as usual", ("usual", "fewer"): "Cards stayed in the pocket",
            ("fewer", "more"): "Few fouls, quick to book", ("fewer", "usual"): "Whistle stayed quiet",
            ("fewer", "fewer"): "Let-it-flow night",
        }.get((whistle, pocket))
        stat_rows = [
            {"label": "Fouls", "match": fouls, "ref": fouls_avg, "league": league_fouls,
             "classification": whistle},
            {"label": "Yellow cards", "match": yellow, "ref": yellow_avg, "league": league_yellow,
             "classification": pocket},
            {"label": "Cards per foul", "match": cards_per_foul, "ref": referee_cards_per_foul,
             "league": league_cards_per_foul, "classification": classify(cards_per_foul, referee_cards_per_foul)},
        ]
        referee_id = str(match.get("referee_id")) if pd.notna(match.get("referee_id")) else None
        own_matches = pd.DataFrame()
        if referee_id and not self.all_matches.empty and "referee_id" in self.all_matches:
            own_matches = self.all_matches[
                self.all_matches["referee_id"].astype(str) == referee_id
            ]
        own_fouls = []
        for _, row in own_matches.iterrows():
            match_id = str(row.get("match_id"))
            stat_rows_for_match = self.team_stats[
                (self.team_stats["match_id"].astype(str) == match_id)
                & (self.team_stats["period"] == "All")
                & (self.team_stats["stat_key"] == "fouls")
            ]
            value = pd.to_numeric(stat_rows_for_match["value_num"], errors="coerce").sum() if not stat_rows_for_match.empty else None
            if value is not None and pd.notna(value):
                own_fouls.append(float(value))
        own_matches_count = len(own_fouls)
        return {
            "name": match.get("referee_name"), "matches": clean(match.get("referee_matches")),
            "fouls": fouls, "yellow": yellow, "red": red, "fouls_avg": fouls_avg,
            "yellow_avg": yellow_avg, "fouls_league": league_fouls, "yellow_league": league_yellow,
            "cards_per_foul": cards_per_foul, "referee_cards_per_foul": referee_cards_per_foul,
            "league_cards_per_foul": league_cards_per_foul,
            "whistle": whistle, "pocket": pocket, "headline": headline,
            "pocket_expected": pocket_expected,
            "rows": stat_rows,
            "teams": [{"name": self.home_name, "fouls": clean(self.stat("home", "fouls")),
                       "yellow": clean(self.stat("home", "yellow_cards"))},
                      {"name": self.away_name, "fouls": clean(self.stat("away", "fouls")),
                       "yellow": clean(self.stat("away", "yellow_cards"))}],
            "own_matches": own_matches_count,
            "own_fouls_avg": sum(own_fouls) / own_matches_count if own_matches_count >= 5 else None,
        }

    def poll(self) -> dict | None:
        values = {key: pd.to_numeric(self.match.get(key), errors="coerce")
                  for key in ("fan_vote_home", "fan_vote_draw", "fan_vote_away")}
        if not all(pd.notna(value) for value in values.values()):
            return None
        votes = [int(values[key]) for key in ("fan_vote_home", "fan_vote_draw", "fan_vote_away")]
        total = sum(votes)
        if total <= 0:
            return None
        exact = [vote * 100 / total for vote in votes]
        shares = [int(value) for value in exact]
        for index in sorted(range(3), key=lambda item: (-(exact[item] - shares[item]), item))[:100 - sum(shares)]:
            shares[index] += 1
        home_score = pd.to_numeric(self.match.get("home_score"), errors="coerce")
        away_score = pd.to_numeric(self.match.get("away_score"), errors="coerce")
        actual = (
            self.home_name if home_score > away_score else
            self.away_name if away_score > home_score else "Draw"
        )
        crowd_correct = (
            ("Home" if shares[0] >= max(shares) else "Draw" if shares[1] >= max(shares) else "Away")
            == ("Home" if actual == self.home_name else "Away" if actual == self.away_name else "Draw")
        )
        return {
            "home": shares[0], "draw": shares[1], "away": shares[2],
            "home_votes": votes[0], "draw_votes": votes[1], "away_votes": votes[2],
            "total": total, "actual": actual,
            "verdict": "The crowd called it" if crowd_correct else "The crowd got this one wrong",
        }

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
        all_matches=loaded.matches,
    )


def load_match_bundles(data_dir: Path, colors: dict[str, str]) -> list[MatchBundle]:
    loaded = load_data(data_dir)
    if loaded.matches.empty:
        raise FileNotFoundError(f"No data found in {data_dir / 'matches.csv'}")
    return [
        build_match_bundle(loaded, row, colors)
        for row in loaded.matches.to_dict("records")
    ]
