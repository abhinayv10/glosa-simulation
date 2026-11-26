# ADR-0016: Evaluation matrix

- **Status:** accepted
- **Date:** 2026-11-10
- **Milestone:** M5

## Context
M1–M4 each answered one question on one seed. Several dials were left open "for M5": the planning horizon
(ADR-0005), the reliability threshold p (ADR-0009) and driver compliance (ADR-0011). Traffic demand was never
varied. One seed of 51 departures also gives no idea of how much a difference is noise.

## Options considered
1. **Full factorial** (every combination of every dial). With 5 dials of 2–6 levels that is several hundred
   configurations per corridor per seed. Interactions are visible, but most cells answer no question.
2. **One factor at a time around the deployed configuration**, over several seeds. Each sweep answers "what
   if only this were different", which is how each dial would be tuned or argued about. Interactions are not
   measured.
3. **Random / Latin-hypercube sampling** with a fitted response model. Efficient, but harder to read and to
   explain.

## Decision
Option 2.

- **Reference** (the deployed configuration) is the M2 "advised + queue" condition: timing plan (fixed) or
  controller logs | cross demand (actuated), queue model, horizon 4, p 0.85, perfect compliance, nominal
  demand.
- **Sweeps:** horizon {1, 2, 3, 6, 8}; p {0.5, 0.7, 0.95, 0.99} (actuated only: fixed-time windows are exact,
  so p changes nothing); compliance {0, 0.25, 0.5, 0.75}; the realistic driver of M2; demand ×{0.6, 0.8,
  1.2, 1.4}, where all background flows are scaled. Each demand level gets its own learned history (queue
  model, forecaster) and its own drive-at-limit baseline.
- **Seeds:** evaluation seeds 1–5 × 51 departures (ADR-0014) = 255 trips per configuration. History is
  always seed 101.
- **Pairing:** every advised trip is compared with the drive-at-limit trip of the same corridor, demand,
  seed and departure: same background traffic, same signal phase. 95% intervals come from a bootstrap over
  these pairs. Swept configurations are also paired against the reference the same way
  (`results/m5/vs_reference.csv`).
- 220 SUMO runs (11,220 trips) in parallel worker processes, cached per run (~13 min on 12 workers).
  The reference on seed 1 reproduces M2 exactly (0.57 / 0.27 stops).

## Results (scripts/m5_matrix.py; means over 5 seeds × 51 departures)
**Reference vs driving at the limit** (change, 95% CI):

| Corridor | Stops | Travel time | Fuel | Broken promises |
|---|---|---|---|---|
| Fixed | 1.89 → 0.55 (−1.34, −1.46 to −1.21) | +14.7 s (+4.4%) | −6.4 g (−2.9%) | 0 |
| Actuated | 1.50 → 0.26 (−1.24, −1.40 to −1.08) | +14.4 s (+4.7%) | −3.9 g (−1.9%) | 0 |

**Horizon: longer is worse past 3.** Stops per trip:

| Horizon | 1 | 2 | 3 | **4 (ref)** | 6 | 8 |
|---|---|---|---|---|---|---|
| Fixed | 1.03 | 0.28 | 0.28 | **0.55** | 0.81 | 0.89 |
| Actuated | 0.24 | 0.20 | 0.18 | **0.26** | 0.43 | 0.56 |

Horizon 3 vs 4, paired: −0.27 stops (−0.33 to −0.21) fixed, −0.08 (−0.13 to −0.03) actuated; travel time
and fuel within ±1 s / ±0.3 g. Every extra stop is planned (no broken promises), and they are at J5, the
signal deliberately out of progression: 0 J5 stops at horizon 3, 13 at 4, 28 at 8 (seed 1). **Cause:** the
planner gives each candidate one constant speed through every signal in its horizon (ADR-0005). With a long horizon, the speeds that
pass J5 on green meet reds further on at that same speed, so a stop at J5 that re-synchronises with J6–J8
looks cheaper. In reality the controller re-plans after each signal (ADR-0007) and would pick a new speed
for J6–J8; the open-loop evaluation does not know that. Horizon 1 is greedy and fails the other way
(fixed: 1.03 stops).

**p (actuated):** 0.5 gives 0.07 fewer stops than 0.85 (−0.11 to −0.04), the same travel time and fuel,
and no broken promises in 255 trips. On this corridor 0.85 is conservative; the cost of that safety is small.

**Compliance** (share of the advised slow-down the driver applies). Stops per trip:

| Compliance | 0 | 0.25 | 0.5 | 0.75 | 1 |
|---|---|---|---|---|---|
| Fixed | 1.87 | 1.54 | 1.37 | 1.16 | 0.55 |
| Actuated | 1.49 | 1.46 | 0.98 | 0.62 | 0.26 |

Benefit is not proportional: half compliance gives about 40% of the stop reduction (38% fixed, 42%
actuated), and on the actuated corridor a quarter gives almost nothing (−0.04, CI spans 0). A partial
slow-down puts the car at a speed whose arrival times nobody planned. At compliance 0 the advised car matches the
baseline (−0.01 stops, CI spans 0), a check that pairing is sound.

**Realistic driver** (compliance 0.8, ±2 km/h bias, 2 s reaction, imperfect speed keeping): stops −50%
(fixed) / −71% (actuated), the largest fuel saving of any configuration (−6.2% / −6.0%) at +5.4% / +5.6%
travel time. Imperfect speed keeping makes it drive slower on average, which saves fuel on its own.

**Demand:** the benefit shrinks with traffic. Stop reduction fixed −88% at ×0.6 → −46% at ×1.4; actuated
−93% → −74%. Fuel saving fixed −5.1% → −0.8% (CI includes 0 at ×1.4). Queues fill more of each green and the
platoon ahead decides the speed more than the advice does. Broken promises stay at 0–0.008 per trip.

## Consequences
- The benefit is robust in sign: every configuration with compliance ≥ 0.5 reduces stops with an interval
  well clear of zero, and none breaks more than 1 promise in 50 trips.
- **The default horizon of 4 is not the best.** Horizon 3 is better on both corridors at no cost. The
  default is *not* changed here, because M1–M4 results are reported at 4. Two ways forward: set the default
  to 3 and re-run M1–M4 (cheap, empirical), or make the planner aware of re-planning (each segment between
  signals gets its own speed, chosen again at each signal: dynamic programming over signals). The second
  removes the reason long horizons hurt, rather than avoiding it, and would also help where signals are
  closer together than here.
- Compliance matters more than any design dial: a display that drivers follow only half-way delivers about
  40% of the benefit. Advice presentation (M6 and beyond) should aim at full adoption of a
  simple speed, not at precision.
- p = 0.85 can stay until real data (M6): the simulated forecasts are well calibrated, real ones may not be.
- Interactions (e.g. horizon × demand) are not measured; a targeted 2-factor grid is the next step if a dial
  is changed.
- The dashboard (one page per milestone question) reads these results; it never runs SUMO.
