#!/usr/bin/env python3
"""RM-043 — parallel animal-count backfill from replays.parquet (dev-only).

Same as animal_backfill.py but parallel across row groups. Each worker writes a
temp CSV (one per chunk); the main process merges them into animal_backfill.csv.

The decode is the bottleneck (~8 eps/s single-core), so the 16-core machine
turns a ~70-min pass into ~6-8 min. Memory stays bounded: each worker streams
one batch at a time.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

DATASET = Path("/home/mayur/Projects/Dataset")
EPISODES_CSV = DATASET / "episodes.csv"
REPLAYS_PARQUET = DATASET / "replays.parquet"
OUT_CSV = DATASET / "animal_backfill.csv"
TMP_DIR = DATASET / ".animal_tmp"


def extract_seat(replay, seat):
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
        max_total = max(max_total, total)
        max_goose = max(max_goose, counts["GOOSE"])
        max_cow = max(max_cow, counts["COW"])
        max_sheep = max(max_sheep, counts["SHEEP"])
    return max_total, max_goose, max_cow, max_sheep


def process_row_groups(rg_indices, sample_ids, out_path):
    pf = pq.ParquetFile(REPLAYS_PARQUET)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode_id", "seat", "max_animals",
                    "max_geese", "max_cows", "max_sheep"])
        n = 0
        it = pf.iter_batches(batch_size=1, columns=["episode_id", "replay_json"],
                             row_groups=rg_indices)
        for batch in it:
            eid = batch.column("episode_id")[0].as_py()
            if eid not in sample_ids:
                continue
            blob = batch.column("replay_json")[0].as_py()
            try:
                replay = json.loads(blob)
            except Exception:
                continue
            for seat in (0, 1):
                mt, mg, mc, ms = extract_seat(replay, seat)
                w.writerow([eid, seat, mt, mg, mc, ms])
            del replay, blob
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 8)
    ap.add_argument("--chunk-size", type=int, default=150,
                    help="row groups per worker chunk")
    args = ap.parse_args()

    import pandas as pd
    pa.jemalloc_set_decay_ms(0)

    eps = pd.read_csv(EPISODES_CSV, usecols=["episode_id", "type"])
    pub = eps[eps["type"] == "EPISODE_TYPE_PUBLIC"]
    sample_ids = set(pub["episode_id"].astype(int))
    print(f"target episodes: {len(sample_ids)}", flush=True)

    pf = pq.ParquetFile(REPLAYS_PARQUET)
    n_groups = pf.metadata.num_row_groups

    # Only chunks that intersect sample_ids (by episode_id stats) are worth
    # scanning; the rest can be skipped.
    id_stats = []
    for i in range(n_groups):
        rg = pf.metadata.row_group(i)
        for j in range(rg.num_columns):
            c = rg.column(j)
            if c.path_in_schema == "episode_id":
                s = c.statistics
                id_stats.append((i, s.min, s.max) if (s and s.has_min_max)
                                else (i, None, None))
                break
    groups = [i for (i, lo, hi) in id_stats
              if (lo is None or hi is None or
                  any(lo <= eid <= hi for eid in sample_ids))]
    print(f"usable row groups: {len(groups)} / {n_groups}", flush=True)

    chunks = [groups[i:i + args.chunk_size]
              for i in range(0, len(groups), args.chunk_size)]

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    paths = [TMP_DIR / f"chunk_{i}.csv" for i in range(len(chunks))]

    # Sample ids are ~34k ints; sharing via fork keeps it cheap.
    total = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_row_groups, chunk, sample_ids, path): (chunk, path)
                for chunk, path in zip(chunks, paths)}
        for fut in as_completed(futs):
            n = fut.result()
            total += n
            print(f"  chunk done: {n} episodes (running total {total})", flush=True)

    # Merge temp files in order.
    with open(OUT_CSV, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["episode_id", "seat", "max_animals",
                    "max_geese", "max_cows", "max_sheep"])
        for p in paths:
            if p.exists():
                with open(p) as f:
                    next(f)  # skip header
                    for line in f:
                        out.write(line)
    print(f"merged {total} episodes -> {OUT_CSV}")


if __name__ == "__main__":
    main()
