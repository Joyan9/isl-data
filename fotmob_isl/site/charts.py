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


def comparison_chart(label, home_name, away_name, home, away, home_color, away_color, suffix=""):
    return (f"<div class='chart' role='img' aria-label='{escape(label)}'><h3>{escape(label)}</h3>"
            f"{tape_bar(home_name, home, away, home_name, away_name, home_color, away_color)}"
            f"<span>{escape(_text(home, suffix))} – {escape(_text(away, suffix))}</span></div>")


def split_bar(home, away, home_name, away_name, home_color, away_color):
    h, a = _number(home), _number(away)
    if h is None or a is None or h + a <= 0:
        return ""
    hp = h / (h + a) * 100
    return (f"<div class='split-bar' role='img' aria-label='Possession: {escape(home_name)} {_text(h,'%')}, "
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
    return (f"<div class='tape-row'><span>{escape(title)}</span><strong>{_text(h)}</strong>"
            f"<div class='tape-track' role='img' aria-label='{escape(title)}: {escape(home_name)} {_text(h)}, "
            f"{escape(away_name)} {_text(a)}'><i style='width:{hp:.2f}%;background:{escape(home_color)}'></i>"
            f"<i style='width:{100-hp:.2f}%;background:{escape(away_color)}'></i></div><strong>{_text(a)}</strong></div>")


def xg_race(shots, home_name, away_name, home_color, away_color):
    valid = shots.copy()
    valid["minute_value"] = valid["minute"].fillna(0) + valid["minute_added"].fillna(0) / 10
    max_minute = max(float(valid["minute_value"].max() or 90), 90)
    width, height = 640, 260
    lines, markers = [], []
    for side, name, color in (("home", home_name, home_color), ("away", away_name, away_color)):
        rows = valid[valid["side"] == side].sort_values("minute_value")
        total = 0.0
        points = [(0, height - 24)]
        for _, row in rows.iterrows():
            minute = float(row["minute_value"])
            x = minute / max_minute * (width - 40) + 20
            points.append((x, height - 24 - total / 3 * (height - 48)))
            xg = _number(row.get("xg")) or 0
            total += xg
            points.append((x, height - 24 - total / 3 * (height - 48)))
            if str(row.get("event_type", "")).lower() == "goal":
                markers.append(f"<circle cx='{x:.1f}' cy='{points[-1][1]:.1f}' r='5' fill='{escape(color)}'><title>{escape(str(row.get('player_name') or 'Goal'))} {int(minute)}'</title></circle>")
        lines.append(f"<polyline fill='none' stroke='{escape(color)}' stroke-width='3' points='{' '.join(f'{x:.1f},{y:.1f}' for x,y in points)}'/>")
    return (f"<div class='chart'><h3>xG race</h3><svg class='xg-race' viewBox='0 0 {width} {height}' role='img'>"
            f"<title>Cumulative expected goals by minute</title><desc>{escape(home_name)} and {escape(away_name)} chance quality over time.</desc>"
            f"<line x1='20' y1='130' x2='620' y2='130' stroke='currentColor' opacity='.2'/><line x1='320' y1='20' x2='320' y2='236' stroke='currentColor' stroke-dasharray='4 4' opacity='.45'/>"
            f"{''.join(lines)}{''.join(markers)}</svg><div class='legend'><span style='color:{escape(home_color)}'>● {escape(home_name)}</span> <span style='color:{escape(away_color)}'>● {escape(away_name)}</span> · dashed line: half-time</div></div>")


def shot_map(shots, home_name, away_name, home_color, away_color):
    both_x = shots["x"].dropna()
    mirror = len(both_x) > 0 and both_x.mean() > 70
    points = []
    for _, row in shots.iterrows():
        x, y = _number(row.get("x")), _number(row.get("y"))
        if x is None or y is None:
            continue
        if mirror and row.get("side") == "away":
            x, y = 105 - x, 68 - y
        sx, sy = x / 105 * 100, y / 68 * 100
        radius = max(2, min(8, (_number(row.get("xg")) or .03) * 18))
        goal = str(row.get("event_type", "")).lower() == "goal" and not bool(row.get("is_own_goal"))
        color = home_color if row.get("side") == "home" else away_color
        minute = _text(row.get("minute"), "'")
        label = f"{row.get('player_name') or 'Shot'}, {minute}, xG {_text(row.get('xg'))}"
        points.append(f"<circle cx='{sx:.1f}' cy='{sy:.1f}' r='{radius:.1f}' fill='{escape(color) if goal else 'none'}' stroke='{escape(color)}' stroke-width='1.5'><title>{escape(label)}</title></circle>")
    return (f"<div class='shot-map'><h3>Shot map</h3><svg viewBox='0 0 100 68' role='img'><title>Shot map</title><desc>Shot locations, sized by expected goals.</desc>"
            "<rect x='1' y='1' width='98' height='66' fill='none' stroke='currentColor'/><line x1='50' y1='1' x2='50' y2='67' stroke='currentColor' opacity='.4'/><circle cx='50' cy='34' r='9' fill='none' stroke='currentColor' opacity='.4'/>"
            f"{''.join(points)}</svg><p class='legend'><span style='color:{escape(home_color)}'>● {escape(home_name)}</span> <span style='color:{escape(away_color)}'>● {escape(away_name)}</span></p></div>")
