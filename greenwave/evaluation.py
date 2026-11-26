"""M5 evaluation matrix (ADR-0016).

One-factor-at-a-time sweeps around the deployed configuration, repeated over several evaluation seeds:

- reference: horizon 4, p 0.85, perfect compliance, nominal demand; signal knowledge = timing plan (fixed) or
  controller logs | cross demand (actuated); queue model on. The M2 "advised ... + queue" conditions.
- horizon: signals considered per plan (ADR-0005 left it to M5).
- p_required: how sure the planner must be that an uncertain green has started (ADR-0009). Actuated only:
  fixed-time windows are exact, so p changes nothing there.
- compliance: how far drivers slow towards the advice (ADR-0011), 0 = ignore it.
- driver: the realistic driver of M2 (compliance 0.8, +/- 2 km/h bias, 2 s reaction, imperfect speed keeping).
- demand: all background flows scaled. Each level has its own history (queue model and forecaster are learned
  at the demand they are used in) and its own drive-at-limit baseline.

Every advised trip is paired with the drive-at-limit trip of the same scenario, demand, seed and departure
time, so effects are differences on identical traffic and signal phase; confidence intervals come from a
bootstrap over those pairs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HIST_SEED = 101
SCENARIOS = ("fixed", "actuated")
REFERENCE = dict(horizon=4, p_required=0.85, compliance=1.0, driver="perfect", demand=1.0)
SWEEPS: dict[str, list] = {
    "horizon": [1, 2, 3, 6, 8],
    "p_required": [0.5, 0.7, 0.95, 0.99],
    "compliance": [0.0, 0.25, 0.5, 0.75],
    "driver": ["realistic"],
    "demand": [0.6, 0.8, 1.2, 1.4],
}
ONLY = {"p_required": ("actuated",)}
METRICS = ("stops", "near_stops", "wait", "travel_time", "fuel_g", "broken_promises")


@dataclass(frozen=True)
class Cell:
    """One SUMO run: 51 test vehicles under one configuration and seed."""
    scenario: str              # "fixed" | "actuated"
    factor: str                # "baseline" (drive at limit) | "reference" | a SWEEPS key
    level: object              # the swept value (the reference value for "reference" / "baseline")
    seed: int
    advised: bool = True
    horizon: int = 4
    p_required: float = 0.85
    compliance: float = 1.0
    driver: str = "perfect"
    demand: float = 1.0

    @property
    def key(self) -> str:
        return f"{self.scenario}_{self.factor}_{self.level}_d{self.demand}_s{self.seed}"


def matrix(seeds: list[int]) -> list[Cell]:
    cells = []
    for name in SCENARIOS:
        for seed in seeds:
            for d in [REFERENCE["demand"]] + SWEEPS["demand"]:
                cells.append(Cell(name, "baseline", d, seed, advised=False, demand=d))
            cells.append(Cell(name, "reference", "-", seed))
            for factor, levels in SWEEPS.items():
                if name not in ONLY.get(factor, SCENARIOS):
                    continue
                for lv in levels:
                    cells.append(Cell(name, factor, lv, seed, **{factor: lv}))
    return cells


def demand_levels() -> list[float]:
    return [REFERENCE["demand"]] + SWEEPS["demand"]


def context_dir(root: Path, scenario: str, demand: float) -> Path:
    return root / "build" / "m5" / f"corridor_{scenario}_d{demand}"


def prepare(root: Path, scenario: str, demand: float) -> Path:
    """Build the network at this demand and record the history the system learns from (seed HIST_SEED).
    Returns the sumocfg path; the history is saved next to it."""
    from .sim import corridor
    from .sim.history import collect_history
    out = context_dir(root, scenario, demand)
    path = root / "scenarios" / f"corridor_{scenario}.yaml"
    cfg = corridor.build(path, out, demand_scale=demand)
    hist_path = out / f"history_{HIST_SEED}.json"
    if not hist_path.exists():
        sc = corridor.scale_demand(_load(root, scenario), demand)
        collect_history(sc, cfg, HIST_SEED).save(hist_path)
    return cfg


def _load(root: Path, scenario: str):
    from .scenario import load_scenario
    return load_scenario(root / "scenarios" / f"corridor_{scenario}.yaml")


def run_cell(cell: Cell, root: Path) -> list[dict]:
    """Run one cell (in a worker process: imports SUMO here). Returns one row per arrived test vehicle."""
    from .analysis import broken_promises
    from .optimizer.band import BandConfig
    from .signals.actuated import ActuatedForecaster
    from .signals.fixed_time import FixedTimeForecaster
    from .sim import corridor
    from .sim.ego import REALISTIC, DriverModel, EgoSpec, departure_times, run_corridor
    from .sim.history import SignalHistory
    from .traffic.queue import QueueModel

    out = context_dir(root, cell.scenario, cell.demand)
    cfg = out / "corridor.sumocfg"
    sc = corridor.scale_demand(_load(root, cell.scenario), cell.demand)
    hist = SignalHistory.load(out / f"history_{HIST_SEED}.json")
    fc = ActuatedForecaster(sc, hist) if cell.scenario == "actuated" else FixedTimeForecaster.from_scenario(sc)
    band = BandConfig.for_limit(sc.speed_limit_ms, horizon=cell.horizon, p_required=cell.p_required)
    driver = REALISTIC if cell.driver == "realistic" else DriverModel(compliance=cell.compliance)
    prefix = "adv" if cell.advised else "base"
    egos = [EgoSpec(f"{prefix}_{d}", d, cell.advised) for d in departure_times()]
    res = run_corridor(sc, cfg, egos, fc, seed=cell.seed, queue=QueueModel.from_history(hist),
                       driver=driver, band_cfg=band)
    sl = corridor.eastbound_stop_lines(sc, out / "corridor.net.xml")
    rows = []
    for lg in res.logs.values():
        if lg.arrived:
            m = lg.metrics()
            m["broken_promises"] = broken_promises(lg, sl) if cell.advised else 0
            m.update({k: v for k, v in asdict(cell).items() if k != "advised"}, level=str(cell.level))
            rows.append(m)
    return rows


# ------------------------------------------------------------------ analysis

def bootstrap_ci(x: np.ndarray, reps: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean."""
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(reps, len(x)))].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def paired_effects(trips: pd.DataFrame, metrics=METRICS) -> pd.DataFrame:
    """Per advised configuration and metric: mean, its CI, and the paired difference to drive-at-limit
    (same scenario, demand, seed, departure) with its CI. Rows are tidy (one per configuration x metric)."""
    keys = ["scenario", "demand", "seed", "depart"]
    base = trips[trips.factor == "baseline"][keys + list(metrics)].rename(columns={m: f"{m}_base" for m in metrics})
    rows = []
    for (sc, factor, level), g in trips[trips.factor != "baseline"].groupby(["scenario", "factor", "level"], sort=False):
        j = g.merge(base, on=keys, how="inner")
        for m in metrics:
            d = (j[m] - j[f"{m}_base"]).to_numpy(float)
            lo, hi = bootstrap_ci(j[m].to_numpy(float))
            dlo, dhi = bootstrap_ci(d)
            b = j[f"{m}_base"].mean()
            rows.append(dict(scenario=sc, factor=factor, level=level, metric=m, n=len(j),
                             mean=j[m].mean(), lo=lo, hi=hi, base=b, delta=d.mean(), delta_lo=dlo, delta_hi=dhi,
                             delta_pct=100 * d.mean() / b if b else np.nan))
    return pd.DataFrame(rows)


def vs_reference(trips: pd.DataFrame, metrics=("stops", "travel_time", "fuel_g")) -> pd.DataFrame:
    """Each swept configuration against the reference configuration, paired by scenario, seed and departure.
    Only configurations at nominal demand (other demands have no reference run to pair with)."""
    keys = ["scenario", "demand", "seed", "depart"]
    ref = trips[trips.factor == "reference"][keys + list(metrics)].rename(columns={m: f"{m}_ref" for m in metrics})
    rows = []
    sw = trips[~trips.factor.isin(["baseline", "reference"]) & (trips.demand == REFERENCE["demand"])]
    for (sc, factor, level), g in sw.groupby(["scenario", "factor", "level"], sort=False):
        j = g.merge(ref, on=keys, how="inner")
        for m in metrics:
            d = (j[m] - j[f"{m}_ref"]).to_numpy(float)
            lo, hi = bootstrap_ci(d)
            rows.append(dict(scenario=sc, factor=factor, level=level, metric=m, n=len(j), delta=d.mean(),
                             delta_lo=lo, delta_hi=hi))
    return pd.DataFrame(rows)


def sweep(effects: pd.DataFrame, scenario: str, factor: str, metric: str) -> pd.DataFrame:
    """One factor's sweep including the reference point at its default level, sorted by level."""
    e = effects[(effects.scenario == scenario) & (effects.metric == metric)]
    ref = e[e.factor == "reference"].assign(level=str(REFERENCE[factor]))
    out = pd.concat([e[e.factor == factor], ref])
    out = out.assign(factor=factor)
    try:
        return out.assign(_k=out.level.astype(float)).sort_values("_k").drop(columns="_k")
    except ValueError:            # categorical levels (driver)
        return out.sort_values("level", key=lambda s: s != str(REFERENCE[factor]))
