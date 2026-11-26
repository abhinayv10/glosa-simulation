"""Route choice & energy (M3): corridor A vs bypass B, ICE vs EV, and the signal-aware route policy."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from common import RESULTS, require, theme_mode

from greenwave.viz import charts

RES = RESULTS / "m3"
require(RES / "options.csv", RES / "policies.csv", script="scripts\\m3_routes.py")
options = pd.read_csv(RES / "options.csv")
policies = pd.read_csv(RES / "policies.csv")
pareto_share = pd.read_csv(RES / "pareto_share.csv") if (RES / "pareto_share.csv").exists() else None
mode = theme_mode()
UNIT = {"ice": ("Fuel (g)", "g"), "ev": ("Battery energy (Wh)", "Wh")}

st.title("Route choice & energy")
st.caption("Route A: the 3.8 km signalised corridor, 50 km/h, 8 signals. Route B: a 6.1 km bypass, 70 km/h, "
           "2 signals. Each point is one route and driving mode, averaged over 51 departures.")

pt = st.radio("Powertrain", ["ice", "ev"], horizontal=True, format_func=lambda p: "Petrol (ICE)" if p == "ice" else "Electric (EV)")
y_title, unit = UNIT[pt]
o = options[options.powertrain == pt]

left, right = st.columns([3, 2])
with left:
    st.subheader("Travel time vs energy")
    st.plotly_chart(charts.pareto(o, "travel_s", "energy", "Travel time (s)", y_title, mode), width="stretch")
    st.caption("Lower-left is better. Points on the dotted line are not beaten on both time and energy by any "
               "other option.")
with right:
    a_lim = o[(o.route == "A") & (o["mode"] == "limit")].iloc[0]
    a_adv = o[(o.route == "A") & (o["mode"] != "limit")].sort_values("energy").iloc[0]
    b_best = o[o.route == "B"].sort_values("energy").iloc[0]
    st.subheader("What the advice is worth")
    c = st.columns(2)
    c[0].metric(f"Energy saved on A ({a_adv['mode']})", f"{100 * (1 - a_adv.energy / a_lim.energy):.0f}%")
    c[1].metric("Bypass B energy vs advised A", f"{100 * (b_best.energy / a_adv.energy - 1):+.0f}%",
                delta_color="off")
    st.caption("An EV gains more from advice than a petrol car: it wastes more by braking and idling costs it "
               "little, so smooth arrival at greens matters most.")

st.divider()
st.subheader("Which route policy is cheapest?")
prof = st.radio("Profile", list(policies.profile.unique()), horizontal=True)
p = policies[(policies.powertrain == pt) & (policies.profile == prof)].copy()
p["condition"] = p.policy
st.plotly_chart(charts.condition_bars(p.sort_values("cost"), "cost",
                                      "Mean cost (equivalent seconds)", mode, ".1f"), width="stretch")
st.caption("Cost combines travel time, stops, waiting and energy (priced by the profile). 'Signal-aware' "
           "predicts both routes at departure from the signal forecasts; 'calibrated' corrects that prediction "
           "with errors learned on a different seed; the oracle knows the outcome.")

with st.expander("Table view"):
    st.dataframe(p.drop(columns=["condition"]), width="stretch", hide_index=True)
    st.dataframe(o, width="stretch", hide_index=True)
    if pareto_share is not None:
        st.caption("Share of departures on which each option is on that departure's Pareto front (%)")
        st.dataframe(pareto_share[pareto_share.powertrain == pt], width="stretch", hide_index=True)
