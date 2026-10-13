from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import parse
from .analysis import generate_insights
from .client import FetchError, fetch_fixtures_props, fetch_match_details, fetch_vote, make_session
from .reporting import write_match_reports
from .site import build_site
from .store import save_raw, upsert_csv
from .validate import validate_match

ISL_LEAGUE_ID = 9478


def _summary(md: dict) -> str:
    return (f"team_stats={len(parse.parse_team_stats(md))} "
            f"shots={len(parse.parse_shots(md))} "
            f"player_stats={len(parse.parse_player_stats(md))}")


def cmd_smoke(args) -> int:
    """Fetch one match and report; writes nothing. Use it to check FotMob answers this machine."""
    md, source = fetch_match_details(make_session(), args.match_id)
    meta = parse.match_meta(md)
    errors, warnings = validate_match(md)
    row = parse.parse_match_row(md)
    print(f"source={source} match={meta['match_id']} "
          f"{meta['home']['name']} v {meta['away']['name']} finished={meta['finished']}")
    print(_summary(md))
    print(f"venue={row['venue_name']} referee={row['referee_name']}")
    for w in warnings:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)
    return 1 if errors else 0


def cmd_discover(args) -> int:
    """List the season's fixtures from the league page; prints finished match IDs."""
    props = fetch_fixtures_props(make_session(), args.league_id, season=args.season)
    fx = parse.parse_fixtures(props)
    finished = [f["match_id"] for f in fx if f["finished"] and not f["cancelled"]]
    cancelled = sum(f["cancelled"] for f in fx)
    print(f"{len(fx)} fixtures: {len(finished)} finished, {cancelled} cancelled, "
          f"{len(fx) - len(finished) - cancelled} not finished")
    print(" ".join(map(str, finished)))
    return 0


def cmd_ingest(args) -> int:
    data_dir = Path(args.data_dir)
    session = make_session()
    ids = list(args.match_ids or [])
    skip_existing = args.skip_existing

    if args.discover:
        fx = parse.parse_fixtures(fetch_fixtures_props(session, args.league_id, season=args.season))
        finished = [f["match_id"] for f in fx if f["finished"] and not f["cancelled"]]
        ids += [m for m in finished if m not in ids]
        skip_existing = True
        todo = sum(1 for m in ids if not (data_dir / "raw" / f"{m}.json.gz").exists())
        print(f"discovered {len(fx)} fixtures, {len(finished)} finished, {todo} not yet ingested")
    if not ids:
        print("nothing to do")
        return 0

    tables = {"matches": [], "team": [], "shots": [], "players": []}
    done: list[int] = []
    failed: list[int] = []
    fetched = 0

    for match_id in ids:
        if skip_existing and (data_dir / "raw" / f"{match_id}.json.gz").exists():
            print(f"{match_id}: already ingested, skipping")
            continue
        if fetched:
            time.sleep(1.5 + random.random())
        fetched += 1
        try:
            md, source = fetch_match_details(session, match_id)
        except FetchError as exc:
            print(f"{match_id}: FETCH FAILED ({exc})")
            failed.append(match_id)
            continue
        try:
            meta = parse.match_meta(md)
            if meta["league_id"] != args.league_id:
                print(f"{match_id}: league {meta['league_id']} != {args.league_id}, skipping")
                continue
            if not meta["finished"]:
                print(f"{match_id}: not finished yet, skipping")
                continue
            time.sleep(0.5)
            md["_pipeline"] = {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": source,
                "vote": fetch_vote(session, match_id),
            }
            errors, warnings = validate_match(md)
            for w in warnings:
                print(f"{match_id}: WARN {w}")
            if errors:
                print(f"{match_id}: VALIDATION FAILED {errors}")
                failed.append(match_id)
                continue
            match_row = parse.parse_match_row(md)
            team_rows = parse.parse_team_stats(md)
            shot_rows = parse.parse_shots(md)
            player_rows = parse.parse_player_stats(md)
        except Exception as exc:  # one malformed match must not abort the batch
            print(f"{match_id}: PARSE FAILED ({type(exc).__name__}: {exc})")
            failed.append(match_id)
            continue
        save_raw(data_dir, match_id, md)
        tables["matches"].append(match_row)
        tables["team"] += team_rows
        tables["shots"] += shot_rows
        tables["players"] += player_rows
        done.append(match_id)
        print(f"{match_id}: ok via {source} ({meta['home']['name']} v {meta['away']['name']}) "
              f"{_summary(md)}")

    if done:
        upsert_csv(data_dir / "matches.csv", tables["matches"],
                   parse.MATCH_COLS, parse.MATCH_PK, done)
        upsert_csv(data_dir / "team_match_stats.csv", tables["team"],
                   parse.TEAM_STATS_COLS, parse.TEAM_STATS_PK, done)
        upsert_csv(data_dir / "shots.csv", tables["shots"],
                   parse.SHOT_COLS, parse.SHOT_PK, done)
        upsert_csv(data_dir / "player_match_stats.csv", tables["players"],
                   parse.PLAYER_STATS_COLS, parse.PLAYER_STATS_PK, done)
    print(f"ingested={len(done)} failed={len(failed)}")
    return 1 if failed else 0


def cmd_report(args) -> int:
    """Generate markdown match reports from the ingested CSV tables."""
    if args.match_id is None and not args.match_ids and not args.all:
        raise SystemExit("report needs --match-id, --match-ids, or --all")

    match_ids = [args.match_id] if args.match_id is not None else list(args.match_ids or [])
    if args.all:
        match_ids = None
    paths = write_match_reports(Path(args.data_dir), Path(args.output_dir), match_ids)
    print(f"wrote {len(paths)} reports to {args.output_dir}")
    return 0


def cmd_analyze(args) -> int:
    stats = generate_insights(
        Path(args.data_dir), Path(args.insights_dir), max_calls=args.max_ai_calls,
        model=args.model, delay_seconds=args.delay_seconds, force=args.force,
    )
    print(" ".join(f"{key}={value}" for key, value in stats.items()))
    if stats["failed"]:
        print(
            "One or more optional AI insight requests failed. "
            "Failure details were saved under the insights directory; "
            "the static site can still be built."
        )
    return 1 if stats["failed"] else 0


def cmd_site(args) -> int:
    print(f"wrote {build_site(Path(args.data_dir), Path(args.insights_dir), Path(args.site_dir), Path(args.logos_dir))} match pages")
    return 0


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="fotmob_isl")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("smoke", help="fetch + parse one match, write nothing")
    s.add_argument("match_id", type=int)
    s.set_defaults(func=cmd_smoke)

    d = sub.add_parser("discover", help="list finished match IDs from the league fixtures page")
    d.add_argument("--league-id", type=int, default=ISL_LEAGUE_ID)
    d.add_argument("--season", help="e.g. 2025/2026 (default: current season)")
    d.set_defaults(func=cmd_discover)

    i = sub.add_parser("ingest", help="fetch matches and upsert the CSV tables")
    i.add_argument("--match-ids", type=int, nargs="+")
    i.add_argument("--discover", action="store_true",
                   help="also ingest every finished fixture not yet in data/raw")
    i.add_argument("--season", help="with --discover, e.g. 2025/2026 (default: current season)")
    i.add_argument("--data-dir", default="data")
    i.add_argument("--league-id", type=int, default=ISL_LEAGUE_ID)
    i.add_argument("--skip-existing", action="store_true")
    i.set_defaults(func=cmd_ingest)

    r = sub.add_parser("report", help="generate markdown match reports from the ingested CSV tables")
    r.add_argument("--match-id", type=int, help="generate a single report for this match")
    r.add_argument("--match-ids", type=int, nargs="+", help="generate reports for these matches")
    r.add_argument("--all", action="store_true", help="generate reports for every match in matches.csv")
    r.add_argument("--data-dir", default="data")
    r.add_argument("--output-dir", default="reports")
    r.set_defaults(func=cmd_report)

    a = sub.add_parser("analyze", help="generate cached Groq insights for ingested matches")
    a.add_argument("--data-dir", default="data")
    a.add_argument("--insights-dir", default="reports/insights")
    a.add_argument("--max-ai-calls", type=int, default=3)
    a.add_argument("--model", default="openai/gpt-oss-20b")
    a.add_argument("--delay-seconds", type=float, default=2.0)
    a.add_argument("--force", action="store_true")
    a.set_defaults(func=cmd_analyze)

    w = sub.add_parser("site", help="build the static match site")
    w.add_argument("--data-dir", default="data")
    w.add_argument("--insights-dir", default="reports/insights")
    w.add_argument("--site-dir", default="site")
    w.add_argument("--logos-dir", default="data/team_logos")
    w.set_defaults(func=cmd_site)

    args = p.parse_args(argv)
    if args.cmd == "ingest" and not (args.match_ids or args.discover):
        p.error("ingest needs --match-ids and/or --discover")
    try:
        sys.exit(args.func(args))
    except FetchError as exc:
        print(f"FETCH FAILED: {exc}")
        sys.exit(1)
