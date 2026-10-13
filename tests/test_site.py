import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from fotmob_isl import parse
from fotmob_isl.site.data import load_match_bundles
from fotmob_isl.site.render import build_site
from fotmob_isl.site.team_colors import TEAM_PALETTE, colors_for, color_for, ciede2000, contrast_ratio


FIXTURE = Path(__file__).parent / "fixtures" / "matchDetails_6361990.json.gz"


def _fixture_data(tmp_path):
    with gzip.open(FIXTURE, "rb") as handle:
        match_data = json.loads(handle.read())
    match = parse.parse_match_row(match_data)
    pd.DataFrame([match], columns=parse.MATCH_COLS).to_csv(tmp_path / "matches.csv", index=False)
    pd.DataFrame(parse.parse_team_stats(match_data), columns=parse.TEAM_STATS_COLS).to_csv(
        tmp_path / "team_match_stats.csv", index=False
    )
    pd.DataFrame(parse.parse_shots(match_data), columns=parse.SHOT_COLS).to_csv(
        tmp_path / "shots.csv", index=False
    )
    pd.DataFrame(parse.parse_player_stats(match_data), columns=parse.PLAYER_STATS_COLS).to_csv(
        tmp_path / "player_match_stats.csv", index=False
    )
    return match


def test_match_bundle_formats_kickoff_and_credits_own_goal(tmp_path):
    _fixture_data(tmp_path)
    bundles = load_match_bundles(tmp_path, {"Bengaluru FC": "#0b4ea2", "SC Delhi": "#111827"})

    bundle = bundles[0]
    assert bundle.kickoff_ist() == "Sat 10 Oct 2026 · 17:00 IST"
    own_goal = next(goal for goal in bundle.goals() if "own goal" in goal["label"])
    assert own_goal["label"] == "Menno Koch (own goal)"
    assert own_goal["team_name"] == "SC Delhi"
    assert bundle.stat("home", ("BallPossesion", "possession")) == 64


def test_site_build_copies_shared_css_and_uses_logo_fallback(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _fixture_data(data_dir)
    output = tmp_path / "site"
    assert build_site(data_dir, tmp_path / "insights", output, tmp_path / "missing-logos") == 1

    html = (output / "6361990.html").read_text(encoding="utf-8")
    assert 'href="assets/style.css"' in html
    assert "Bengaluru FC" in html
    assert "2.97" in html
    assert "1.85" in html
    assert "3 – 2" in html
    assert "27 (" in html and ") – 10 (" in html
    assert "Menno Koch (og) 32'" in html
    assert (output / "assets" / "style.css").exists()
    assert "<style>" not in html
    assert "Shot map" not in html
    assert "Top performers" not in html


def test_unknown_team_palette_is_explicit():
    with pytest.raises(KeyError):
        color_for("Unknown Club")
    with pytest.raises(KeyError):
        colors_for("Unknown Club", "Bengaluru FC")


def test_team_palette_has_fixed_foreground_colours():
    assert len(TEAM_PALETTE) == 13
    assert len({entry["color"] for entry in TEAM_PALETTE.values()}) == len(TEAM_PALETTE)
    assert all(entry["on_color"] in {"#000000", "#ffffff"} for entry in TEAM_PALETTE.values())


def test_matches_and_logos_have_palette_entries():
    matches = pd.read_csv(Path("data/matches.csv"))
    assert set(matches["home_team_name"]).union(matches["away_team_name"]) <= set(TEAM_PALETTE)
    logos = {path.stem for path in Path("data/team_logos").iterdir() if path.is_file()}
    assert logos <= set(TEAM_PALETTE)


def test_palette_contrast_and_distances():
    for entry in TEAM_PALETTE.values():
        assert contrast_ratio(entry["color"], "#172033") >= 3
        assert contrast_ratio(entry["color"], "#111827") >= 3
        assert contrast_ratio(entry["text_color"], "#172033") >= 4.5
        assert contrast_ratio(entry["text_color"], "#111827") >= 4.5
    distances = [
        ciede2000(first["color"], second["color"])
        for index, first in enumerate(TEAM_PALETTE.values())
        for second_index, second in enumerate(TEAM_PALETTE.values())
        if second_index > index
    ]
    assert min(distances) >= 20


def test_site_has_compare_placeholder_and_match_reports(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _fixture_data(data_dir)
    output = tmp_path / "site"
    build_site(data_dir, tmp_path / "insights", output, tmp_path / "missing-logos")
    index = (output / "index.html").read_text(encoding="utf-8")
    matches = (output / "matches.html").read_text(encoding="utf-8")
    assert "Give Indian Football a Chance" in index
    assert "Pick two clubs. Start the argument." in index
    assert "League table" not in index
    assert "team-filter" not in index
    assert "Round 1" in matches
    assert "xG 2.97 – 1.85" in matches
    assert "6361990.html" in matches
    assert "Unofficial fan project" in matches
