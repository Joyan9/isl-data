from __future__ import annotations

from html import escape


def _number(value):
    try:
        value = float(value)
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _text(value, suffix=""):
    value = _number(value)
    return "—" if value is None else f"{int(value) if value.is_integer() else value:g}{suffix}"


def split_bar(home, away, home_name, away_name, home_color, away_color):
    h, a = _number(home), _number(away)
    if h is None or a is None or h + a <= 0:
        return ""
    hp = h / (h + a) * 100
    return (f"<div class='split-bar interactive-mark' data-tooltip='{escape(home_name)} {_text(h,'%')} ({hp:.1f}% share) · "
            f"{escape(away_name)} {_text(a,'%')} ({100-hp:.1f}% share)' role='img' aria-label='Possession: {escape(home_name)} {_text(h,'%')}, "
            f"{escape(away_name)} {_text(a,'%')}'><span class='split-home' style='width:{hp:.2f}%;background:{escape(home_color)}'></span>"
            f"<span class='split-away' style='width:{100-hp:.2f}%;background:{escape(away_color)}'></span></div>"
            f"<div class='split-labels'><span>{escape(home_name)} {_text(h,'%')}</span><span>{escape(away_name)} {_text(a,'%')}</span></div>")


def tape_bar(title, home, away, home_name, away_name, home_color, away_color):
    h, a = _number(home), _number(away)
    if h is None and a is None:
        return ""
    h, a = h or 0, a or 0
    total = h + a
    hp = h / total * 100 if total else 50
    return (f"<div class='tape-row interactive-mark' data-tooltip='{escape(title)}: {escape(home_name)} {_text(h)} ({hp:.1f}% share), "
            f"{escape(away_name)} {_text(a)} ({100-hp:.1f}% share)'><span>{escape(title)}</span><strong>{_text(h)}</strong>"
            f"<div class='tape-track' role='img' aria-label='{escape(title)}: {escape(home_name)} {_text(h)}, "
            f"{escape(away_name)} {_text(a)}'><i style='width:{hp:.2f}%;background:{escape(home_color)}'></i>"
            f"<i style='width:{100-hp:.2f}%;background:{escape(away_color)}'></i></div><strong>{_text(a)}</strong></div>")


def xg_race(shots, home_name, away_name, home_color, away_color, home_on_color="#000000", away_on_color="#000000"):
    valid = shots.copy()
    valid["minute_value"] = valid["minute"].fillna(0) + valid["minute_added"].fillna(0) / 10
    max_minute = max(float(valid["minute_value"].max() or 90), 90)
    width, height = 640, 260
    lines, goals = [], []
    for side, name, color in (("home", home_name, home_color), ("away", away_name, away_color)):
        rows = valid[valid["side"] == side].sort_values("minute_value")
        total = 0.0
        series = [(0.0, 0.0)]
        points = [(0, height - 24)]
        for _, row in rows.iterrows():
            minute = float(row["minute_value"])
            x = minute / max_minute * (width - 40) + 20
            points.append((x, height - 24 - total / 3 * (height - 48)))
            xg = _number(row.get("xg")) or 0
            total += xg
            series.append((minute, total))
            points.append((x, height - 24 - total / 3 * (height - 48)))
            if str(row.get("event_type", "")).lower() == "goal":
                credited_side = side
                if bool(row.get("is_own_goal")):
                    credited_side = "away" if side == "home" else "home"
                goals.append({"minute": minute, "x": x, "y": points[-1][1], "side": credited_side,
                              "name": str(row.get("player_name") or "Goal"),
                              "own": bool(row.get("is_own_goal"))})
        dash = "" if side == "home" else " stroke-dasharray='8 5'"
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        area_text = f"20,{height - 24} {point_text} {width - 20},{height - 24}"
        lines.append(f"<polygon data-team='{side}' points='{area_text}' fill='{escape(color)}' opacity='.12'/>"
                     f"<polyline data-team='{side}' data-series='{' '.join(f'{minute:.1f}:{value:.3f}' for minute, value in series)}' fill='none' stroke='{escape(color)}' stroke-width='3'{dash} points='{point_text}'/>"
                     f"<text data-team='{side}' x='{width - 18}' y='{points[-1][1] - 5:.1f}' text-anchor='end' fill='{escape(color)}' font-size='12'>{escape(name)} {total:.2f}</text>")
    goals.sort(key=lambda goal: goal["minute"])
    lanes = []
    for goal in goals:
        lane = 0
        while any(abs(goal["minute"] - previous["minute"]) < 6 and previous["lane"] == lane for previous in lanes):
            lane += 1
        goal["lane"] = lane
        lanes.append(goal)
    pills = []
    for goal in goals:
        side = goal["side"]
        color = home_color if side == "home" else away_color
        on_color = home_on_color if side == "home" else away_on_color
        surname = goal["name"].split()[-1]
        label = f"⚽ {int(goal['minute'])}' {surname}"
        detail = f"{label}{' OG' if goal['own'] else ''}"
        pills.append(
            f"<button class='goal-pill lane-{goal['lane']}' data-tooltip='{escape(detail)}' "
            f"style='left:{goal['x'] / width * 100:.2f}%;--pill:{escape(color)};--pill-on:{escape(on_color)}'>"
            f"{escape(label)}{' <b>OG</b>' if goal['own'] else ''}</button>"
        )
    event_data = "".join(
        f"<circle data-team='{goal['side']}' data-minute='{goal['minute']:.1f}' data-value='{escape(goal['name'])}' "
        f"cx='{goal['x']:.1f}' cy='{goal['y']:.1f}' r='5' fill='{escape(home_color if goal['side'] == 'home' else away_color)}'/>"
        for goal in goals
    )
    return (f"<div class='chart xg-chart'><h3>xG race</h3><div class='goal-strip'>{''.join(pills)}</div>"
            f"<svg class='xg-race' viewBox='0 0 {width} {height}' role='img' tabindex='0' aria-label='Interactive cumulative expected goals by minute'>"
            f"<title>Cumulative expected goals by minute</title><desc>{escape(home_name)} and {escape(away_name)} chance quality over time.</desc>"
            f"<line x1='20' y1='130' x2='620' y2='130' stroke='currentColor' opacity='.2'/><line x1='320' y1='20' x2='320' y2='236' stroke='currentColor' stroke-dasharray='4 4' opacity='.45'/>"
            f"{''.join(lines)}{event_data}<line class='xg-crosshair' x1='20' x2='20' y1='20' y2='236' stroke='currentColor' opacity='.7' hidden='hidden'/></svg>"
            f"<div class='xg-readout' aria-live='polite'>Hover or use arrow keys for minute-by-minute xG.</div>"
            f"<div class='legend'><button type='button' data-team-toggle='home' aria-pressed='true' style='color:{escape(home_color)}'>● {escape(home_name)}</button> "
            f"<button type='button' data-team-toggle='away' aria-pressed='true' style='color:{escape(away_color)}'>● {escape(away_name)}</button> · dashed line: away · marker: half-time</div></div>")
