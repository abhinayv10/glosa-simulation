"""Shared helpers for the dashboard pages."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "results"


def theme_mode() -> str:
    th = getattr(st.context, "theme", None)
    return "dark" if th is not None and th.type == "dark" else "light"


def require(*paths: Path, script: str) -> None:
    """Stop the page with a run hint if a results file is missing."""
    missing = [p for p in paths if not p.exists()]
    if missing:
        st.error(f"No results yet ({missing[0].relative_to(ROOT)}). Run: `.venv\\Scripts\\python.exe {script}`")
        st.stop()


def pct(a: float, b: float) -> str:
    """Change from a to b in percent, for st.metric deltas."""
    return f"{100 * (b - a) / a:+.0f}%" if a else "n/a"
