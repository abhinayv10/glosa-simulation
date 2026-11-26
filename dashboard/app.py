"""Streamlit dashboard. Run: .venv\\Scripts\\streamlit run dashboard/app.py

Reads results written by the experiment scripts (scripts/m1_compare.py ... scripts/m5_matrix.py); it does not
run SUMO itself. One page per question.
"""
from __future__ import annotations

import streamlit as st

import common  # noqa: F401  (puts the project root on sys.path for the pages)

st.set_page_config(page_title="Green-Wave Advisory", layout="wide")
nav = st.navigation({
    "Results": [
        st.Page("views/matrix.py", title="Evaluation matrix", icon=":material/grid_view:", default=True),
        st.Page("views/trip.py", title="Single trip", icon=":material/timeline:"),
        st.Page("views/robustness.py", title="Robustness", icon=":material/shield:"),
        st.Page("views/routes.py", title="Route choice & energy", icon=":material/alt_route:"),
        st.Page("views/probes.py", title="Timing from probes", icon=":material/sensors:"),
    ],
})
nav.run()
