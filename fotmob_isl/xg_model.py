"""Small, dependency-free match outcome model based on shot-level xG."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite


def goal_distribution(xgs: Iterable[float]) -> list[float]:
    """Return P(0), P(1), ... for independent Bernoulli shot probabilities."""
    distribution = [1.0]
    for value in xgs:
        try:
            probability = float(value)
        except (TypeError, ValueError):
            continue
        if not isfinite(probability):
            continue
        probability = min(1.0, max(0.0, probability))
        next_distribution = [0.0] * (len(distribution) + 1)
        for goals, chance in enumerate(distribution):
            next_distribution[goals] += chance * (1.0 - probability)
            next_distribution[goals + 1] += chance * probability
        distribution = next_distribution
    return distribution


def _outcome_probabilities(home: list[float], away: list[float]) -> dict[str, float]:
    home_distribution = goal_distribution(home)
    away_distribution = goal_distribution(away)
    home_win = draw = away_win = 0.0
    for home_goals, home_chance in enumerate(home_distribution):
        for away_goals, away_chance in enumerate(away_distribution):
            chance = home_chance * away_chance
            if home_goals > away_goals:
                home_win += chance
            elif home_goals == away_goals:
                draw += chance
            else:
                away_win += chance
    total = home_win + draw + away_win
    return {
        "home_win": home_win / total,
        "draw": draw / total,
        "away_win": away_win / total,
    }


def fair_result(
    shots: Iterable[Mapping[str, object]],
    home_team_id: object,
    away_team_id: object,
) -> dict[str, float | str]:
    """Calculate exact result probabilities, excluding own goals without xG."""
    home_id, away_id = str(home_team_id), str(away_team_id)
    home, away = [], []
    for shot in shots:
        if bool(shot.get("is_own_goal")):
            continue
        try:
            xg = float(shot.get("xg"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not isfinite(xg):
            continue
        team_id = str(shot.get("team_id", ""))
        if team_id == home_id:
            home.append(xg)
        elif team_id == away_id:
            away.append(xg)
    return _outcome_probabilities(home, away)


def match_xpts(
    shots: Iterable[Mapping[str, object]],
    home_team_id: object,
    away_team_id: object,
) -> dict[str, float]:
    """Return expected points (3*win probability + draw probability) per side."""
    result = fair_result(shots, home_team_id, away_team_id)
    return {
        "home": 3.0 * float(result["home_win"]) + float(result["draw"]),
        "away": 3.0 * float(result["away_win"]) + float(result["draw"]),
    }


xpts_for_match = match_xpts


def verdict(probability: float) -> str:
    if probability >= 0.45:
        return "Fair result"
    if probability >= 0.20:
        return "Could've gone either way"
    return "Robbery"


# Descriptive aliases keep the small model convenient for callers and tests.
poisson_binomial = goal_distribution
calculate_outcome_probabilities = fair_result
