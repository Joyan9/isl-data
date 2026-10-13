import gzip
import json
from pathlib import Path

import pandas as pd

from fotmob_isl import parse
from fotmob_isl.site.charts import comparison_chart
from fotmob_isl.site.data import load_match_bundles
from fotmob_isl.site.render import build_site
from fotmob_isl.site.team_colors import colors_for


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
    assert "BF" in html
    assert "2.97" in html
    assert "1.85" in html
    assert "3 – 2" in html
    assert "27 (" in html and ") – 10 (" in html
    assert "Menno Koch (og) 32'" in html
    assert (output / "assets" / "style.css").exists()
    assert "<style>" not in html


def test_charts_escape_labels_and_include_team_names():
    svg = comparison_chart(
        "Shots", "<Home>", "Away & Co", 3, 1, "#123456", "#654321"
    )
    assert "&lt;Home&gt;" in svg
    assert "Away &amp; Co" in svg
    assert "#123456" in svg and "#654321" in svg


def test_team_color_clashes_get_a_distinct_away_color():
    home, away = colors_for("Unknown Club", "Unknown Club")
    assert home != away


def test_index_groups_matches_and_includes_table(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _fixture_data(data_dir)
    output = tmp_path / "site"
    build_site(data_dir, tmp_path / "insights", output, tmp_path / "missing-logos")
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "Round 1" in html
    assert "League table" in html
    assert "Bengaluru FC" in html and "SC Delhi" in html
    assert 'id="team-filter"' in html
    assert 'meta name="description"' in html
