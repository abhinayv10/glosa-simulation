"""Plotly figures: time-space diagram, speed-vs-cost, stops distribution."""
from __future__ import annotations

import math

import plotly.graph_objects as go

from ..optimizer.band import KMH, Plan
from ..signals.base import SignalForecaster
from ..signals.fixed_time import MAIN_THROUGH
from .theme import STATUS_CRITICAL, STATUS_GOOD, TOKENS, base_layout


def time_space(stop_lines: list[tuple[str, float]], fc: SignalForecaster, trips: dict, mode: str = "light",
               t_range: tuple[float, float] | None = None, show_band: bool = True) -> go.Figure:
    """trips: {"advised": TripLog, "drive at limit": TripLog}. Time on x, distance on y."""
    t = TOKENS[mode]
    logs = [lg for lg in trips.values() if lg is not None and lg.t]
    if t_range is None:
        t_range = (min(lg.t[0] for lg in logs) - 10, max(lg.t[-1] for lg in logs) + 10)
    t0, t1 = t_range
    fig = go.Figure()

    # Signal phases: red/yellow underneath, green on top, as thin bars at each stop line.
    red_x, red_y, grn_x, grn_y = [], [], [], []
    for sid, sx in stop_lines:
        red_x += [t0, t1, None]; red_y += [sx, sx, None]
        for w in fc.green_windows(sid, MAIN_THROUGH, t0, t1):
            grn_x += [max(w.start, t0), min(w.end, t1), None]; grn_y += [sx, sx, None]
    fig.add_trace(go.Scatter(x=red_x, y=red_y, mode="lines", line=dict(color=STATUS_CRITICAL, width=5),
                             name="Signal red / yellow", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grn_x, y=grn_y, mode="lines", line=dict(color=STATUS_GOOD, width=5),
                             name="Signal green", hoverinfo="skip"))

    # Advised band from the first plan, drawn as a fan of constant-speed paths to the last horizon signal.
    adv = trips.get("advised")
    if show_band and adv is not None and adv.advice and adv.advice[0].advised:
        rec = adv.advice[0]
        lo, hi = rec.advised
        horizon_x = max(sx for sid, sx in stop_lines if sid in rec.expected)
        d = horizon_x - rec.x
        fig.add_trace(go.Scatter(
            x=[rec.t, rec.t + d / hi, rec.t + d / lo, rec.t], y=[rec.x, horizon_x, horizon_x, rec.x],
            fill="toself", fillcolor=t["band_fill"], line=dict(width=0), mode="lines",
            name=f"Advised band {lo / KMH:.0f}–{hi / KMH:.0f} km/h (first plan)", hoverinfo="skip"))

    ends = []
    for name, colour in (("drive at limit", t["series2"]), ("advised", t["series1"])):
        lg = trips.get(name)
        if lg is None or not lg.t:
            continue
        kmh = [v / KMH for v in lg.v]
        fig.add_trace(go.Scatter(
            x=lg.t, y=lg.x, mode="lines", line=dict(color=colour, width=2), name=name.capitalize(),
            customdata=kmh, hovertemplate="t=%{x:.0f}s · x=%{y:.0f}m · %{customdata:.0f} km/h<extra>" + name + "</extra>"))
        ends.append((lg.t[-1], lg.x[-1], name))
    # Direct labels at trip ends; both trips end at the same x, so stack them by arrival order.
    for i, (te, xe, name) in enumerate(sorted(ends)):
        fig.add_annotation(x=te, y=xe, text=name, showarrow=False, xanchor="right", xshift=-6,
                           yshift=10 - 22 * i, font=dict(color=t["text2"], size=12))

    # Signal ids in the right margin, clear of the distance tick labels.
    for sid, sx in stop_lines:
        fig.add_annotation(x=1, xref="paper", y=sx, text=sid, showarrow=False, xanchor="left", xshift=6,
                           font=dict(color=t["muted"], size=11))
    fig.update_layout(**base_layout(mode, height=560, hovermode="closest",
                                    margin=dict(l=60, r=40, t=40, b=50)))
    fig.update_xaxes(title="Time (s)", range=[t0, t1])
    fig.update_yaxes(title="Distance along corridor (m)", showticklabels=True)
    return fig


def speed_cost(plan: Plan, mode: str = "light") -> go.Figure:
    """Cost of every candidate speed in a plan, with the chosen feasible band shaded and target marked."""
    t = TOKENS[mode]
    sp = [e.speed / KMH for e in plan.evaluations]
    fig = go.Figure()
    b = plan.best
    fig.add_vrect(x0=b.v_lo / KMH, x1=b.v_hi / KMH, fillcolor=t["band_fill"], line_width=0)
    fig.add_trace(go.Scatter(
        x=sp, y=[e.cost for e in plan.evaluations], mode="lines", line=dict(color=t["series1"], width=2),
        name="Cost J", customdata=[[e.stops, sum(e.pattern), e.travel_time] for e in plan.evaluations],
        hovertemplate="%{x:.1f} km/h · J=%{y:.0f}<br>%{customdata[1]} greens · %{customdata[0]} stops · "
                      "%{customdata[2]:.0f}s<extra></extra>"))
    fig.add_trace(go.Scatter(x=[b.target / KMH], y=[b.centre.cost], mode="markers",
                             marker=dict(size=10, color=t["series1"], line=dict(color=t["surface"], width=2)),
                             name="Advised target", hoverinfo="skip"))
    fig.add_annotation(x=b.target / KMH, y=b.centre.cost, text=f"target {b.target / KMH:.0f} km/h",
                       showarrow=False, yshift=16, font=dict(color=t["text2"], size=12))
    fig.update_layout(**base_layout(mode, height=340, showlegend=False))
    fig.update_xaxes(title="Candidate cruise speed (km/h)")
    fig.update_yaxes(title="Cost J (equivalent seconds)")
    return fig


def stops_distribution(df, mode: str = "light") -> go.Figure:
    t = TOKENS[mode]
    fig = go.Figure()
    max_s = int(df.stops.max())
    for advised, name, colour in ((False, "Drive at limit", t["series2"]), (True, "Advised", t["series1"])):
        counts = df[df.advised == advised].stops.value_counts().reindex(range(max_s + 1), fill_value=0)
        fig.add_trace(go.Bar(x=list(counts.index), y=list(counts.values), name=name, marker_color=colour,
                             hovertemplate="%{x} stops: %{y} trips<extra>" + name + "</extra>"))
    fig.update_layout(**base_layout(mode, height=320, barmode="group", bargap=0.3, bargroupgap=0.08))
    fig.update_xaxes(title="Stops per trip", dtick=1)
    fig.update_yaxes(title="Trips")
    return fig


def condition_bars(summary, metric: str, label: str, mode: str = "light", fmt: str = ".2f") -> go.Figure:
    """One horizontal bar per condition (summary: rows with `condition` and `metric`). Drive-at-limit rows take
    the drive-at-limit colour, advised rows the advised colour, as everywhere else in the dashboard."""
    t = TOKENS[mode]
    d = summary.dropna(subset=[metric]).iloc[::-1]
    limit = d.condition.str.startswith("drive at limit")
    names = d.condition.str.replace("advised: ", "", regex=False)
    fig = go.Figure(go.Bar(
        y=names, x=d[metric], orientation="h", marker_color=[t["series2"] if b else t["series1"] for b in limit],
        text=[f"{v:{fmt}}" for v in d[metric]], textposition="outside", textfont=dict(color=t["text2"]),
        cliponaxis=False, hovertemplate="%{y}<br>" + label + ": %{x:" + fmt + "}<extra></extra>"))
    fig.update_layout(**base_layout(mode, height=60 + 34 * len(d), showlegend=False, bargap=0.35,
                                    margin=dict(l=10, r=60, t=10, b=40)))
    fig.update_xaxes(title=label, rangemode="tozero")
    fig.update_yaxes(automargin=True)
    return fig


def sweep_chart(sw, label: str, mode: str = "light", x_title: str = "", categorical: bool = False,
                from_zero: bool = False) -> go.Figure:
    """One factor sweep for one metric (rows from evaluation.sweep): advised mean with its 95% CI, and the
    drive-at-limit mean on the same traffic. Numeric levels draw lines; categorical levels draw points."""
    t = TOKENS[mode]
    x = list(sw.level) if categorical else [float(v) for v in sw.level]
    fig = go.Figure()
    if not categorical:
        fig.add_trace(go.Scatter(x=x + x[::-1], y=list(sw.hi) + list(sw.lo)[::-1], fill="toself", mode="lines",
                                 fillcolor=t["band_fill"], line=dict(width=0), hoverinfo="skip",
                                 name="Advised, 95% CI"))
    fig.add_trace(go.Scatter(
        x=x, y=sw.base, mode="lines+markers" if not categorical else "markers", name="Drive at limit",
        line=dict(color=t["series2"], width=2, dash="dot"), marker=dict(size=8, color=t["series2"]),
        hovertemplate="%{x}: %{y:.2f}<extra>Drive at limit</extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=sw["mean"], mode="lines+markers" if not categorical else "markers", name="Advised",
        line=dict(color=t["series1"], width=2), marker=dict(size=9, color=t["series1"],
                                                             line=dict(color=t["surface"], width=2)),
        error_y=dict(type="data", symmetric=False, array=sw.hi - sw["mean"], arrayminus=sw["mean"] - sw.lo,
                     color=t["series1"], thickness=1.5, width=4) if categorical else None,
        customdata=list(zip(sw.lo, sw.hi, sw.delta, sw.delta_lo, sw.delta_hi)),
        hovertemplate="%{x}: %{y:.2f} (95% CI %{customdata[0]:.2f}–%{customdata[1]:.2f})<br>"
                      "vs limit %{customdata[2]:+.2f} (%{customdata[3]:+.2f} to %{customdata[4]:+.2f})"
                      "<extra>Advised</extra>"))
    fig.update_layout(**base_layout(mode, height=300, hovermode="closest", margin=dict(l=60, r=20, t=50, b=50),
                                    title=dict(text=label, font=dict(size=14, color=t["text"]), x=0, y=0.98)))
    fig.update_xaxes(title=x_title, type="category" if categorical else "linear")
    if from_zero:
        fig.update_yaxes(rangemode="tozero")
    return fig


def pareto(options, x: str, y: str, x_title: str, y_title: str, mode: str = "light") -> go.Figure:
    """Route x driving-mode options as points (route = colour, mode = direct label); the Pareto front (lower is
    better on both axes) as a line."""
    t = TOKENS[mode]
    fig = go.Figure()
    pts = options.sort_values(x)
    front, best = [], float("inf")
    for _, r in pts.iterrows():
        if r[y] < best:
            front.append(r)
            best = r[y]
    fig.add_trace(go.Scatter(x=[r[x] for r in front], y=[r[y] for r in front], mode="lines", name="Pareto front",
                             line=dict(color=t["muted"], width=1.5, dash="dot"), hoverinfo="skip"))
    # Labels above each point; a point almost on top of an already-labelled one gets its label below instead.
    xr, yr = options[x].max() - options[x].min() or 1, options[y].max() - options[y].min() or 1
    placed, pos = [], {}
    for i, r in options.sort_values(x).iterrows():
        near = any(abs(r[x] - px) < 0.04 * xr and abs(r[y] - py) < 0.06 * yr for px, py in placed)
        pos[i] = "bottom center" if near else "top center"
        placed.append((r[x], r[y]))
    for route, colour in (("A", t["series3"]), ("B", t["series4"])):
        d = options[options.route == route]
        fig.add_trace(go.Scatter(
            x=d[x], y=d[y], mode="markers+text", name=f"Route {route}", text=d["mode"],
            textposition=[pos[i] for i in d.index],
            textfont=dict(color=t["text2"], size=11),
            marker=dict(size=11, color=colour, line=dict(color=t["surface"], width=2)),
            hovertemplate=f"Route {route}, " + "%{text}<br>" + x_title + ": %{x:.1f}<br>" + y_title +
                          ": %{y:.1f}<extra></extra>"))
    fig.update_layout(**base_layout(mode, height=360, hovermode="closest"))
    fig.update_xaxes(title=x_title)
    fig.update_yaxes(title=y_title)
    return fig


def accuracy_lines(acc, y: str, y_title: str, mode: str = "light") -> go.Figure:
    """Timing error vs probe penetration, one line per observation window. Lines converge at high penetration,
    so each is direct-labelled at its first (sparsest) point, where they are furthest apart."""
    t = TOKENS[mode]
    fig = go.Figure()
    colours = [t["series1"], t["series3"], t["series4"]]
    for colour, (w, d) in zip(colours, acc.dropna(subset=[y]).groupby("window_min")):
        d = d.sort_values("rate")
        name = f"{w:.0f} min observed"
        fig.add_trace(go.Scatter(x=100 * d.rate, y=d[y], mode="lines+markers", name=name,
                                 line=dict(color=colour, width=2), marker=dict(size=8, color=colour),
                                 hovertemplate="%{x:.0f}% probes: %{y:.2f} s<extra>" + name + "</extra>"))
        # annotation x on a log axis is given in log10 units
        fig.add_annotation(x=math.log10(100 * d.rate.iloc[0]), y=d[y].iloc[0], text=f"{w:.0f} min", showarrow=False,
                           xanchor="left", xshift=8, font=dict(color=t["text2"], size=11))
    fig.update_layout(**base_layout(mode, height=320))
    fig.update_xaxes(title="Share of cars reporting (%)", type="log", tickvals=[2, 5, 10, 25])
    fig.update_yaxes(title=y_title, rangemode="tozero")
    return fig
