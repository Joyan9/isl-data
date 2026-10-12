"""Sanity checks on a parsed match. Returns (errors, warnings); errors should block the load."""
from __future__ import annotations

from .parse import match_meta, parse_shots, parse_team_stats

XG_PARTS_TOL = 0.011   # displayed values are rounded to 2 dp
XG_SHOTS_TOL = 0.03    # team xG vs sum of shot-level xG (observed gap on the sample: 0.012)


def validate_match(md: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    meta = match_meta(md)
    team_rows = parse_team_stats(md)
    shots = parse_shots(md)

    if meta["finished"] and not team_rows:
        errors.append("finished match has no team stats")

    all_period = {(r["side"], r["stat_key"]): r["value_num"]
                  for r in team_rows if r["period"] == "All"}

    for side in ("home", "away"):
        total = all_period.get((side, "expected_goals"))
        if total is None:
            continue
        op = all_period.get((side, "expected_goals_open_play"))
        sp = all_period.get((side, "expected_goals_set_play"))
        if op is not None and sp is not None and abs(op + sp - total) > XG_PARTS_TOL:
            warnings.append(f"{side}: open play {op} + set play {sp} != total xG {total}")

        if shots:
            shot_sum = sum(s["xg"] or 0 for s in shots if s["side"] == side)
            if abs(shot_sum - total) > XG_SHOTS_TOL:
                warnings.append(f"{side}: shot-level xG {shot_sum:.3f} vs team xG {total}")
            xgot_total = all_period.get((side, "expected_goals_on_target"))
            if xgot_total is not None:
                xgot_sum = sum(s["xgot"] or 0 for s in shots if s["side"] == side)
                if abs(xgot_sum - xgot_total) > XG_SHOTS_TOL:
                    warnings.append(f"{side}: shot-level xGOT {xgot_sum:.3f} vs team {xgot_total}")
    return errors, warnings
