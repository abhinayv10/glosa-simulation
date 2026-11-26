"""Single trip (M1): one departure, advised vs drive-at-limit, with the time-space diagram and the plan."""
from __future__ import annotations

import pickle

import pandas as pd
import streamlit as st
from common import RESULTS, ROOT, pct, require, theme_mode

from greenwave.optimizer.band import KMH
from greenwave.scenario import load_scenario
from greenwave.signals.fixed_time import FixedTimeForecaster
from greenwave.sim import corridor
from greenwave.viz import charts

RES = RESULTS / "m1"
require(RES / "runs.pkl", RES / "trips.csv", script="scripts\\m1_compare.py")


@st.cache_resource
def load():
    data = pickle.load(open(RES / "runs.pkl", "rb"))
    sc = load_scenario(data["scenario"])
    net = ROOT / "build" / sc.name / "corridor.net.xml"
    return data["runs"], sc, corridor.eastbound_stop_lines(sc, net), FixedTimeForecaster.from_scenario(sc)


runs, sc, stop_lines, fc = load()
df = pd.read_csv(RES / "trips.csv")
mode = theme_mode()

st.title("Single trip")
st.caption(f"Scenario **{sc.name}** · {len(sc.intersections)} fixed-time signals · cycle {sc.timing.cycle_s:.0f}s · "
           f"limit {sc.speed_limit_ms / KMH:.0f} km/h · signal knowledge: exact timing plan · profile: balanced · "
           "no queue model (M1)")

base, adv = df[~df.advised], df[df.advised]
c = st.columns(4)
for col, (m, label, f) in zip(c, [("stops", "Stops per trip", ".2f"), ("wait", "Waiting at red (s)", ".0f"),
                                  ("travel_time", "Travel time (s)", ".0f"), ("fuel_g", "Fuel (g)", ".0f")]):
    col.metric(label, f"{adv[m].mean():{f}}", pct(base[m].mean(), adv[m].mean()), delta_color="inverse")
st.caption(f"Advised vs drive-at-limit, mean over {len(adv)} departures (one every 59 s, each at a different signal "
           "phase). Deltas are relative to driving at the limit; lower is better.")

st.divider()
departs = sorted(int(d) for d in df.depart.unique())
dep = st.select_slider("Departure time (s)", options=departs, value=departs[len(departs) // 2])
pair = {"advised": runs[True].get(f"adv_{dep}"), "drive at limit": runs[False].get(f"base_{dep}")}

left, right = st.columns([3, 2])
with left:
    st.subheader("Time-space diagram")
    st.plotly_chart(charts.time_space(stop_lines, fc, pair, mode), width="stretch")
with right:
    a, b = pair["advised"], pair["drive at limit"]
    ma, mb = a.metrics(), b.metrics()
    st.subheader("This departure")
    st.dataframe(pd.DataFrame({
        "Advised": [ma["stops"], round(ma["wait"]), round(ma["travel_time"]), round(ma["fuel_g"])],
        "Drive at limit": [mb["stops"], round(mb["wait"]), round(mb["travel_time"]), round(mb["fuel_g"])],
    }, index=["Stops", "Waiting (s)", "Travel time (s)", "Fuel (g)"]), width="stretch")
    if a.first_plan is not None:
        st.subheader("Why this speed")
        st.info(a.first_plan.explanation)
        st.plotly_chart(charts.speed_cost(a.first_plan, mode), width="stretch")

with st.expander("Advice log for this trip"):
    st.dataframe(pd.DataFrame([{
        "t (s)": round(r.t, 1), "x (m)": round(r.x), "speed (km/h)": round(r.v / KMH),
        "reason": r.reason,
        "advised (km/h)": f"{r.advised[0] / KMH:.0f}–{r.advised[1] / KMH:.0f}" if r.advised else "limit",
        "planned greens": ", ".join(f"{k}:{'G' if v else 'R'}" for k, v in r.expected.items()),
        "explanation": r.explanation,
    } for r in a.advice]), width="stretch", hide_index=True)

st.divider()
st.subheader("Stops per trip across all departures")
st.plotly_chart(charts.stops_distribution(df, mode), width="stretch")
with st.expander("Table view: all trips"):
    st.dataframe(df, width="stretch", hide_index=True)
