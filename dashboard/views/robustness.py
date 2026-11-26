"""Robustness (M2): queues, actuated signals, imperfect signal knowledge, realistic drivers."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from common import RESULTS, require, theme_mode

from greenwave.viz import charts

RES = RESULTS / "m2"
require(RES / "summary.csv", RES / "forecast_quality.json", script="scripts\\m2_robustness.py")
summary = pd.read_csv(RES / "summary.csv")
fq = pd.DataFrame(json.loads((RES / "forecast_quality.json").read_text())).T
mode = theme_mode()

METRICS = {"Stops per trip": ("stops", ".2f"), "Broken promises per trip": ("broken_promises", ".2f"),
           "Trips with no stop (%)": ("zero_stop_pct", ".0f"), "Waiting at red (s)": ("wait_s", ".1f"),
           "Travel time (s)": ("travel_s", ".1f"), "Fuel (g)": ("fuel_g", ".1f")}

st.title("Robustness")
st.caption("Does the advice survive queues, actuated signals, imperfect signal knowledge and real drivers? "
           "51 departures on evaluation seed 1; the system learned from a different seed (101). "
           "A broken promise is a stop at a signal the advice had planned as green.")

c1, c2 = st.columns([1, 2])
scen = c1.radio("Corridor", ["corridor_fixed", "corridor_actuated"], horizontal=True,
                format_func=lambda s: "Fixed-time" if s.endswith("fixed") else "Actuated")
label = c2.radio("Metric", list(METRICS), horizontal=True)
m, fmt = METRICS[label]
d = summary[summary.scenario == scen]
st.plotly_chart(charts.condition_bars(d, m, label, mode, fmt), width="stretch")
st.caption("Orange: driving at the limit. Blue: advised. Lower is better except for trips with no stop.")

if scen.endswith("actuated"):
    st.subheader("How well each forecaster predicts green starts, 60 s ahead")
    st.dataframe(fq.rename(columns={"windows": "Greens", "start_MAE_s": "Start error, mean (s)",
                                    "start_p90_err_s": "Start error, p90 (s)",
                                    "reliable_start_not_early_%": "Reliable start not early (%)"}).round(2),
                 width="stretch")
    st.caption("The planner only relies on a green once it has started with probability p = 0.85, so the "
               "'reliable start' should be at or after the true start about 85% of the time or more.")

with st.expander("Table view"):
    st.dataframe(d.drop(columns="scenario"), width="stretch", hide_index=True)
