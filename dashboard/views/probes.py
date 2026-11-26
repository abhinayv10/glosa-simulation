"""Timing from probes (M4): signal timing inferred from ordinary cars' GPS traces, and what the advice loses."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from common import RESULTS, require, theme_mode

from greenwave.viz import charts

RES = RESULTS / "m4"
require(RES / "timing_accuracy.csv", RES / "summary.csv", script="scripts\\m4_probe_inference.py")
acc = pd.read_csv(RES / "timing_accuracy.csv")
summary = pd.read_csv(RES / "summary.csv")
mode = theme_mode()

st.title("Signal timing from probes")
st.caption("No timing sheets, no controller logs: only 1 Hz position reports from a share of ordinary cars. A car "
           "crosses a stop line (or leaves a queue) only on green, so every crossing is a 'green now' sample; "
           "folding samples over candidate cycle lengths reveals the cycle and each signal's green.")

scen = st.radio("Corridor", ["corridor_fixed", "corridor_actuated"], horizontal=True,
                format_func=lambda s: "Fixed-time" if s.endswith("fixed") else "Actuated")
a = acc[acc.scenario == scen]
left, right = st.columns(2)
if scen.endswith("fixed"):
    with left:
        st.subheader("Green start error")
        st.plotly_chart(charts.accuracy_lines(a, "start_mae_s", "Mean error (s)", mode), width="stretch")
    with right:
        st.subheader("Green end error")
        st.plotly_chart(charts.accuracy_lines(a, "end_mae_s", "Mean error (s)", mode), width="stretch")
    st.caption("Error against the timing plan, mean over the 8 signals. Green end comes from the cross street "
               "(its green start minus the intergreen); with too few cross-street probes it falls back to the main "
               "road, which on a well-progressed road ends early.")
else:
    with left:
        st.subheader("Yield point error")
        st.plotly_chart(charts.accuracy_lines(a, "yield_mae_s", "Mean error (s)", mode), width="stretch")
    with right:
        st.subheader("Per-cycle green start error (median)")
        st.plotly_chart(charts.accuracy_lines(a, "start_err_median_s", "Median error (s)", mode), width="stretch")
    st.caption("Error against the controller log of the same run. The yield point (where main green ends) is fixed "
               "in the cycle; each cycle's start varies with cross-street demand and is bracketed from both sides.")

st.subheader("Trips with probe-inferred timing")
s = summary[summary.scenario == scen]
st.plotly_chart(charts.condition_bars(s, "stops", "Stops per trip", mode), width="stretch")
with st.expander("Table views"):
    st.dataframe(s.drop(columns="scenario"), width="stretch", hide_index=True)
    st.dataframe(a.dropna(axis=1, how="all").drop(columns="scenario"), width="stretch", hide_index=True)
