from __future__ import annotations

import re
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..analysis import _insight_path, _load_cached, context_hash, _match_context
from ..stat_keys import ACCURATE_PASSES, BALL_POSSESSION, EXPECTED_GOALS, TOTAL_SHOTS
from .charts import split_bar, tape_bar, xg_race
from .data import MatchBundle, load_match_bundles
from .team_colors import TEAM_COLORS
from ..xg_model import fair_result, verdict
from .share_card import make_share_card
from .comparison import build_comparison_data, write_expected_table_csv


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "team"


def _initials(value: str) -> str:
    words = [word for word in re.split(r"\W+", value) if word]
    return "".join(word[0] for word in words[:2]).upper() or "?"


def _display_number(value):
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _display_decimal(value):
    if value is None or pd.isna(value):
        return None
    return f"{float(value):.2f}"


def _format_generated_at(value: str) -> str:
    generated = datetime.fromisoformat(value)
    return generated.astimezone(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")


def _format_table_value(column: str, value) -> str:
    if value is None or pd.isna(value):
        return ""
    if column in {"P", "Pts", "GF", "GA", "GD"}:
        return str(int(round(float(value))))
    if column in {"xPts", "Pts-xPts", "xGF", "xGA", "xGD"}:
        return f"{float(value):.2f}"
    return str(value)


def _insights(bundle: MatchBundle, insights_dir: Path) -> list[str]:
    context = _match_context(bundle.match, bundle.team_stats, bundle.shots, bundle.players)
    cached = _load_cached(
        _insight_path(insights_dir, bundle.match_id), context_hash(context)
    )
    if not cached:
        return []
    return [
        line.lstrip("-–—•* \t").strip()
        for line in cached.get("insights", "").splitlines()
        if line.strip()
    ]


def _copy_logos(logos_dir: Path, site_dir: Path) -> dict[str, str]:
    output = site_dir / "assets" / "logos"
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for source in logos_dir.glob("*"):
        if source.is_file() and source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            slug = _slug(source.stem)
            target = output / f"{slug}{source.suffix.lower()}"
            shutil.copyfile(source, target)
            paths[source.stem] = f"assets/logos/{target.name}"
    return paths


def build_site(data_dir: Path, insights_dir: Path, site_dir: Path,
               logos_dir: Path = Path("data/team_logos"),
               base_url: str = "https://joyan9.github.io/isl-data/") -> int:
    bundles = load_match_bundles(data_dir, TEAM_COLORS)
    logo_paths = _copy_logos(logos_dir, site_dir) if logos_dir.exists() else {}
    assets = site_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).parent / "static" / "style.css", assets / "style.css")
    shutil.copyfile(Path(__file__).parent / "static" / "site.js", assets / "site.js")
    fonts = Path(__file__).parent / "static" / "fonts"
    if fonts.exists():
        shutil.copytree(fonts, assets / "fonts", dirs_exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["split_bar"] = split_bar
    env.globals["tape_bar"] = tape_bar
    env.globals["xg_race"] = xg_race
    env.globals["logo_path"] = lambda name: logo_paths.get(name)
    env.globals["initials"] = _initials
    env.globals["slug"] = _slug
    env.globals["format_table_value"] = _format_table_value
    site_bundles = []
    for bundle in bundles:
        if pd.isna(pd.to_numeric(bundle.match.get("home_score"), errors="coerce")) or pd.isna(
            pd.to_numeric(bundle.match.get("away_score"), errors="coerce")
        ):
            continue
        home_shots_frame = bundle.shots_for("home")
        away_shots_frame = bundle.shots_for("away")
        site_bundles.append({
            "bundle": bundle,
            "insights": _insights(bundle, insights_dir),
            "home_logo": logo_paths.get(bundle.home_name),
            "away_logo": logo_paths.get(bundle.away_name),
            "home_xg": _display_decimal(bundle.stat("home", EXPECTED_GOALS)),
            "away_xg": _display_decimal(bundle.stat("away", EXPECTED_GOALS)),
            "home_shots": len(home_shots_frame),
            "away_shots": len(away_shots_frame),
            "home_on_target": _display_number(bundle.stat("home", "ShotsOnTarget")),
            "away_on_target": _display_number(bundle.stat("away", "ShotsOnTarget")),
            "home_possession": _display_number(bundle.stat("home", (BALL_POSSESSION, "possession"))),
            "away_possession": _display_number(bundle.stat("away", (BALL_POSSESSION, "possession"))),
            "home_passes": _display_number(bundle.stat("home", ACCURATE_PASSES)),
            "away_passes": _display_number(bundle.stat("away", ACCURATE_PASSES)),
            "tape": bundle.tape(),
            "referee": bundle.referee(),
            "poll": bundle.poll(),
            "scorers_home": bundle.scorers("home"),
            "scorers_away": bundle.scorers("away"),
            "home_initials": _initials(bundle.home_name),
            "away_initials": _initials(bundle.away_name),
        })
        probability = fair_result(
            bundle.shots.to_dict("records"), bundle.match.get("home_team_id"), bundle.match.get("away_team_id")
        )
        actual = ("home_win" if int(bundle.score("home")) > int(bundle.score("away"))
                  else "away_win" if int(bundle.score("away")) > int(bundle.score("home")) else "draw")
        probability["actual"] = actual
        probability["verdict"] = verdict(float(probability[actual]))
        site_bundles[-1]["fair"] = probability
    site_bundles.sort(
        key=lambda item: (
            float(pd.to_numeric(item["bundle"].match.get("round"), errors="coerce") or 0),
            str(item["bundle"].match.get("match_date_utc") or ""),
        ),
        reverse=True,
    )
    rounds = []
    for item in site_bundles:
        round_name = str(item["bundle"].match.get("round") or "Other")
        if not rounds or rounds[-1]["name"] != round_name:
            rounds.append({"name": round_name, "matches": []})
        rounds[-1]["matches"].append(item)
    common = {
        "site_name": "Give Indian Football a Chance",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": base_url.rstrip("/") + "/",
    }
    common["generated_at_display"] = _format_generated_at(common["generated_at"])
    comparison = build_comparison_data([item["bundle"] for item in site_bundles], logo_paths)
    build_date = datetime.now(timezone.utc).date().isoformat()
    write_expected_table_csv(site_dir / "expected_table.csv", comparison["table"], comparison["generated_at"])
    write_expected_table_csv(site_dir / f"expected_table_{build_date}.csv", comparison["table"], comparison["generated_at"])
    common["comparison_json"] = json.dumps(comparison, separators=(",", ":"), ensure_ascii=False)
    common["table_csv"] = f"expected_table_{build_date}.csv"
    common["comparison"] = comparison
    (site_dir / "index.html").write_text(
        env.get_template("index.html").render(**common), encoding="utf-8"
    )
    (site_dir / "matches.html").write_text(
        env.get_template("matches.html").render(rounds=rounds, **common), encoding="utf-8"
    )
    match_template = env.get_template("match.html")
    for item in site_bundles:
        bundle = item["bundle"]
        html = match_template.render(
            item=item,
            goals=bundle.goals(),
            shots=bundle.shots[bundle.shots["match_id"].astype(str) == bundle.match_id],
            **common,
        )
        make_share_card(site_dir / "share" / f"{bundle.match_id}.png", item, item["fair"]["verdict"])
        (site_dir / f"{bundle.match_id}.html").write_text(html, encoding="utf-8")
    return len(site_bundles)
