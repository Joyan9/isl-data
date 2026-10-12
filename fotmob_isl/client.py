"""HTTP access to FotMob.

* matchDetails: /api/data/matchDetails?matchId=<id> (the endpoint the web app itself calls).
  Fallback on 401/403: the match page HTML, whose embedded __NEXT_DATA__ carries the same
  `stats`, `shotmap`, `playerStats` and `matchFacts` blocks (fallback URL pattern unverified).
* fixtures: the league page HTML; `__NEXT_DATA__.props.pageProps.fixtures.allMatches` lists the season.
* vote: /api/data/vote?matchId=<id>, the fan "Who will win?" poll (best effort).
"""
from __future__ import annotations

import json
import re
import time

import requests

API_URL = "https://www.fotmob.com/api/data/matchDetails"
VOTE_URL = "https://www.fotmob.com/api/data/vote"
HTML_URL = "https://www.fotmob.com/match/{match_id}"
LEAGUE_URL = "https://www.fotmob.com/leagues/{league_id}/fixtures/{slug}"
USER_AGENT = "fotmob-isl-research/0.1 (personal research project; low volume, cached)"
RETRY_STATUSES = {429, 500, 502, 503, 504}
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html"})
    return s


def _get(session: requests.Session, url: str, params: dict | None = None,
         attempts: int = 4) -> requests.Response:
    last_status = None
    err = "no attempt made"
    for i in range(attempts):
        try:
            r = session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            last_status = None
            err = str(exc)
        else:
            if r.status_code == 200:
                return r
            last_status = r.status_code
            err = f"HTTP {r.status_code}"
            if r.status_code not in RETRY_STATUSES:
                raise FetchError(f"{url}: {err}", r.status_code)
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 60))
                continue
        time.sleep(2 ** (i + 1))
    raise FetchError(f"{url}: gave up after {attempts} attempts ({err})", last_status)


def _next_props(html: str) -> dict:
    m = _NEXT_DATA.search(html)
    if not m:
        raise FetchError("page has no __NEXT_DATA__ block")
    return json.loads(m.group(1)).get("props", {}).get("pageProps", {})


def _from_html(session: requests.Session, match_id: int) -> dict:
    props = _next_props(_get(session, HTML_URL.format(match_id=match_id)).text)
    if "general" not in props or "content" not in props:
        raise FetchError("__NEXT_DATA__ pageProps lacks general/content")
    return props


def _is_match(md) -> bool:
    return isinstance(md, dict) and "general" in md and "header" in md


def fetch_match_details(session: requests.Session, match_id: int) -> tuple[dict, str]:
    """Return (matchDetails-shaped dict, source) where source is 'api' or 'html'.

    FotMob answers unknown match IDs with HTTP 200 and a body that has no match data,
    so the shape is checked here instead of trusting the status code.
    """
    try:
        r = _get(session, API_URL, params={"matchId": match_id})
    except FetchError as exc:
        if exc.status in (401, 403):
            return _from_html(session, match_id), "html"
        raise
    try:
        md = r.json()
    except ValueError:
        raise FetchError(f"match {match_id}: response was not JSON") from None
    if not _is_match(md):
        raise FetchError(f"match {match_id}: no match data in response (unknown match id?)")
    return md, "api"


def fetch_vote(session: requests.Session, match_id: int) -> dict | None:
    """Fan poll for a match. Best effort: any failure returns None and never fails the match."""
    try:
        body = _get(session, VOTE_URL, params={"matchId": match_id}, attempts=2).json()
    except (FetchError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def fetch_fixtures_props(session: requests.Session, league_id: int = 9478,
                         slug: str = "indian-super-league", season: str | None = None) -> dict:
    """pageProps of the league fixtures page. `season` like '2025/2026' (unverified for past seasons)."""
    url = LEAGUE_URL.format(league_id=league_id, slug=slug)
    props = _next_props(_get(session, url, params={"season": season} if season else None).text)
    if "fixtures" not in props:
        raise FetchError("league page pageProps has no 'fixtures' block")
    return props
