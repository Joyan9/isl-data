"""Hand-tuned ISL palette; sampled logo colors are kept distinct for chart readability."""

TEAM_COLORS = {
    "Bengaluru FC": "#0b4ea2",
    "Chennaiyin FC": "#f59e0b",
    "Churchill Brothers": "#b91c1c",
    "East Bengal FC": "#dc2626",
    "FC Goa": "#f97316",
    "Inter Kashi": "#7c3aed",
    "Kerala Blasters FC": "#facc15",
    "Mohun Bagan SG": "#047857",
    "Mumbai City FC": "#2563eb",
    "Northeast United FC": "#7f1d1d",
    "Odisha FC": "#ea580c",
    "Punjab FC": "#0891b2",
    "SC Delhi": "#111827",
}


def colors_for(home: str, away: str) -> tuple[str, str]:
    home_color = TEAM_COLORS.get(home, "#2563eb")
    away_color = TEAM_COLORS.get(away, "#e11d48")
    if home_color.lower() == away_color.lower():
        away_color = "#475569"
    return home_color, away_color
