"""CSV + raw-JSON persistence. Writes are deterministic so git diffs only show real changes."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd


def save_raw(data_dir: Path, match_id: int, md: dict) -> Path:
    path = data_dir / "raw" / f"{match_id}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(md, sort_keys=True, separators=(",", ":")).encode()
    with gzip.GzipFile(path, "wb", mtime=0) as f:  # mtime=0 -> identical bytes for identical data
        f.write(payload)
    return path


def load_raw(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read())


def _as_str_frame(rows: list[dict], cols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=cols, dtype=object)
    return df.where(df.notna(), "").astype(str)


def upsert_csv(path: Path, rows: list[dict], cols: list[str], pk: list[str],
               match_ids: list[int]) -> int:
    """Replace every row of `match_ids` in `path` with `rows` (idempotent per match).

    Existing rows are read back as strings and left untouched, so re-running never rewrites
    other matches' values. Returns the number of rows written for the given matches.
    """
    new = _as_str_frame(rows, cols)
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        old = old[~old["match_id"].isin({str(m) for m in match_ids})]
        df = pd.concat([old[cols], new], ignore_index=True)
    else:
        df = new
    df = df.assign(_m=pd.to_numeric(df["match_id"])).sort_values(
        ["_m"] + [c for c in pk if c != "match_id"], kind="mergesort"
    ).drop(columns="_m")
    dupes = df.duplicated(subset=pk).sum()
    if dupes:
        raise ValueError(f"{path.name}: {dupes} duplicate primary keys {pk}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")
    return len(new)
