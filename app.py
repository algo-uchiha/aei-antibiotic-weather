"""AEI — Antibiotic weather report. Display only: numbers come from core.py, detect.py and cache/."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import detect

st.set_page_config(page_title="AEI — Antibiotic weather report", layout="wide")
CACHE = Path(__file__).parent / "cache"
FIRST_DAY, LAST_DAY = date(2024, 10, 28), date(2026, 9, 27)
COL = {"green": "#2e7d32", "amber": "#e09b00", "red": "#c62828", "grey": "#aab2bc",
       "purple": "#6a1b9a", "accent": "#1f5fa8"}
LEVEL_COL = {"": COL["green"], "watch": COL["amber"], "warning": COL["red"], "sentinel": COL["purple"]}
LEVEL_TXT = {"": "Clear", "watch": "Watch", "warning": "Warning", "sentinel": "Sentinel"}
ORG_SHORT = {"Escherichia coli": "E. coli", "Klebsiella pneumoniae": "K. pneumoniae",
             "Klebsiella oxytoca": "K. oxytoca", "Proteus mirabilis": "P. mirabilis",
             "Pseudomonas aeruginosa": "P. aeruginosa", "Citrobacter freundii": "C. freundii",
             "Enterococcus faecalis": "E. faecalis", "Staphylococcus aureus": "S. aureus",
             "Staphylococcus saprophyticus": "S. saprophyticus"}

st.markdown("""<style>
.block-container {padding-top: 1.6rem;}
.banner {background:#f3f6fa;border-left:6px solid #1f5fa8;padding:.7rem 1rem;border-radius:6px;
         font-size:1.15rem;margin-bottom:1rem;}
.tile {border-radius:10px;padding:.9rem .8rem;color:white;min-height:96px;margin-bottom:.6rem;}
.tile .w {font-size:1.25rem;font-weight:700;} .tile .s {font-size:.95rem;opacity:.95;}
.card {border:1px solid #dde3ea;border-left-width:8px;border-radius:8px;padding:.8rem 1rem;margin-bottom:.4rem;}
.big {font-size:1.05rem;} .muted {color:#5b6670;font-size:.9rem;}
</style>""", unsafe_allow_html=True)


# ---------- data ----------
@st.cache_resource
def data():
    cul, iso, ast = core.load()
    rd = lambda n: pd.read_parquet(CACHE / f"{n}.parquet")
    return dict(cul=cul, iso=iso, ast=ast, af=ast[ast["first"]], cd=rd("cluster_daily"),
                shift=rd("shift"), sent=rd("sentinel"), lab=rd("lab"), drift=rd("drift"),
                inj=rd("injection"), annual=rd("annual_vs_ward"),
                summary=json.loads((CACHE / "summary.json").read_text()))


D = data()


@st.cache_data(show_spinner=False)
def coverage(asof, days, ward, specimen, sex, age, origin):
    return core.coverage(D["iso"], D["ast"], asof, days=days, ward=ward, specimen=specimen,
                         sex=sex, age=age, origin=origin)


@st.cache_data(show_spinner=False)
def antibiogram(asof, days, ward, specimen, sex, age, origin):
    return core.antibiogram(D["ast"], asof, days, ward=ward, specimen=specimen, sex=sex,
                            age=age, origin=origin)


@st.cache_data(show_spinner=False)
def alarms(asof, level):
    return detect.active_alarms(D["cd"], D["shift"], D["sent"], D["lab"], asof, level)


# ---------- state ----------
ss = st.session_state
ss.setdefault("page", "Home")
ss.setdefault("asof", LAST_DAY)
ss.setdefault("playing", False)
ss.setdefault("play_start", date(2025, 5, 25))
for k, v in dict(p_ward="URO", p_spec="urine", p_sex="ALL", p_age="ALL", p_origin="ALL").items():
    ss.setdefault(k, v)
    ss[k] = ss[k]  # keep filter values when the Prescriber widgets are not on screen

if ss.playing:  # advance the time machine before the slider is drawn
    if ss.asof >= LAST_DAY:
        ss.playing = False
    else:
        ss.asof = ss.asof + timedelta(days=1)


def go_to(p):
    ss.page = p


def start_play():
    ss.asof, ss.playing = ss.play_start, True


def stop_play():
    ss.playing = False


def reset():
    ss.asof, ss.playing = LAST_DAY, False


# ---------- sidebar ----------
with st.sidebar:
    st.markdown("### AEI")
    st.radio("Screen", ["Home", "Prescriber", "Infection control", "Lab & proof"], key="page")
    st.divider()
    st.slider("As-of date", FIRST_DAY, LAST_DAY, key="asof", format="YYYY-MM-DD")
    st.date_input("Replay from", key="play_start", min_value=FIRST_DAY, max_value=LAST_DAY)
    c1, c2, c3 = st.columns(3)
    c1.button("▶ Play", on_click=start_play, width="stretch", disabled=ss.playing)
    c2.button("⏸ Pause", on_click=stop_play, width="stretch", disabled=not ss.playing)
    c3.button("Reset", on_click=reset, width="stretch")
    speed = st.select_slider("Replay speed", ["slow", "normal", "fast"], value="normal")
    st.divider()
    level = st.radio("Alert level shown", ["Watch", "Warning"], horizontal=True).lower()
    st.caption("Synthetic data. In production this module runs nightly inside Mylab My+.")

asof = pd.Timestamp(ss.asof)
active = alarms(asof, level)

# ---------- banner ----------
cov_banner = coverage(asof, 365, ss.p_ward, ss.p_spec, ss.p_sex, ss.p_age, ss.p_origin)
n_warn = sum(a["level"] == "warning" for a in active)
n_watch = sum(a["level"] == "watch" for a in active)
n_sent = sum(a["level"] == "sentinel" for a in active)
n_low = int((cov_banner["mean"] < 0.8).sum())
sent_txt = f" · <b>{n_sent}</b> sentinel" if n_sent else ""
st.markdown(f"## AEI — Antibiotic weather report")
st.markdown(f"<div class='banner'>As of <b>{asof.date()}</b>: <b>{n_warn}</b> warnings · "
            f"<b>{n_watch}</b> watches{sent_txt} · <b>{n_low}</b> drugs below 80% coverage "
            f"<span class='muted'>({ss.p_ward}, {ss.p_spec})</span></div>", unsafe_allow_html=True)


# ---------- shared charts ----------
def pct(x):
    return "–" if x is None or pd.isna(x) else f"{x*100:.0f}%"


def heatmap(ab, title):
    if ab.empty:
        st.info("No isolates in this window.")
        return
    orgs = sorted(ab["organism"].unique())
    drugs = [d for d in detect.DRUG_NAME if d in set(ab["antibiotic_code"])]
    z = np.full((len(orgs), len(drugs)), np.nan)
    text = np.full(z.shape, "", dtype=object)
    hover = np.full(z.shape, "", dtype=object)
    for r in ab.itertuples():
        i, j = orgs.index(r.organism), drugs.index(r.antibiotic_code)
        if r.enough:
            z[i, j] = {"green": 3, "amber": 2, "red": 1}[core.traffic(r.pct)]
            text[i, j] = f"{r.pct*100:.0f}% / n={r.n}"
        else:
            z[i, j] = 0
            text[i, j] = f"<i>{r.shrunk*100:.0f}%</i> / n={r.n}"
        hover[i, j] = (f"{r.organism} · {r.antibiotic_code}<br>%S {r.pct*100:.0f}% "
                       f"(95% CI {r.lo*100:.0f}–{r.hi*100:.0f}%), n={r.n}"
                       + ("" if r.enough else f"<br>n<30: shrunk estimate {r.shrunk*100:.0f}%"))
    scale = [[0, COL["grey"]], [0.25, COL["grey"]], [0.25, COL["red"]], [0.5, COL["red"]],
             [0.5, COL["amber"]], [0.75, COL["amber"]], [0.75, COL["green"]], [1, COL["green"]]]
    fig = go.Figure(go.Heatmap(z=z, x=drugs, y=[ORG_SHORT.get(o, o) for o in orgs], text=text,
                               texttemplate="%{text}", customdata=hover,
                               hovertemplate="%{customdata}<extra></extra>", colorscale=scale,
                               zmin=-0.5, zmax=3.5, showscale=False, xgap=2, ygap=2,
                               textfont=dict(color="white", size=11)))
    fig.update_layout(title=title, height=60 + 34 * len(orgs), margin=dict(l=10, r=10, t=40, b=10),
                      yaxis=dict(autorange="reversed"), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")


# ---------- pages ----------
def home():
    st.markdown("#### Who are you today?")
    cols = st.columns(3)
    roles = [("Prescriber", "Culture pending: what should I give on my ward?"),
             ("Infection control", "Is something spreading?"),
             ("Lab & proof", "Is it real or a lab artefact? Can I trust the alarms?")]
    for c, (name, q) in zip(cols, roles):
        with c:
            st.button(name, on_click=go_to, args=(name,), width="stretch", type="primary")
            st.markdown(f"<div class='big' style='text-align:center'>{q}</div>", unsafe_allow_html=True)
    st.markdown("&nbsp;")
    st.markdown("Tyks publishes antibiotic resistance once a year, for the whole hospital. AEI "
                "recomputes it every night for **your ward**, for the **last 4 weeks and the last "
                "12 months**, and raises a weather-style **Watch** or **Warning** when resistant "
                "bacteria cluster. Move the as-of date or press ▶ Play to watch it update.")


def prescriber():
    st.markdown("#### Culture pending? Chance each drug covers what grows here.")
    c = st.columns(5)
    c[0].selectbox("Ward", ["ALL"] + core.WARDS, key="p_ward")
    c[1].selectbox("Specimen", ["urine", "blood", "wound"], key="p_spec")
    c[2].selectbox("Sex", ["ALL", "F", "M"], key="p_sex")
    c[3].selectbox("Age band", ["ALL"] + core.AGE_BANDS, key="p_age")
    c[4].selectbox("Origin", ["ALL", "community", "hospital"], key="p_origin")
    f = (ss.p_ward, ss.p_spec, ss.p_sex, ss.p_age, ss.p_origin)
    cov12 = coverage(asof, 365, *f)
    cov28 = coverage(asof, 28, *f).set_index("drug")
    if cov12.empty:
        st.info("No isolates match these filters in the last 12 months.")
        return
    n_iso = int(cov12["n_isolates"].iloc[0])
    n28 = int(cov28["n_isolates"].iloc[0]) if len(cov28) else 0
    st.caption(f"Empiric coverage over the last 12 months to {asof.date()}, first isolates only "
               f"(n = {n_iso} isolates; last 28 days n = {n28}). Bar = mean, line = 95% interval. "
               "A drug not reported for an organism counts as not covering it. Cefoxitin is excluded "
               "(MRSA screen).")
    cov12 = cov12.iloc[::-1]
    colors = [COL[core.traffic(m)] for m in cov12["mean"]]
    labels = [f"{detect.DRUG_NAME[d].split(' (')[0]} ({d})" for d in cov12["drug"]]
    fig = go.Figure(go.Bar(
        x=cov12["mean"] * 100, y=labels, orientation="h", marker_color=colors,
        error_x=dict(type="data", symmetric=False, array=(cov12["hi"] - cov12["mean"]) * 100,
                     arrayminus=(cov12["mean"] - cov12["lo"]) * 100, color="#333"),
        text=[f"{m*100:.0f}%  ({lo*100:.0f}–{hi*100:.0f})" for m, lo, hi in
              zip(cov12["mean"], cov12["lo"], cov12["hi"])],
        textposition="inside", insidetextanchor="start", textfont=dict(color="white", size=13),
        name="Last 12 months", hovertemplate="%{y}: %{x:.0f}%<extra>12 months</extra>"))
    if n28 >= 10:
        m28 = [cov28["mean"].get(d, np.nan) * 100 for d in cov12["drug"]]
        fig.add_trace(go.Scatter(x=m28, y=labels, mode="markers", name="Last 28 days",
                                 marker=dict(symbol="diamond", size=12, color="black"),
                                 hovertemplate="%{y}: %{x:.0f}%<extra>28 days</extra>"))
    for x in (80, 90):
        fig.add_vline(x=x, line_dash="dot", line_color="#888")
    fig.update_layout(height=60 + 38 * len(cov12), margin=dict(l=10, r=10, t=10, b=30),
                      xaxis=dict(range=[0, 100], title="% of likely pathogens covered"),
                      legend=dict(orientation="h", y=1.02, x=0), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    if n28 >= 10:
        top = cov12.iloc[::-1].head(5)
        drops = [(d, (cov28["mean"].get(d, np.nan) - m)) for d, m in zip(top["drug"], top["mean"])]
        worst = min(drops, key=lambda t: t[1] if not pd.isna(t[1]) else 0)
        if not pd.isna(worst[1]) and worst[1] <= -0.05:
            st.warning(f"Last 28 days: {detect.DRUG_NAME[worst[0]]} covers "
                       f"{(cov28['mean'][worst[0]])*100:.0f}%, {abs(worst[1])*100:.0f} points below its "
                       f"12-month level (n = {n28} isolates in 28 days).")
    with st.expander("Antibiogram: last 28 days vs last 12 months", expanded=False):
        st.caption("%S per organism × drug, first isolates. Cells with n < 30 are grey and show an "
                   "empirical-Bayes estimate in italics, shrunk toward the hospital 12-month rate.")
        a, b = st.columns(2)
        with a:
            heatmap(antibiogram(asof, 28, *f), "Last 28 days")
        with b:
            heatmap(antibiogram(asof, 365, *f), "Last 12 months")


def ward_status(asof_alarms):
    worst = {w: "" for w in core.WARDS}
    for a in asof_alarms:
        if a["ward"] in worst and detect.LEVEL_RANK[a["level"]] > detect.LEVEL_RANK[worst[a["ward"]]]:
            worst[a["ward"]] = a["level"]
    return worst


def case_chart(ward, ph, height=180):
    x = D["cd"][(D["cd"]["ward"] == ward) & (D["cd"]["phenotype"] == ph) &
                D["cd"]["date"].between(asof - pd.Timedelta(days=90), asof)]
    fig = go.Figure(go.Bar(x=x["date"], y=x["cases"], marker_color=COL["accent"], name="new cases"))
    for lv in ["watch", "warning"]:
        y = x[x["level"] == lv]
        fig.add_trace(go.Scatter(x=y["date"], y=[x["cases"].max() + 0.6] * len(y), mode="markers",
                                 marker=dict(color=LEVEL_COL[lv], size=7), name=LEVEL_TXT[lv]))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                      yaxis=dict(title="cases/day", dtick=1), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch", key=f"cc_{ward}_{ph}")


def rate_chart(organism, drug, specimen, ward, start, height=180, key=None):
    x = D["af"][(D["af"]["organism"] == organism) & (D["af"]["antibiotic_code"] == drug) &
                (D["af"]["specimen"] == specimen)]
    if ward not in (None, "ALL"):
        x = x[x["ward_code"] == ward]
    r = core.rolling_rate(x, start, asof)
    fig = go.Figure([
        go.Scatter(x=r["date"], y=r["hi"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["lo"] * 100, fill="tonexty", fillcolor="rgba(31,95,168,.15)",
                   line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["pct"] * 100, line=dict(color=COL["accent"], width=2),
                   customdata=r["n"], name="%R",
                   hovertemplate="%{x|%Y-%m-%d}: %{y:.0f}% R (n=%{customdata})<extra></extra>")])
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                      yaxis=dict(title="% resistant (28 d)", rangemode="tozero"), plot_bgcolor="white")
    return fig, r


def infection_control():
    st.markdown("#### Ward weather map")
    st.caption(f"Worst alarm that fired in the 14 days up to {asof.date()}. "
               "Amber = Watch, red = Warning, purple = sentinel (VRE/CPE, notifiable).")
    status = ward_status(active)
    cols = st.columns(9)
    for c, w in zip(cols, core.WARDS):
        lv = status[w]
        n = sum(a["ward"] == w for a in active)
        c.markdown(f"<div class='tile' style='background:{LEVEL_COL[lv]}'><div class='w'>{w}</div>"
                   f"<div class='s'>{LEVEL_TXT[lv]}{f' · {n}' if n else ''}</div></div>",
                   unsafe_allow_html=True)
    hosp_wide = [a for a in active if a["ward"] == "ALL"]
    if hosp_wide:
        st.caption(f"Plus {len(hosp_wide)} hospital-wide resistance shift(s), shown below.")
    st.markdown("#### Alarms")
    if not active:
        st.success("No active alarms. Clear skies.")
    for i, a in enumerate(active):
        colr = LEVEL_COL[a["level"]]
        with st.container():
            left, right = st.columns([3, 2])
            with left:
                st.markdown(
                    f"<div class='card' style='border-left-color:{colr}'>"
                    f"<b style='color:{colr}'>{LEVEL_TXT[a['level']].upper()}</b>"
                    f"{'' if a['kind'] == 'SENTINEL' else ' · ' + a['kind']} · "
                    f"{a['ward']} · {a['what']} · last fired {pd.Timestamp(a['date']).date()}"
                    f"<div class='big' style='margin-top:.3rem'>{a['sentence']}</div>"
                    f"<div class='muted' style='margin-top:.3rem'>Lab check: {a['lab']}</div></div>",
                    unsafe_allow_html=True)
            with right:
                if a["kind"] == "SHIFT":
                    fig, _ = rate_chart(a["organism"], a["antibiotic_code"], a["specimen"], a["ward"],
                                        asof - pd.Timedelta(days=365), height=170)
                    st.plotly_chart(fig, width="stretch", key=f"sc{i}")
                elif a["kind"] == "CLUSTER":
                    case_chart(a["ward"], a["phenotype"])


def lab_proof():
    S = D["summary"]
    st.markdown("#### Is the alarm real, and can we trust the detectors?")
    st.caption(f"Validation replay over {S['period'][0]} → {S['period'][1]} (every date with a full "
               "year of baseline). All detectors are compared over this same period.")

    st.markdown("##### (a) Replay timeline")
    c1, c2 = st.columns(2)
    w = c1.selectbox("Ward", core.WARDS, index=core.WARDS.index("URO"), key="lp_w")
    ph = c2.selectbox("Phenotype", detect.CLUSTER_PHENO, format_func=detect.PHENO_LABEL.get, key="lp_p")
    x = D["cd"][(D["cd"]["ward"] == w) & (D["cd"]["phenotype"] == ph) & D["cd"]["evaluated"]]
    fig = go.Figure(go.Bar(x=x["date"], y=x["cases"], name="new cases/day", marker_color=COL["accent"]))
    top = max(x["cases"].max(), 1)
    for name, mask, colr, off in [("3-in-5 rule", x["rule3in5"], "#555", 1.0),
                                  ("Watch", x["level"].isin(["watch", "warning"]), COL["amber"], 1.6),
                                  ("Warning", x["level"] == "warning", COL["red"], 2.2)]:
        y = x[mask]
        fig.add_trace(go.Scatter(x=y["date"], y=[top + off] * len(y), mode="markers", name=name,
                                 marker=dict(color=colr, size=6, symbol="line-ns-open" if off == 1.0 else "circle")))
    fig.add_vline(x=asof, line_dash="dash", line_color="#333")
    fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")

    a, b = st.columns(2)
    with a:
        st.markdown("##### (b) Known clusters: first alert date")
        st.dataframe(pd.DataFrame(S["known_clusters"]).drop(columns=["ward", "phenotype"])
                     .rename(columns={"cluster": "Cluster", "rule_3in5": "3-in-5 rule"}),
                     hide_index=True, width="stretch")
        st.markdown("##### (d) Alarm episodes per year")
        e = S["episodes_per_year"]
        fig = go.Figure(go.Bar(x=list(e), y=list(e.values()), marker_color=COL["accent"],
                               text=[f"{v:.1f}" for v in e.values()], textposition="outside"))
        fig.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                          yaxis=dict(title="episodes / year"))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Episode counts over {S['years']:.1f} years: "
                   + ", ".join(f"{k} {v}" for k, v in S["episodes"].items())
                   + ". Alert days on the same ward × phenotype merge unless >28 quiet days apart.")
    with b:
        st.markdown("##### (c) Spike injection: sensitivity")
        inj = S["injection"]
        fig = go.Figure()
        for det, colr in [("Watch", COL["amber"]), ("Warning", COL["red"]), ("rule_3in5", "#555")]:
            fig.add_trace(go.Bar(name=det.replace("rule_3in5", "3-in-5 rule"), x=[f"k={k}" for k in inj],
                                 y=[inj[k][det]["sensitivity"] * 100 for k in inj], marker_color=colr,
                                 text=[f"{inj[k][det]['sensitivity']*100:.0f}%" for k in inj],
                                 textposition="outside",
                                 customdata=[inj[k][det]["median_delay_days"] for k in inj],
                                 hovertemplate="%{y:.0f}% detected, median delay %{customdata} d<extra></extra>"))
        fig.update_layout(barmode="group", height=300, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis=dict(range=[0, 115], title="% of injected clusters caught"),
                          plot_bgcolor="white", legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, width="stretch")
        n_tr = sum(inj[k]["Watch"]["trials"] for k in inj)
        st.caption(f"{n_tr} trials: k synthetic ESBL (70%) or MRSA patients on a random ward over 14 days, "
                   "start 2025-01-01 → 2026-08-15. Caught = an alarm the injection caused within 28 days. "
                   "Median delay (days): " + "; ".join(
                       f"k={k}: Watch {inj[k]['Watch']['median_delay_days']}, Warning "
                       f"{inj[k]['Warning']['median_delay_days']}, 3-in-5 {inj[k]['rule_3in5']['median_delay_days']}"
                       for k in inj))

    st.markdown("##### (e) The annual report hides the outbreak")
    av = S["annual_vs_ward"]
    r = D["annual"]
    fig = go.Figure([
        go.Scatter(x=r["date"], y=r["hi"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["lo"] * 100, fill="tonexty", fillcolor="rgba(198,40,40,.12)",
                   line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["pct"] * 100, name="Urology, rolling 28 days",
                   line=dict(color=COL["red"], width=2.5), customdata=r["n"],
                   hovertemplate="%{x|%Y-%m-%d}: %{y:.0f}% ESBL (n=%{customdata})<extra></extra>"),
        go.Scatter(x=[r["date"].min(), r["date"].max()], y=[av["annual_hospital_esbl_2025"] * 100] * 2,
                   name="Hospital annual report 2025", line=dict(color="#333", dash="dash", width=2))])
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      yaxis=dict(title="% ESBL among ESBL-capable isolates"),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"The 2025 hospital-level figure is {av['annual_hospital_esbl_2025']*100:.1f}% "
               f"(n = {av['n_2025']} first isolates). Urology's 28-day rate peaks at "
               f"{r['pct'].max()*100:.0f}% in {r.loc[r['pct'].idxmax(), 'date']:%B %Y}.")

    st.markdown("##### (f) Trend: rolling 28-day resistance")
    c = st.columns(4)
    org = c[0].selectbox("Organism", sorted(D["af"]["organism"].unique()),
                         index=sorted(D["af"]["organism"].unique()).index("Escherichia coli"), key="t_o")
    drugs = sorted(D["af"].loc[D["af"]["organism"] == org, "antibiotic_code"].unique())
    drug = c[1].selectbox("Drug", drugs, index=drugs.index("TMP") if "TMP" in drugs else 0, key="t_d")
    specs = sorted(D["af"].loc[(D["af"]["organism"] == org) & (D["af"]["antibiotic_code"] == drug), "specimen"].unique())
    spec = c[2].selectbox("Specimen", specs, index=specs.index("urine") if "urine" in specs else 0, key="t_s")
    ward = c[3].selectbox("Ward", ["ALL"] + core.WARDS, key="t_w")
    fig, _ = rate_chart(org, drug, spec, ward, pd.Timestamp("2023-10-30"), height=320)
    for br in detect.BREAKS:
        fig.add_vline(x=pd.Timestamp(br), line_dash="dash", line_color="#999")
        fig.add_annotation(x=pd.Timestamp(br), y=1, yref="paper", text=f"EUCAST {br[:4]}",
                           showarrow=False, font=dict(size=10, color="#777"), xanchor="left")
    thr = detect.THRESHOLDS.get((org, drug, spec))
    if thr:
        fig.add_hline(y=thr * 100, line_color=COL["red"], line_dash="dot",
                      annotation_text=f"empiric threshold {thr*100:.0f}%", annotation_position="top left")
    st.plotly_chart(fig, width="stretch")
    dr = D["drift"]
    row = dr[(dr["organism"] == org) & (dr["antibiotic_code"] == drug) & (dr["specimen"] == spec)]
    if len(row):
        r0 = row.iloc[0]
        txt = detect.drift_sentence(r0)
        (st.error if r0["alert"] else st.info)(("DRIFT alert: " if r0["alert"] else "No drift alert. ") + txt
                                                + f" (3-year model to {S['period'][1]}, all wards.)")
    else:
        st.info("Too few isolates for a 3-year drift model (needs n ≥ 300 and ≥ 15 resistant).")
    st.caption("Lab check: " + detect.lab_for(D["lab"], f"{org}|{drug}|{spec}", asof))

    st.markdown("##### (g) Download alerts — the integration hook for My+")
    hist = []
    for d in pd.date_range(asof - pd.Timedelta(days=90), asof, freq="7D"):
        hist += [dict(as_of=str(d.date()), **{k: (str(v.date()) if isinstance(v, pd.Timestamp) else v)
                                              for k, v in al.items()}) for al in alarms(d, level)]
    cur = [dict(as_of=str(asof.date()), **{k: (str(v.date()) if isinstance(v, pd.Timestamp) else v)
                                           for k, v in al.items()}) for al in active]
    c1, c2, c3 = st.columns(3)
    c1.download_button("Active alerts (JSON)", json.dumps(cur, indent=2), f"aei_alerts_{asof.date()}.json",
                       "application/json", width="stretch")
    c2.download_button("Active alerts (CSV)", pd.DataFrame(cur).to_csv(index=False),
                       f"aei_alerts_{asof.date()}.csv", "text/csv", width="stretch")
    c3.download_button("Weekly alert history, last 90 days (CSV)", pd.DataFrame(hist).to_csv(index=False),
                       f"aei_alert_history_{asof.date()}.csv", "text/csv", width="stretch")

    st.markdown("##### (h) Method and sources")
    st.markdown("""
**Data rules.** First isolate per patient × organism × specimen, ≥30 days after the previous kept one (CLSI M39).
Hospital-acquired = inpatient sample on hospital day ≥3. Percentages shown only when n ≥ 30; smaller cells show an
empirical-Bayes estimate (S + 10·p_hospital) / (n + 10). Wilson 95% intervals. Cefoxitin is an MRSA screen and is
excluded from treatment views.

**Empiric coverage (WISCA-style).** Organism mix ~ Dirichlet(counts + 1), per-organism %S ~ Beta(S + 1, R + 1),
coverage = Σ mix × %S over 2,000 draws. An organism with no reported result counts as not covered.

**CLUSTER (ESBL, MRSA).** Daily per ward. New phenotype patients (the same patient re-counts after 30 days) in 7- and
28-day windows vs a volume-adjusted expectation from the previous 365 days. Poisson upper tail, Bonferroni ×2.
Watch: p < 0.01 and ≥3 cases. Warning: p < 0.001 and ≥3 cases. **SENTINEL:** any new VRE or CPE patient.
**SHIFT:** %R last 28 days vs previous 365 days (beta-binomial, Benjamini–Hochberg), alert if q < 0.05 and +10 pp.
**DRIFT:** monthly binomial GLM over 3 years, BH, alert if q < 0.05 and ≥ +1.5 pp/year.
**LAB CHECK:** Fisher test 90 days before vs after each 1 January EUCAST version change; p < 0.01 and |Δ| > 5 pp
flags a possible lab/breakpoint effect. **Comparator:** the classic manual rule, ≥3 patients on a ward within 5 days.

**Sources.** Natale et al., WHONET-SaTScan for AMR clusters, *Eurosurveillance* 22(11), 2017
([PMC5356424](https://pmc.ncbi.nlm.nih.gov/articles/PMC5356424)) · Vivli AMR Data Challenge winners
[2024](https://amr.vivli.org/?p=9536) and [2025](https://amr.vivli.org/?p=9987) · CLSI M39 · EUCAST Expected
Resistant Phenotypes v1.2 · THL Finres 2023 (dataset calibration) · ECDC EARS-Net · WISCA: Hebert et al. 2012 ·
Empiric 20% trimethoprim threshold: IDSA/ESCMID cystitis guideline 2010.

*All data are synthetic. In production AEI would run nightly inside Mylab My+ on the lab system's own data.*
""")


{"Home": home, "Prescriber": prescriber, "Infection control": infection_control,
 "Lab & proof": lab_proof}[ss.page]()

if ss.playing:
    time.sleep({"slow": 0.8, "normal": 0.35, "fast": 0.05}[speed])
    st.rerun()
