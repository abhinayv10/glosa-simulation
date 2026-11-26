from pathlib import Path

import numpy as np
import pandas as pd

from greenwave.evaluation import REFERENCE, SWEEPS, bootstrap_ci, matrix, paired_effects, sweep
from greenwave.scenario import load_scenario
from greenwave.sim.corridor import flows, scale_demand

ROOT = Path(__file__).resolve().parents[1]


def test_matrix_shape():
    cells = matrix([1, 2])
    assert len({c.key for c in cells}) == len(cells)                       # keys unique (cache files)
    fixed = [c for c in cells if c.scenario == "fixed"]
    assert not any(c.factor == "p_required" for c in fixed)                # p is meaningless for exact windows
    # every demand level has its own drive-at-limit baseline per seed
    for d in [REFERENCE["demand"]] + SWEEPS["demand"]:
        assert sum(c.factor == "baseline" and c.demand == d for c in fixed) == 2
    hz = [c for c in cells if c.factor == "horizon"]
    assert all(c.horizon == c.level and c.p_required == REFERENCE["p_required"] for c in hz)


def test_scale_demand_scales_all_flows():
    sc = load_scenario(ROOT / "scenarios" / "corridor_actuated.yaml")
    base = {f[0]: f[5] for f in flows(sc)}
    scaled = {f[0]: f[5] for f in flows(scale_demand(sc, 1.4))}
    assert base.keys() == scaled.keys()
    assert all(abs(scaled[k] - 1.4 * v) < 1e-9 for k, v in base.items())


def test_bootstrap_ci_covers_mean():
    x = np.random.default_rng(1).normal(5, 1, 400)
    lo, hi = bootstrap_ci(x)
    assert lo < 5 < hi and hi - lo < 0.3


def test_paired_effects_pairs_by_departure():
    rows = []
    for seed in (1, 2):
        for dep in range(10):
            b = dict(scenario="fixed", demand=1.0, seed=seed, depart=dep, stops=2 + dep % 2, wait=0, travel_time=300,
                     fuel_g=200, near_stops=0, broken_promises=0)
            rows.append(dict(b, factor="baseline", level="1.0"))
            rows.append(dict(b, factor="reference", level="-", stops=b["stops"] - 1, travel_time=310))
            rows.append(dict(b, factor="horizon", level="2", stops=b["stops"], travel_time=305))
    eff = paired_effects(pd.DataFrame(rows))
    ref = eff[(eff.factor == "reference") & (eff.metric == "stops")].iloc[0]
    assert ref.n == 20 and ref.delta == -1 and ref.delta_lo == ref.delta_hi == -1   # identical pairs: no spread
    s = sweep(eff, "fixed", "horizon", "travel_time")
    assert list(s.level) == ["2", "4"] and list(s.delta) == [5, 10]
