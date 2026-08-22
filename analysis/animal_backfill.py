#!/usr/bin/env python3
"""RM-043 — animal-count backfill from replays.parquet (dev-only, NOT shipped).

The existing `episode_features.csv` has no animal column; only the small
`summary.csv` sample does. This streams `replays.parquet`, decodes only the
PUBLIC ladder episodes (validation episodes excluded), and writes a compact
per-seat animal table:

    animal_backfill.csv
      episode_id, seat, max_animals, max_geese, max_cows, max_sheep

`max_*` is the peak simultaneous count of placed animals of that type across
the episode (an animal is a tile with "animal" in it; structure kind COOP for
goose, PASTURE for cow/sheep). The earlier RM-040 regression could not test the
animal lever because this column was missing; this file fills that gap.

Memory pattern follows the proven extract_summary.py: pyarrow iter_batches with
batch_size=1, row-group min/max filtering on episode_id, and only the matching
groups decoded. Run `--limit 200` first to sanity-check throughput, then drop
the limit for the full pass.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).parent
DATASET = Path("/home/mayur/Projects/Dataset")
EPISODES_CSV = DATASET / "episodes.csv"
REPLAYS_PARQUET = DATASET / "replays.parquet"
OUT_CSV = DATASET / "animal_backfill.csv"

ANIMAL_TO_KIND = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}


def extract_seat(replay, seat):
    """Peak placed-animal counts for one seat."""
    max_total = 0
    max_goose = 0
    max_cow = 0
    max_sheep = 0
    for step in replay["steps"]:
        farm = step[0]["observation"]["farms"][seat]
        counts = {"GOOSE": 0, "COW": 0, "SHEEP": 0}
        for row in farm.get("tiles", []):
            for cell in row:
                if isinstance(cell, dict) and "animal" in cell:
                    a = cell.get("animal")
                    if a in counts:
                        counts[a] += 1
        total = sum(counts.values())
        if total > max_total:
            max_total = total
        max_goose = max(max_goose, counts["GOOSE"])
        max_cow = max(max_cow, counts["COW"])
        max_sheep = max(max_sheep, counts["SHEEP"])
    return {
        "max_animals": max_total,
        "max_geese": max_goose,
        "max_cows": max_cow,
        "max_sheep": max_sheep,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cap public episodes (default: all public)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import pandas as pd

    pa.jemalloc_set_decay_ms(0)

    eps = pd.read_csv(EPISODES_CSV, usecols=["episode_id", "type"])
    pub = eps[eps["type"] == "EPISODE_TYPE_PUBLIC"]
    if args.limit:
        pub = pub.sample(n=min(args.limit, len(pub)), random_state=args.seed)
    sample_ids = set(pub["episode_id"].astype(int))
    print(f"target episodes: {len(sample_ids)}", flush=True)

    pf = pq.ParquetFile(REPLAYS_PARQUET)
    groups = []
    for i in range(pf.metadata.num_row_groups):
        rg = pf.metadata.row_group(i)
        for j in range(rg.num_columns):
            col = rg.column(j)
            if col.path_in_schema == "episode_id":
                s = col.statistics
                if s and s.has_min_max:
                    groups.append((i, s.min, s.max))
                break
    matching = [g[0] for g in groups
                if any(g[1] <= eid <= g[2] for eid in sample_ids)]
    print(f"row groups to read: {len(matching)} / {len(groups)}", flush=True)

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode_id", "seat", "max_animals",
                    "max_geese", "max_cows", "max_sheep"])
        done = 0
        t0 = time.time()
        it = pf.iter_batches(batch_size=1, columns=["episode_id", "replay_json"],
                             row_groups=matching)
        for batch in it:
            eid = batch.column("episode_id")[0].as_py()
            if eid not in sample_ids:
                continue
            blob = batch.column("replay_json")[0].as_py()
            try:
                replay = json.loads(blob)
            except Exception as e:
                print(f"  episode {eid}: decode failed ({e})", flush=True)
                continue
            for seat in (0, 1):
                row = {"episode_id": eid, "seat": seat}
                row.update(extract_seat(replay, seat))
                w.writerow([row["episode_id"], row["seat"], row["max_animals"],
                            row["max_geese"], row["max_cows"], row["max_sheep"]])
            del replay, blob
            done += 1
            if done % 200 == 0:
                rate = done / (time.time() - t0)
                print(f"  done {done}/{len(sample_ids)} "
                      f"({rate:.1f} eps/s)", flush=True)

    print(f"wrote {OUT_CSV} ({done} episodes)")


if __name__ == "__main__":
    main()
