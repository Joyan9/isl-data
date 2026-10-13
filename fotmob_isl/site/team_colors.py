"""Permanent, high-contrast club colours sampled from the logo set and hand-tuned."""

TEAM_PALETTE = {
    "Bengaluru FC": {"color": "#97b886", "on_color": "#000000"},
    "Chennaiyin FC": {"color": "#e413ff", "on_color": "#000000"},
    "Churchill Brothers": {"color": "#fb5a0a", "on_color": "#000000"},
    "East Bengal FC": {"color": "#07a4ff", "on_color": "#000000"},
    "FC Goa": {"color": "#f9e3f1", "on_color": "#000000"},
    "Inter Kashi": {"color": "#feba24", "on_color": "#000000"},
    "Kerala Blasters FC": {"color": "#39f7ff", "on_color": "#000000"},
    "Mohun Bagan SG": {"color": "#b07a85", "on_color": "#000000"},
    "Mumbai City FC": {"color": "#dafc0b", "on_color": "#000000"},
    "Northeast United FC": {"color": "#0d9a9b", "on_color": "#000000"},
    "Odisha FC": {"color": "#b1a1f6", "on_color": "#000000"},
    "Punjab FC": {"color": "#968907", "on_color": "#000000"},
    "SC Delhi": {"color": "#fefde2", "on_color": "#000000"},
}

TEAM_COLORS = {name: values["color"] for name, values in TEAM_PALETTE.items()}


def colors_for(home: str, away: str) -> tuple[str, str]:
    return (
        TEAM_PALETTE.get(home, {"color": "#538ae2"})["color"],
        TEAM_PALETTE.get(away, {"color": "#f05b49"})["color"],
    )


def color_for(name: str) -> dict[str, str]:
    return TEAM_PALETTE.get(name, {"color": "#538ae2", "on_color": "#000000"})
