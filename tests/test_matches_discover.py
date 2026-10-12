import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from fotmob_isl import cli, parse

FIXTURE = Path(__file__).parent / "fixtures" / "matchDetails_6361990.json.gz"


@pytest.fixture()
def md():
    with gzip.open(FIXTURE, "rb") as f:
        return json.loads(f.read())


def test_match_row_matches_the_page(md):
    r = parse.parse_match_row(md)
    assert (r["venue_name"], r["venue_city"], r["venue_capacity"], r["venue_surface"]) == (
        "Sree Kanteerava Stadium", "Bangalore", 28001, "grass")
    assert (r["referee_id"], r["referee_name"], r["referee_country"]) == (
        1001080378, "Ashwin Kumar", "India")
    assert r["referee_yellow_per_match"] == pytest.approx(5.45)
    assert r["referee_yellow_league_avg"] == pytest.approx(4.24)
    assert r["referee_fouls_per_match"] == pytest.approx(21.67)
    assert r["referee_fouls_league_avg"] == pytest.approx(20.62)
    assert (r["referee_matches"], r["referee_red_total"], r["referee_penalties_total"]) == (22, 4, 3)
    assert (r["home_score"], r["away_score"]) == (3, 2)
    assert r["weather_temp_c"] == 27
    assert len(json.loads(r["insights_json"])) == 2
    assert r["fan_vote_home"] is None and r["fetched_at_utc"] is None   # no _pipeline block in fixture
    assert set(r) == set(parse.MATCH_COLS)


def test_fan_vote_from_pipeline_block(md):
    md["_pipeline"] = {"fetched_at": "2026-10-11T18:00:00+00:00",
                       "vote": {"Votes": [{"Name": "1x2", "Votes": [1243, 359, 307]},
                                          {"Name": "bts", "Votes": [0, 1]}]}}
    r = parse.parse_match_row(md)
    assert (r["fan_vote_home"], r["fan_vote_draw"], r["fan_vote_away"]) == (1243, 359, 307)
    assert r["fetched_at_utc"] == "2026-10-11T18:00:00+00:00"


def test_match_row_tolerates_missing_blocks(md):
    r = parse.parse_match_row({"general": md["general"], "header": md["header"], "content": {}})
    assert r["referee_id"] is None and r["venue_name"] is None and r["weather_temp_c"] is None


def _fx(id_, finished=False, cancelled=False):
    return {"id": str(id_), "home": {"id": "1", "name": "A"}, "away": {"id": "2", "name": "B"},
            "status": {"utcTime": "2026-10-10T11:30:00Z", "finished": finished, "cancelled": cancelled}}


def test_parse_fixtures():
    props = {"fixtures": {"allMatches": [_fx(1, finished=True), _fx(2), _fx(3, cancelled=True)]}}
    got = parse.parse_fixtures(props)
    assert [(g["match_id"], g["finished"], g["cancelled"]) for g in got] == [
        (1, True, False), (2, False, False), (3, False, True)]
    assert parse.parse_fixtures({}) == []


def test_ingest_discover_only_takes_new_finished_matches(md, monkeypatch, tmp_path, capsys):
    props = {"fixtures": {"allMatches": [_fx(6361990, finished=True), _fx(7, finished=True),
                                         _fx(8), _fx(9, cancelled=True)]}}
    fetched = []

    def fake_fetch(session, match_id):
        fetched.append(match_id)
        return json.loads(json.dumps(md)), "api"

    monkeypatch.setattr(cli, "fetch_fixtures_props", lambda *a, **k: props)
    monkeypatch.setattr(cli, "fetch_match_details", fake_fetch)
    monkeypatch.setattr(cli, "fetch_vote", lambda s, m: {"Votes": [{"Name": "1x2", "Votes": [1, 2, 3]}]})
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "7.json.gz").write_bytes(b"x")          # match 7 already ingested

    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "--discover", "--data-dir", str(tmp_path)])
    assert exc.value.code == 0
    assert fetched == [6361990]                                  # not 7 (have it), 8 (unfinished), 9 (cancelled)
    m = pd.read_csv(tmp_path / "matches.csv")
    assert list(m.columns) == parse.MATCH_COLS and len(m) == 1
    assert m.loc[0, "fan_vote_draw"] == 2 and m.loc[0, "referee_name"] == "Ashwin Kumar"
    assert (tmp_path / "raw" / "6361990.json.gz").exists()
    assert all((tmp_path / f).exists() for f in ("shots.csv", "team_match_stats.csv", "player_match_stats.csv"))


def test_ingest_requires_ids_or_discover():
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest"])
    assert exc.value.code == 2
