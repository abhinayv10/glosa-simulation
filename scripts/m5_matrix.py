"""M5 experiment: evaluation matrix (ADR-0016).

One-factor-at-a-time sweeps (horizon, p, compliance, driver, demand) around the deployed configuration, on both
corridors, over several evaluation seeds. Each cell is one SUMO run of 51 test vehicles; cells run in parallel
worker processes and are cached in build/m5/cells/, so an interrupted run resumes where it stopped.

Usage: python scripts/m5_matrix.py [--seeds 5] [--workers 12]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenwave.evaluation import (REFERENCE, SCENARIOS, SWEEPS, demand_levels, matrix,  # noqa: E402
                                  paired_effects, prepare, run_cell, vs_reference)

OUT = ROOT / "results" / "m5"
CELLS = ROOT / "build" / "m5" / "cells"


def _work(cell):
    path = CELLS / f"{cell.key}.csv"
    t = time.time()
    pd.DataFrame(run_cell(cell, ROOT)).to_csv(path, index=False)
    return cell.key, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5, help="evaluation seeds 1..N")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    seeds = list(range(1, args.seeds + 1))
    OUT.mkdir(parents=True, exist_ok=True)
    CELLS.mkdir(parents=True, exist_ok=True)

    for name in SCENARIOS:                       # networks + learned history per demand level (sequential)
        for d in demand_levels():
            prepare(ROOT, name, d)
            print(f"prepared corridor_{name} at demand x{d}", flush=True)

    cells = matrix(seeds)
    todo = [c for c in cells if not (CELLS / f"{c.key}.csv").exists()]
    print(f"{len(cells)} cells, {len(todo)} to run on {args.workers} workers", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(args.workers) as pool:
        futs = [pool.submit(_work, c) for c in todo]
        for i, f in enumerate(as_completed(futs), 1):
            key, dt = f.result()
            print(f"  [{i}/{len(todo)}] {key} ({dt:.0f}s)", flush=True)
    print(f"matrix done in {time.time() - t0:.0f}s", flush=True)

    trips = pd.concat([pd.read_csv(CELLS / f"{c.key}.csv", dtype={"level": str}) for c in cells], ignore_index=True)
    trips.to_csv(OUT / "trips.csv", index=False)
    eff = paired_effects(trips)
    eff.round(4).to_csv(OUT / "effects.csv", index=False)
    vs_reference(trips).round(4).to_csv(OUT / "vs_reference.csv", index=False)
    expected = {c.key: 51 for c in cells}
    got = trips.groupby(["scenario", "factor", "level", "demand", "seed"]).size()
    (OUT / "meta.json").write_text(json.dumps({
        "seeds": seeds, "reference": REFERENCE, "sweeps": SWEEPS, "cells": len(cells),
        "trips": len(trips), "trips_expected": sum(expected.values()), "min_trips_per_cell": int(got.min()),
    }, indent=2))

    pd.set_option("display.width", 220)
    show = eff[eff.metric.isin(["stops", "travel_time", "fuel_g", "broken_promises"])]
    piv = show.pivot_table(index=["scenario", "factor", "level"], columns="metric", values="mean", sort=False)
    print("\nMeans per configuration:\n", piv.round(2).to_string())


if __name__ == "__main__":
    main()
