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
    if valid.empty:
        valid = shots.copy()
    for column in ("minute", "minute_added", "xg"):
        if column not in valid:
            valid[column] = 0
    valid["minute_value"] = valid["minute"].fillna(0) + valid["minute_added"].fillna(0) / 10
    max_minute = max(float(valid["minute_value"].max() or 90), 90)
    max_minute = int(max_minute) if max_minute.is_integer() else max_minute
    width, height = 760, 380
    left, right, top, bottom = 48, 20, 80, 56
    plot_width, plot_height = width - left - right, height - top - bottom
    lines, goals = [], []
    series_by_side = {}
    max_xg = 0.0
    def cumulative_at(side, minute):
        rows = valid[(valid["side"] == side) & (valid["minute_value"] <= minute)]
        return sum(_number(value) or 0 for value in rows["xg"])
    for side, name, color in (("home", home_name, home_color), ("away", away_name, away_color)):
        rows = valid[valid["side"] == side].sort_values("minute_value")
        total = 0.0
        series = [(0.0, 0.0)]
        points = [(left, top + plot_height)]
        for _, row in rows.iterrows():
            minute = float(row["minute_value"])
            x = left + minute / max_minute * plot_width
            points.append((x, top + plot_height - total / 3 * plot_height))
            xg = _number(row.get("xg")) or 0
            total += xg
            max_xg = max(max_xg, total)
            series.append((minute, total))
            points.append((x, top + plot_height - total / 3 * plot_height))
            if str(row.get("event_type", "")).lower() == "goal":
                credited_side = side
                if bool(row.get("is_own_goal")):
                    credited_side = "away" if side == "home" else "home"
                goals.append({"minute": minute, "x": x, "side": credited_side,
                              "name": str(row.get("player_name") or "Goal"),
                              "own": bool(row.get("is_own_goal")),
                              "line_total": cumulative_at(credited_side, minute)})
        series_by_side[side] = (series, total)
    y_max = max(0.5, (int(max_xg / 0.5) + (max_xg % 0.5 > 0)) * 0.5)
    for side, name, color in (("home", home_name, home_color), ("away", away_name, away_color)):
        series, total = series_by_side[side]
        rows = valid[valid["side"] == side].sort_values("minute_value")
        points = [(left, top + plot_height)]
        current = 0.0
        for _, row in rows.iterrows():
            x = left + float(row["minute_value"]) / max_minute * plot_width
            points.append((x, top + plot_height - current / y_max * plot_height))
            current += _number(row.get("xg")) or 0
            points.append((x, top + plot_height - current / y_max * plot_height))
        dash = "" if side == "home" else " stroke-dasharray='8 5'"
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        area_text = f"{left},{top + plot_height} {point_text} {width - right},{top + plot_height}"
        lines.append(f"<polygon data-team='{side}' points='{area_text}' fill='{escape(color)}' opacity='.12'/>"
                     f"<polyline data-team='{side}' data-series='{' '.join(f'{minute:.1f}:{value:.3f}' for minute, value in series)}' fill='none' stroke='{escape(color)}' stroke-width='3'{dash} points='{point_text}'/>"
                     f"<text data-team='{side}' x='{width - right}' y='{max(top + 14, points[-1][1] - 5):.1f}' text-anchor='end' fill='{escape(color)}' font-size='12'>{escape(name)} {total:.2f}</text>")
    goals.sort(key=lambda goal: goal["minute"])
    lanes = []
    for goal in goals:
        lane = 0
        while any(abs(goal["minute"] - previous["minute"]) < 18 and previous["lane"] == lane for previous in lanes):
            lane += 1
        goal["lane"] = lane
        lanes.append(goal)
    pills = []
    for goal in goals:
        side = goal["side"]
        color = home_color if side == "home" else away_color
        on_color = home_on_color if side == "home" else away_on_color
        surname = goal["name"].split()[-1]
        label = f"{int(goal['minute'])}' {surname}"
        detail = f"{label}{' OG' if goal['own'] else ''}"
        # Use the credited team's cumulative line for own goals too.
        line_total = goal["line_total"]
        marker_y = top + plot_height - line_total / y_max * plot_height
        pill_x = goal["x"] + (goal["lane"] % 2 * 2 - 1) * min(34, goal["lane"] * 18)
        pill_x = max(left + 24, min(width - right - 24, pill_x))
        pill_y = 8 + goal["lane"] * 22
        pill_width = max(54, len(label) * 6.6 + (23 if goal["own"] else 12))
        edge_x = pill_x - pill_width / 2 if pill_x >= goal["x"] else pill_x + pill_width / 2
        goal["marker_y"], goal["pill_x"], goal["pill_y"], goal["edge_x"] = marker_y, pill_x, pill_y, edge_x
        pills.append(
            f"<g class='goal-event' data-goal='{len(pills)}' data-team='{side}' tabindex='0' data-tooltip='{escape(detail)}' aria-label='{escape(detail)}'>"
            f"<path class='goal-connector-halo' d='M {goal['x']:.1f} {marker_y:.1f} V {pill_y + 20:.1f} H {edge_x:.1f}'/>"
            f"<path class='goal-connector' d='M {goal['x']:.1f} {marker_y:.1f} V {pill_y + 20:.1f} H {edge_x:.1f}' stroke='{escape(color)}'/>"
            f"<circle class='goal-marker' data-tooltip='{escape(detail)}' cx='{goal['x']:.1f}' cy='{marker_y:.1f}' r='5' fill='{escape(color)}' stroke='#070b14' stroke-width='2'/>"
            f"<rect class='goal-pill' data-tooltip='{escape(detail)}' x='{pill_x - pill_width / 2:.1f}' y='{pill_y:.1f}' width='{pill_width:.1f}' height='20' rx='10' fill='{escape(color)}' stroke='{escape(color)}'/>"
            f"<text x='{pill_x:.1f}' y='{pill_y + 14:.1f}' text-anchor='middle' fill='{escape(on_color)}' font-size='11' font-weight='800'>{escape(label)}"
            f"{' OG' if goal['own'] else ''}</text></g>"
        )
    # Recalculate marker heights after all goals: goals are ordered and xG only changes on shots.
    # The line marker is supplied by the chart data; event markers remain at the credited line.
    event_data = "".join(
        f"<circle class='is-hidden' data-team='{goal['side']}' data-minute='{goal['minute']:.1f}' data-value='{escape(goal['name'])}' "
        f"cx='{goal['x']:.1f}' cy='{goal['marker_y']:.1f}' r='0'/>"
        for goal in goals
    )
    axes = []
    for tick in range(0, int(y_max * 2) + 1):
        value = tick / 2
        y = top + plot_height - value / y_max * plot_height
        axes.append(f"<line class='xg-grid' x1='{left}' x2='{width-right}' y1='{y:.1f}' y2='{y:.1f}'/><text x='{left-8}' y='{y+4:.1f}' text-anchor='end'>{value:g}</text>")
    x_ticks = [0, 15, 30, 45, 60, 75, 90]
    if max_minute > 90:
        x_ticks.append(max_minute)
    x_axis = "".join(
        f"<line class='xg-tick' x1='{left + tick / max_minute * plot_width:.1f}' x2='{left + tick / max_minute * plot_width:.1f}' y1='{top+plot_height}' y2='{top+plot_height+5}'/>"
        f"<text x='{left + tick / max_minute * plot_width:.1f}' y='{height-24}' text-anchor='middle'>{tick:g}</text>"
        for tick in x_ticks
    )
    ht_x = left + 45 / max_minute * plot_width
    return (f"<div class='chart xg-chart'><h3>xG race</h3>"
            f"<svg class='xg-race' data-max-minute='{max_minute}' viewBox='0 0 {width} {height}' role='img' tabindex='0' aria-label='Interactive cumulative expected goals by minute'>"
            f"<title>Cumulative expected goals by minute</title><desc>{escape(home_name)} and {escape(away_name)} chance quality over time.</desc>"
            f"<g class='xg-axes'>{''.join(axes)}{x_axis}<text class='xg-axis-label' x='12' y='{top + plot_height / 2}' transform='rotate(-90 12 {top + plot_height / 2})' text-anchor='middle'>Cumulative xG</text><text class='xg-axis-label' x='{ht_x}' y='{top-10}' text-anchor='middle'>HT</text></g>"
            f"<line class='xg-half-time' x1='{ht_x:.1f}' x2='{ht_x:.1f}' y1='{top}' y2='{top+plot_height}'/>"
            f"{''.join(lines)}{event_data}{''.join(pills)}<line class='xg-crosshair' x1='{left}' x2='{left}' y1='{top}' y2='{top+plot_height}' hidden='hidden'/></svg>"
            f"<div class='xg-readout' aria-live='polite'>Hover or use arrow keys for minute-by-minute xG.</div>"
            f"<div class='legend'><button type='button' data-team-toggle='home' aria-pressed='true' style='color:{escape(home_color)}'>● {escape(home_name)}</button> "
            f"<button type='button' data-team-toggle='away' aria-pressed='true' style='color:{escape(away_color)}'>● {escape(away_name)}</button> · dashed line: away · HT: half-time</div></div>")
