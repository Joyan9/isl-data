import gzip
import json
from pathlib import Path

import pytest

from fotmob_isl import cli
from fotmob_isl.client import FetchError, fetch_match_details

FIXTURE = Path(__file__).parent / "fixtures" / "matchDetails_6361990.json.gz"


class FakeResp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text, self.headers = status, body, text, {}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)

    def get(self, url, params=None, timeout=None):
        return self.responses.pop(0)


@pytest.fixture(scope="module")
def md():
    with gzip.open(FIXTURE, "rb") as f:
        return json.loads(f.read())


def test_unknown_match_id_is_a_fetch_error():
    # FotMob returns 200 with no match data for ids that don't exist
    with pytest.raises(FetchError, match="no match data"):
        fetch_match_details(FakeSession(FakeResp(200, {})), 1)


def test_non_json_body_is_a_fetch_error():
    with pytest.raises(FetchError, match="not JSON"):
        fetch_match_details(FakeSession(FakeResp(200, None)), 1)


def test_valid_response_uses_api(md):
    got, source = fetch_match_details(FakeSession(FakeResp(200, md)), 6361990)
    assert source == "api" and got["general"]["matchId"] == "6361990"


def test_403_falls_back_to_next_data(md):
    html = ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": md}}) + "</script>")
    got, source = fetch_match_details(FakeSession(FakeResp(403), FakeResp(200, text=html)), 6361990)
    assert source == "html" and "shotmap" in got["content"]


def test_404_is_not_retried_or_fallen_back():
    with pytest.raises(FetchError) as exc:
        fetch_match_details(FakeSession(FakeResp(404)), 1)
    assert exc.value.status == 404


def test_ingest_survives_a_malformed_match(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "fetch_match_details", lambda s, m: ({"general": {}}, "api"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "--match-ids", "1", "--data-dir", str(tmp_path)])
    assert exc.value.code == 1
    assert "PARSE FAILED" in capsys.readouterr().out
    assert not (tmp_path / "shots.csv").exists()


def test_ingest_unknown_id_exits_1_with_message(monkeypatch, tmp_path, capsys):
    def boom(session, match_id):
        raise FetchError(f"match {match_id}: no match data in response (unknown match id?)")
    monkeypatch.setattr(cli, "fetch_match_details", boom)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "--match-ids", "1", "--data-dir", str(tmp_path)])
    assert exc.value.code == 1
    assert "FETCH FAILED" in capsys.readouterr().out
