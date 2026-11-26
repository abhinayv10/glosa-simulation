"""Evaluation matrix (M5): how the advice's benefit depends on each design and deployment dial."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from common import RESULTS, require, theme_mode

from greenwave.evaluation import sweep
from greenwave.viz import charts

RES = RESULTS / "m5"
require(RES / "effects.csv", RES / "meta.json", script="scripts\\m5_matrix.py")
eff = pd.read_csv(RES / "effects.csv", dtype={"level": str})
meta = json.loads((RES / "meta.json").read_text())
mode = theme_mode()

FACTORS = {
    "horizon": ("Planning horizon", "Signals considered per plan"),
    "p_required": ("Reliability threshold p", "Required probability that an uncertain green has started"),
    "compliance": ("Driver compliance", "Share of the advised slow-down drivers apply (0 = ignore advice)"),
    "driver": ("Driver realism", ""),
    "demand": ("Traffic demand", "Background traffic (× nominal)"),
}
METRICS = {"stops": ("Stops per trip", ".2f"), "wait": ("Waiting at red (s)", ".1f"),
           "travel_time": ("Travel time (s)", ".1f"), "fuel_g": ("Fuel (g)", ".1f"),
           "near_stops": ("Near-stops per trip (< 10 km/h)", ".2f"),
           "broken_promises": ("Broken promises per trip", ".3f")}

st.title("Evaluation matrix")
st.caption(f"One dial at a time around the deployed configuration, {len(meta['seeds'])} evaluation seeds × 51 "
           f"departures per point ({meta['trips']:,} trips in all). Every advised trip is compared with the "
           "drive-at-limit trip on the same traffic, seed and departure time; ranges are 95% bootstrap intervals.")

c1, c2 = st.columns([1, 2])
scen = c1.radio("Corridor", ["fixed", "actuated"], horizontal=True, format_func=str.capitalize)
factors = [f for f in FACTORS if (eff[(eff.scenario == scen)].factor == f).any()]
factor = c2.radio("Dial", factors, horizontal=True, format_func=lambda f: FACTORS[f][0])

# ---- headline: the reference configuration
ref = eff[(eff.scenario == scen) & (eff.factor == "reference")].set_index("metric")
st.subheader("Deployed configuration vs driving at the limit")
cols = st.columns(4)
for col, m in zip(cols, ["stops", "wait", "travel_time", "fuel_g"]):
    r = ref.loc[m]
    label, fmt = METRICS[m]
    col.metric(label, f"{r['mean']:{fmt}}", f"{r.delta_pct:+.0f}%", delta_color="inverse")
    col.caption(f"Change {r.delta:+{fmt}} (95% CI {r.delta_lo:+{fmt}} to {r.delta_hi:+{fmt}})")
ref_desc = ("timing plan" if scen == "fixed" else "controller logs | cross demand") + \
    ", queue model, horizon 4, p 0.85, perfect compliance, nominal demand"
st.caption(f"Deployed configuration: {ref_desc}. Broken promises: {ref.loc['broken_promises', 'mean']:.3f} per trip.")

# ---- the sweep
st.divider()
name, x_title = FACTORS[factor]
st.subheader(name)
cat = factor == "driver"
grid = st.columns(2)
for i, m in enumerate(["stops", "travel_time", "fuel_g", "broken_promises"]):
    sw = sweep(eff, scen, factor, m)
    with grid[i % 2]:
        st.plotly_chart(charts.sweep_chart(sw, METRICS[m][0], mode, x_title, categorical=cat,
                                             from_zero=m in ("stops", "broken_promises")), width="stretch")
NOTES = {
    "horizon": "How many signals ahead each plan looks. One signal is greedy; more signals avoid trading a green "
               "now for a stop later, but rely on longer forecasts.",
    "p_required": "The planner relies on an uncertain green start only once it has started with probability p. "
                  "Higher p: fewer broken promises, fewer usable greens. Actuated corridor only (fixed-time "
                  "windows are exact).",
    "compliance": "Drivers who apply only part of the advised slow-down. At 0 the advised car drives at the limit, "
                  "so it matches the baseline.",
    "driver": "Realistic: compliance 0.8, a personal speed bias (±2 km/h), 2 s reaction and imperfect speed keeping.",
    "demand": "All background traffic scaled. The queue model and forecaster are relearned at each demand, and "
              "each demand has its own drive-at-limit baseline (the orange line moves too).",
}
st.caption(NOTES[factor])

# ---- all configurations
st.divider()
st.subheader("All configurations: change vs driving at the limit")
show = eff[eff.scenario == scen].copy()
show["configuration"] = show.apply(lambda r: "reference" if r.factor == "reference"
                                   else f"{FACTORS[r.factor][0]} = {r.level}", axis=1)
piv = show[show.metric.isin(["stops", "wait", "travel_time", "fuel_g"])].pivot_table(
    index="configuration", columns="metric", values="delta_pct", sort=False)
piv = piv.rename(columns={m: f"{METRICS[m][0]} Δ%" for m in piv.columns})
bp = show[show.metric == "broken_promises"].set_index("configuration")["mean"].rename("Broken promises per trip")
st.dataframe(piv.join(bp).round(3), width="stretch")
with st.expander("Table view: every configuration and metric with intervals"):
    st.dataframe(show.drop(columns=["configuration"]).round(3), width="stretch", hide_index=True)
