"""AEI — Antibiotic weather report. Display only: numbers come from core.py, detect.py and cache/."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import core
import detect

st.set_page_config(page_title="AEI — Antibiotic weather report", layout="wide")
ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
FIRST_DAY, LAST_DAY = date(2024, 10, 28), date(2026, 9, 27)
PAGES = ["Home", "Prescriber", "Infection control", "Lab & proof"]

# ---------- design tokens ----------
INK, MUTED, LINE, SURFACE, ACCENT = "#111827", "#6B7280", "#E5E7EB", "#F9FAFB", "#0F766E"
STATUS = {"green": "#16A34A", "amber": "#D97706", "red": "#DC2626", "purple": "#7C3AED", "grey": "#9CA3AF"}
STATUS_BG = {"green": "#F0FDF4", "amber": "#FFFBEB", "red": "#FEF2F2", "purple": "#F5F3FF", "grey": "#F3F4F6"}
LEVEL_KEY = {"": "green", "watch": "amber", "warning": "red", "sentinel": "purple"}
LEVEL_TXT = {"": "Clear", "watch": "Watch", "warning": "Warning", "sentinel": "Notifiable"}
KIND_TXT = {"CLUSTER": "Cluster", "SHIFT": "Resistance jump", "SENTINEL": "VRE/CPE case"}
DETECTOR_TXT = {"Watch": "Watch", "Warning": "Warning", "rule_3in5": "Manual rule (3 in 5 days)",
                "SHIFT": "Resistance jump", "SENTINEL": "Notifiable (VRE/CPE)"}
ORG_SHORT = {"Escherichia coli": "E. coli", "Klebsiella pneumoniae": "K. pneumoniae",
             "Klebsiella oxytoca": "K. oxytoca", "Proteus mirabilis": "P. mirabilis",
             "Pseudomonas aeruginosa": "P. aeruginosa", "Citrobacter freundii": "C. freundii",
             "Enterococcus faecalis": "E. faecalis", "Staphylococcus aureus": "S. aureus",
             "Staphylococcus saprophyticus": "S. saprophyticus"}
WARD_FULL = {"ED": "Emergency", "MED-A": "Internal medicine A", "MED-B": "Internal medicine B",
             "SURG": "Surgery", "URO": "Urology", "ICU": "Intensive care", "GER": "Geriatrics",
             "PHC-N": "Health centre North", "PHC-S": "Health centre South", "ALL": "Whole hospital"}

pio.templates["aei"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, system-ui, sans-serif", size=13, color="#374151"),
    paper_bgcolor="white", plot_bgcolor="white", colorway=[ACCENT, "#6B7280", "#9CA3AF"],
    xaxis=dict(showgrid=False, linecolor=LINE, ticks="outside", tickcolor=LINE, zeroline=False,
               title=dict(font=dict(size=13, color=MUTED))),
    yaxis=dict(showgrid=True, gridcolor="#F1F2F4", zeroline=False, linecolor="rgba(0,0,0,0)",
               title=dict(font=dict(size=13, color=MUTED))),
    legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", font=dict(size=13)),
    hoverlabel=dict(font=dict(family="Inter, sans-serif", size=13), bgcolor="white", bordercolor=LINE),
    margin=dict(l=8, r=8, t=36, b=8)))
pio.templates.default = "aei"

st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, .stApp, [class*="st-"], .stMarkdown, button, input, textarea, select {{
  font-family: 'Inter', system-ui, sans-serif !important; }}
[data-testid="stIconMaterial"], [data-testid="stExpanderIcon"], .material-symbols-rounded {{
  font-family: 'Material Symbols Rounded' !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], footer {{ display: none !important; }}
.block-container {{ max-width: 1200px; padding-top: 2.2rem; padding-bottom: 4rem; }}
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.015em; }}
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
.brand {{ display:flex; align-items:baseline; gap:.6rem; margin-bottom:.4rem; }}
.brand b {{ font-size:1.05rem; color:{ACCENT}; font-weight:800; letter-spacing:.02em; }}
.brand span {{ color:{MUTED}; font-size:.95rem; }}
.statusbar {{ display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; margin:.2rem 0 1.4rem;
  color:{MUTED}; font-size:.95rem; }}
.statusbar .date {{ color:{INK}; font-weight:600; margin-right:.3rem; }}
.pill {{ display:inline-flex; align-items:center; gap:.4rem; padding:.22rem .7rem; border-radius:999px;
  font-size:.88rem; font-weight:600; white-space:nowrap; }}
.dot {{ width:.55rem; height:.55rem; border-radius:50%; display:inline-block; flex:none; }}
.hero h1 {{ font-size:3.1rem; line-height:1.06; font-weight:800; letter-spacing:-0.035em; max-width:none;
  margin:.4rem 0 1rem; padding:0; }}
.hero p {{ font-size:1.15rem; max-width:62ch; color:#4B5563; line-height:1.55; }}
.stat {{ border:1px solid {LINE}; border-radius:12px; padding:1.2rem 1.25rem; height:100%; background:white; }}
.stat .v {{ font-size:2.3rem; font-weight:800; letter-spacing:-0.03em; color:{INK}; line-height:1.1; }}
.stat .v small {{ font-size:1.1rem; color:{MUTED}; font-weight:600; letter-spacing:0; }}
.stat .t {{ margin-top:.5rem; color:#4B5563; font-size:.97rem; line-height:1.45; }}
.ward {{ border:1px solid {LINE}; border-left-width:5px; border-radius:12px; padding:.8rem .9rem;
  background:white; margin-bottom:.8rem; min-height:104px; }}
.ward .n {{ font-weight:700; color:{INK}; font-size:1rem; }}
.ward .full {{ color:{MUTED}; font-size:.82rem; margin-bottom:.45rem; }}
.ward .s {{ display:flex; align-items:center; gap:.4rem; font-weight:600; font-size:.92rem; }}
.ward .c {{ color:{MUTED}; font-size:.82rem; margin-top:.2rem; }}
.alarm {{ border:1px solid {LINE}; border-left-width:5px; border-radius:12px; padding:1rem 1.1rem;
  background:white; }}
.alarm .head {{ display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; margin-bottom:.5rem; }}
.alarm .meta {{ color:{MUTED}; font-size:.88rem; }}
.alarm .sent {{ font-size:1.05rem; color:{INK}; line-height:1.5; }}
.alarm .lab {{ margin-top:.6rem; color:#4B5563; font-size:.9rem; }}
.rec {{ font-size:1.15rem; color:{INK}; margin:.4rem 0 .6rem; line-height:1.5; font-weight:500; }}
.cov {{ border:1px solid {LINE}; border-radius:12px; overflow:hidden; background:white; margin-top:.4rem; }}
.cov .row {{ display:grid; grid-template-columns: 2.2fr .9fr 2.2fr 1.1fr 1fr; gap:1.2rem; align-items:center;
  padding:.8rem 1.1rem; border-top:1px solid {LINE}; }}
.cov .row:first-child {{ border-top:none; }}
.cov .hdr {{ color:{MUTED}; font-size:.82rem; font-weight:600; background:{SURFACE}; padding:.55rem 1.1rem; }}
.cov .drug b {{ color:{INK}; font-size:1.02rem; }} .cov .drug div {{ color:{MUTED}; font-size:.84rem; }}
.cov .pct {{ font-size:1.6rem; font-weight:800; letter-spacing:-0.02em; color:{INK}; }}
.ci {{ position:relative; height:8px; background:#F1F2F4; border-radius:4px; }}
.ci .r {{ position:absolute; top:0; height:8px; border-radius:4px; opacity:.35; }}
.ci .m {{ position:absolute; top:-3px; width:3px; height:14px; border-radius:2px; }}
.ci .g {{ position:absolute; top:-4px; width:1px; height:16px; background:#C4C8CE; }}
.ci-l {{ color:{MUTED}; font-size:.78rem; margin-top:.35rem; }}
.d28 {{ font-weight:600; color:{INK}; }} .d28 span {{ font-size:.85rem; font-weight:600; }}
.section {{ margin-top:2.2rem; }}
table.kt {{ width:100%; border-collapse:separate; border-spacing:0; border:1px solid {LINE}; border-radius:12px;
  overflow:hidden; font-size:.92rem; margin-bottom:1.6rem; }}
table.kt th {{ background:{SURFACE}; color:{MUTED}; font-weight:600; text-align:left; padding:.55rem .8rem;
  border:none; white-space:nowrap; }}
table.kt td + td {{ white-space:nowrap; }}
table.kt td {{ padding:.65rem .8rem; border:none; border-top:1px solid {LINE}; color:{INK}; }}
.note {{ color:{MUTED}; font-size:.92rem; line-height:1.5; max-width:90ch; }}
</style>""", unsafe_allow_html=True)


# ---------- data ----------
@st.cache_resource
def data():
    cul, iso, ast = core.load()
    rd = lambda n: pd.read_parquet(CACHE / f"{n}.parquet")
    abx = pd.read_csv(ROOT / "data" / "antibiotics.csv").set_index("antibiotic_code")
    return dict(cul=cul, iso=iso, ast=ast, af=ast[ast["first"]], cd=rd("cluster_daily"),
                shift=rd("shift"), sent=rd("sentinel"), lab=rd("lab"), drift=rd("drift"),
                inj=rd("injection"), annual=rd("annual_vs_ward"), abx=abx,
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
    ss.page = ss.nav = p


def on_nav():
    if ss.nav is None:  # clicking the active segment deselects it; stay put
        ss.nav = ss.page
    ss.page = ss.nav


def start_play():
    ss.asof, ss.playing = ss.play_start, True


def stop_play():
    ss.playing = False


def reset():
    ss.asof, ss.playing = LAST_DAY, False


# ---------- sidebar: time machine ----------
with st.sidebar:
    st.markdown("#### Time machine")
    st.caption("Move the date to see what AEI would have shown that morning.")
    st.slider("As-of date", FIRST_DAY, LAST_DAY, key="asof", format="YYYY-MM-DD")
    st.date_input("Replay from", key="play_start", min_value=FIRST_DAY, max_value=LAST_DAY)
    c1, c2, c3 = st.columns(3)
    c1.button("▶ Play", on_click=start_play, width="stretch", disabled=ss.playing, type="primary")
    c2.button("Pause", on_click=stop_play, width="stretch", disabled=not ss.playing)
    c3.button("Reset", on_click=reset, width="stretch")
    speed = st.select_slider("Replay speed", ["slow", "normal", "fast"], value="normal")
    level = st.radio("Show alarms from", ["Watch", "Warning"], horizontal=True,
                     help="Watch shows everything; Warning hides the lower level.").lower()
    st.caption("Synthetic data. In production AEI runs nightly inside Mylab My+.")

asof = pd.Timestamp(ss.asof)
active = alarms(asof, level)

# ---------- top: brand, navigation, hospital status ----------
st.markdown("<div class='brand'><b>AEI</b><span>Antibiotic weather report</span></div>",
            unsafe_allow_html=True)
if ss.get("nav") is None:
    ss.nav = ss.page
st.segmented_control("Screen", PAGES, key="nav", on_change=on_nav, label_visibility="collapsed")


def pill(key, text):
    return (f"<span class='pill' style='background:{STATUS_BG[key]};color:{STATUS[key]}'>"
            f"<span class='dot' style='background:{STATUS[key]}'></span>{text}</span>")


n_warn = sum(a["level"] == "warning" for a in active)
n_watch = sum(a["level"] == "watch" for a in active)
n_sent = sum(a["level"] == "sentinel" for a in active)
pills = [pill("red", f"{n_warn} warning{'s' * (n_warn != 1)}")] if n_warn else []
pills += [pill("amber", f"{n_watch} watch{'es' * (n_watch != 1)}")] if n_watch else []
pills += [pill("purple", f"{n_sent} notifiable")] if n_sent else []
if not pills:
    pills = [pill("green", "All clear")]
st.markdown(f"<div class='statusbar'><span class='date'>Hospital status on {asof:%-d %B %Y}</span>"
            f"{''.join(pills)}<span>from the last 14 days</span></div>", unsafe_allow_html=True)


# ---------- helpers ----------
def status_key(p):
    return {"green": "green", "amber": "amber", "red": "red"}.get(core.traffic(p), "grey")


def cap(text):
    return text[:1].upper() + text[1:]


def drug_label(code):
    return D["abx"].loc[code, "antibiotic"].replace(" (screen)", "")


def heatmap(ab, title):
    if ab.empty:
        st.info("No isolates in this window. Try a wider filter.")
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
            text[i, j] = f"{r.pct*100:.0f}%<br>n={r.n}"
        else:
            z[i, j] = 0
            text[i, j] = f"<i>{r.shrunk*100:.0f}%</i><br>n={r.n}"
        hover[i, j] = (f"{r.organism}, {drug_label(r.antibiotic_code)}<br>{r.pct*100:.0f}% susceptible "
                       f"(95% CI {r.lo*100:.0f}–{r.hi*100:.0f}%), n={r.n}"
                       + ("" if r.enough else f"<br>Fewer than 30: shrunk estimate {r.shrunk*100:.0f}%"))
    scale = [[0, "#D1D5DB"], [0.25, "#D1D5DB"], [0.25, STATUS["red"]], [0.5, STATUS["red"]],
             [0.5, STATUS["amber"]], [0.75, STATUS["amber"]], [0.75, STATUS["green"]], [1, STATUS["green"]]]
    fig = go.Figure(go.Heatmap(z=z, x=drugs, y=[ORG_SHORT.get(o, o) for o in orgs], text=text,
                               texttemplate="%{text}", customdata=hover,
                               hovertemplate="%{customdata}<extra></extra>", colorscale=scale,
                               zmin=-0.5, zmax=3.5, showscale=False, xgap=3, ygap=3,
                               textfont=dict(color="white", size=12)))
    fig.update_layout(title=dict(text=title, font=dict(size=15, color=INK)), height=90 + 44 * len(orgs),
                      yaxis=dict(autorange="reversed", showgrid=False), xaxis=dict(side="top", ticks=""),
                      margin=dict(l=8, r=8, t=70, b=8))
    st.plotly_chart(fig, width="stretch")


def known_cluster_facts():
    """For each known cluster: whether the first Watch came on the day the 7-day count first reached 3."""
    out = []
    for k in D["summary"]["known_clusters"]:
        w = pd.Timestamp(k["Watch"])
        x = D["cd"][(D["cd"]["ward"] == k["ward"]) & (D["cd"]["phenotype"] == k["phenotype"]) &
                    D["cd"]["date"].between(w - pd.Timedelta(days=1), w)].set_index("date")["obs7"]
        out.append(dict(k, same_day=bool(len(x) == 2 and x.iloc[0] < 3 <= x.iloc[1])))
    return out


# ---------- pages ----------
def home():
    S = D["summary"]
    r = D["annual"]
    peak = r.loc[r["pct"].idxmax()]
    annual = S["annual_vs_ward"]["annual_hospital_esbl_2025"]
    facts = known_cluster_facts()
    windows = [(pd.Timestamp(k["Watch"]) - pd.Timedelta(days=60), pd.Timestamp(k["Watch"]) + pd.Timedelta(days=90))
               for k in S["known_clusters"]]
    stray = [k for k in S["shift_alert_keys"]
             if not any(a <= pd.Timestamp(k["first"]) <= b for a, b in windows)]
    months = round(S["years"] * 12)

    st.markdown("<div class='hero'><h1>Tyks sees resistance once a year.<br>AEI sees it every day, per ward.</h1>"
                "<p>Doctors get this morning's susceptibility for their own ward, over the last 4 weeks and "
                "the last 12 months. Infection control gets a Watch or a Warning the day resistant bacteria "
                "start to cluster.</p></div>", unsafe_allow_html=True)
    c = st.columns(3, gap="medium")
    c[0].markdown(f"<div class='stat'><div class='v'>{peak['pct']*100:.0f}% <small>vs</small> "
                  f"{annual*100:.1f}%</div><div class='t'>ESBL share in Urology at its {peak['date']:%B %Y} "
                  f"peak, against the 2025 hospital-wide annual figure.</div></div>",
                  unsafe_allow_html=True)
    dates = " and ".join(f"{WARD_FULL[k['ward']]} {detect.PHENO_LABEL[k['phenotype']]} on "
                         f"{pd.Timestamp(k['Watch']):%-d %b %Y}" for k in facts)
    lead = ("Each flagged the day its third case arrived" if all(k["same_day"] for k in facts)
            else "Both hidden outbreaks flagged")
    c[1].markdown(f"<div class='stat'><div class='v'>{len(facts)} of {len(facts)} <small>outbreaks</small></div>"
                  f"<div class='t'>{lead}: {dates}.</div></div>", unsafe_allow_html=True)
    c[2].markdown(f"<div class='stat'><div class='v'>{len(stray)} <small>false alarms</small></div>"
                  f"<div class='t'>Resistance-jump alarms outside those two outbreaks, over {months} months "
                  f"of replayed lab data.</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    st.markdown("#### Choose your view")
    roles = [("Prescriber", "Culture pending: what should I give on my ward?", "Open coverage"),
             ("Infection control", "Is something spreading right now?", "Open ward map"),
             ("Lab & proof", "Is it real or a lab artefact? Can I trust the alarms?", "Open the evidence")]
    cols = st.columns(3, gap="medium")
    for col, (name, q, cta) in zip(cols, roles):
        with col:
            with st.container(border=True):
                st.markdown(f"<h3 style='font-size:1.25rem;margin:0;padding:0'>{name}</h3>"
                            f"<p style='color:#4B5563;min-height:3.3em;line-height:1.6;margin:.35rem 0 .2rem'>{q}</p>",
                            unsafe_allow_html=True)
                st.button(cta, key=f"go_{name}", on_click=go_to, args=(name,), type="primary",
                          width="stretch")
    st.markdown("<p class='note' style='margin-top:1.4rem'>Press ▶ Play in the time machine to replay "
                "the Urology outbreak of June 2025 day by day.</p>", unsafe_allow_html=True)


def recommendation(cov):
    good = cov[cov["mean"] >= 0.8]
    best = good.head(2) if len(good) else cov.head(2)
    names = " and ".join(drug_label(d) for d in best["drug"])
    s = (f"Best options here: {names}." if len(good) else
         f"No drug reaches 80% here. Highest coverage: {names}.")
    avoid = cov[(cov["mean"] < 0.8) & (cov["mean"] >= 0.5)].sort_values("mean").head(2)
    if len(avoid):
        s += " Avoid " + " and ".join(f"{drug_label(d)} ({m*100:.0f}%)"
                                     for d, m in zip(avoid["drug"], avoid["mean"])) + "."
    return s


def coverage_rows(cov, cov28, show28):
    rows = ["<div class='cov'><div class='row hdr'><div>Drug</div><div>12 months</div>"
            "<div>95% interval (marks at 80 and 90%)</div><div>Last 28 days</div><div>Status</div></div>"]
    for r in cov.itertuples():
        k = status_key(r.mean)
        label = {"green": "Good", "amber": "Caution", "red": "Avoid"}[k]
        m28 = cov28["mean"].get(r.drug, np.nan) if show28 else np.nan
        if not show28:
            d28 = "<span style='color:#9CA3AF'>too few</span>"
        elif np.isnan(m28):
            d28 = "–"
        else:
            delta = (m28 - r.mean) * 100
            arrow = "↑" if delta > 0 else "↓"
            col = STATUS["red"] if delta <= -5 else STATUS["green"] if delta >= 5 else MUTED
            d28 = f"{m28*100:.0f}% <span style='color:{col}'>{arrow} {abs(delta):.0f}</span>"
        rows.append(
            f"<div class='row'><div class='drug'><b>{cap(drug_label(r.drug))}</b>"
            f"<div>{cap(D['abx'].loc[r.drug, 'class'])}</div></div>"
            f"<div class='pct'>{r.mean*100:.0f}%</div>"
            f"<div><div class='ci'><div class='g' style='left:80%'></div><div class='g' style='left:90%'></div>"
            f"<div class='r' style='left:{r.lo*100:.1f}%;width:{(r.hi-r.lo)*100:.1f}%;background:{STATUS[k]}'></div>"
            f"<div class='m' style='left:calc({r.mean*100:.1f}% - 1px);background:{STATUS[k]}'></div></div>"
            f"<div class='ci-l'>{r.lo*100:.0f}–{r.hi*100:.0f}%</div></div>"
            f"<div class='d28'>{d28}</div>"
            f"<div>{pill(k, label)}</div></div>")
    rows.append("</div>")
    return "".join(rows)


def prescriber():
    st.markdown("### Culture pending? Chance each drug covers what grows here.")
    c = st.columns(5)
    c[0].selectbox("Ward", ["ALL"] + core.WARDS, key="p_ward",
                   format_func=lambda w: f"{w} · {WARD_FULL[w]}" if w != "ALL" else "All wards")
    c[1].selectbox("Specimen", ["urine", "blood", "wound"], key="p_spec", format_func=str.capitalize)
    c[2].selectbox("Sex", ["ALL", "F", "M"], key="p_sex",
                   format_func={"ALL": "Any", "F": "Female", "M": "Male"}.get)
    c[3].selectbox("Age band", ["ALL"] + core.AGE_BANDS, key="p_age",
                   format_func=lambda a: "Any age" if a == "ALL" else a)
    c[4].selectbox("Origin", ["ALL", "community", "hospital"], key="p_origin",
                   format_func={"ALL": "Any", "community": "Community", "hospital": "Hospital-acquired"}.get)
    f = (ss.p_ward, ss.p_spec, ss.p_sex, ss.p_age, ss.p_origin)
    cov = coverage(asof, 365, *f)
    if cov.empty:
        st.info("No isolates match these filters in the last 12 months. Widen the ward or age filter.")
        return
    cov28 = coverage(asof, 28, *f).set_index("drug")
    n_iso = int(cov["n_isolates"].iloc[0])
    n28 = int(cov28["n_isolates"].iloc[0]) if len(cov28) else 0
    show28 = n28 >= 10
    n_low = int((cov["mean"] < 0.8).sum())

    st.markdown(f"<div class='rec'>{recommendation(cov)}</div>", unsafe_allow_html=True)
    tail = (f" and {n28} in the last 28 days" if show28 else
            "; the last 28 days have too few isolates to compare")
    st.markdown(f"<p class='note'>{n_low} of {len(cov)} drugs cover less than 80% of likely pathogens here. "
                f"Based on {n_iso} first isolates in the 12 months to {asof:%-d %b %Y}{tail}. "
                "A drug not reported for an organism counts as not covering it. Cefoxitin is a screen, not a "
                "treatment, and is left out.</p>", unsafe_allow_html=True)
    show_all = st.toggle("Show all drugs, including those under 50%", value=False)
    shown = cov if show_all else cov[cov["mean"] >= 0.5]
    st.markdown(coverage_rows(shown, cov28, show28), unsafe_allow_html=True)
    hidden = len(cov) - len(shown)
    if hidden:
        st.caption(f"{hidden} drug{'s' * (hidden != 1)} under 50% hidden.")

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    with st.expander("Antibiogram: last 28 days vs last 12 months"):
        st.caption("Susceptibility per organism and drug, first isolates only. Grey cells have fewer than 30 "
                   "isolates and show a shrunk estimate in italics.")
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


def case_chart(ward, ph, key):
    x = D["cd"][(D["cd"]["ward"] == ward) & (D["cd"]["phenotype"] == ph) &
                D["cd"]["date"].between(asof - pd.Timedelta(days=90), asof)]
    fig = go.Figure(go.Bar(x=x["date"], y=x["cases"], marker_color="#9CA3AF", name="New patients",
                           hovertemplate="%{x|%-d %b}: %{y}<extra></extra>"))
    for lv in ["watch", "warning"]:
        y = x[x["level"] == lv]
        fig.add_trace(go.Scatter(x=y["date"], y=[x["cases"].max() + 0.7] * len(y), mode="markers",
                                 marker=dict(color=STATUS[LEVEL_KEY[lv]], size=7, symbol="square"),
                                 name=LEVEL_TXT[lv], hoverinfo="skip"))
    fig.update_layout(height=200, margin=dict(l=4, r=4, t=34, b=4),
                      yaxis=dict(title="new patients/day", dtick=1))
    st.plotly_chart(fig, width="stretch", key=key)


def rate_chart(organism, drug, specimen, ward, start, height=200):
    x = D["af"][(D["af"]["organism"] == organism) & (D["af"]["antibiotic_code"] == drug) &
                (D["af"]["specimen"] == specimen)]
    if ward not in (None, "ALL"):
        x = x[x["ward_code"] == ward]
    r = core.rolling_rate(x, start, asof)
    fig = go.Figure([
        go.Scatter(x=r["date"], y=r["hi"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["lo"] * 100, fill="tonexty", fillcolor="rgba(15,118,110,.12)",
                   line=dict(width=0), name="95% interval", hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["pct"] * 100, line=dict(color=ACCENT, width=2.2),
                   customdata=r["n"], name="% resistant, rolling 28 days",
                   hovertemplate="%{x|%-d %b %Y}: %{y:.0f}% resistant (n=%{customdata})<extra></extra>")])
    fig.update_layout(height=height, showlegend=height > 250,
                      yaxis=dict(title="% resistant", rangemode="tozero"))
    return fig


def infection_control():
    st.markdown("### Is something spreading?")
    st.markdown("<p class='note'>Each ward shows its worst alarm from the last 14 days, with the number of "
                "new ESBL and MRSA patients in the last 28 days.</p>", unsafe_allow_html=True)
    status = ward_status(active)
    cd = D["cd"]
    recent = cd[cd["date"].between(asof - pd.Timedelta(days=27), asof)].groupby("ward")["cases"].sum()
    for row in (core.WARDS[:5], core.WARDS[5:]):
        cols = st.columns(5, gap="small")
        for c, w in zip(cols, row):
            lv = status[w]
            k = LEVEL_KEY[lv]
            bg = STATUS_BG[k] if lv in ("warning", "sentinel") else "white"
            n = int(recent.get(w, 0))
            c.markdown(f"<div class='ward' style='border-left-color:{STATUS[k]};background:{bg}'>"
                       f"<div class='n'>{w}</div><div class='full'>{WARD_FULL[w]}</div>"
                       f"<div class='s' style='color:{STATUS[k] if lv else INK}'>"
                       f"<span class='dot' style='background:{STATUS[k]}'></span>{LEVEL_TXT[lv]}</div>"
                       f"<div class='c'>{n} new patient{'s' * (n != 1)}, 28 days</div></div>",
                       unsafe_allow_html=True)
    hosp_wide = [a for a in active if a["ward"] == "ALL"]
    if hosp_wide:
        st.caption(f"Plus {len(hosp_wide)} hospital-wide resistance jump{'s' * (len(hosp_wide) != 1)}, listed below.")

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    st.markdown("#### Active alarms")
    if not active:
        st.success("No alarms in the last 14 days.")
    for i, a in enumerate(active):
        k = LEVEL_KEY[a["level"]]
        left, right = st.columns([3, 2], gap="medium")
        with left:
            st.markdown(
                f"<div class='alarm' style='border-left-color:{STATUS[k]}'><div class='head'>"
                f"{pill(k, LEVEL_TXT[a['level']])}<b>{KIND_TXT[a['kind']]}</b>"
                f"<span class='meta'>{WARD_FULL[a['ward']]}, {a['what']}, last fired "
                f"{pd.Timestamp(a['date']):%-d %b %Y}</span></div>"
                f"<div class='sent'>{a['sentence']}</div>"
                + ("" if a["kind"] == "SENTINEL" else f"<div class='lab'><b>Lab check:</b> {a['lab']}</div>")
                + "</div>", unsafe_allow_html=True)
        with right:
            if a["kind"] == "SHIFT":
                st.plotly_chart(rate_chart(a["organism"], a["antibiotic_code"], a["specimen"], a["ward"],
                                           asof - pd.Timedelta(days=365)), width="stretch", key=f"sc{i}")
            elif a["kind"] == "CLUSTER":
                case_chart(a["ward"], a["phenotype"], key=f"cc{i}")
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)


def lab_proof():
    S = D["summary"]
    st.markdown("### Is the alarm real, and can we trust the detectors?")
    st.markdown(f"<p class='note'>Every number here comes from replaying the lab data day by day from "
                f"{pd.Timestamp(S['period'][0]):%-d %b %Y} to {pd.Timestamp(S['period'][1]):%-d %b %Y}, "
                "the dates with a full year of history behind them. All detectors are compared over this same "
                "period.</p>", unsafe_allow_html=True)

    st.markdown("#### The annual report hides the outbreak")
    av = S["annual_vs_ward"]
    r = D["annual"]
    fig = go.Figure([
        go.Scatter(x=r["date"], y=r["hi"] * 100, line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["lo"] * 100, fill="tonexty", fillcolor="rgba(220,38,38,.10)",
                   line=dict(width=0), name="95% interval", hoverinfo="skip"),
        go.Scatter(x=r["date"], y=r["pct"] * 100, name="Urology, rolling 28 days",
                   line=dict(color=STATUS["red"], width=2.5), customdata=r["n"],
                   hovertemplate="%{x|%-d %b %Y}: %{y:.0f}% ESBL (n=%{customdata})<extra></extra>"),
        go.Scatter(x=[r["date"].min(), r["date"].max()], y=[av["annual_hospital_esbl_2025"] * 100] * 2,
                   name="Hospital annual report, 2025", line=dict(color=INK, dash="dash", width=2),
                   hovertemplate="%{y:.1f}%<extra>annual</extra>")])
    fig.update_layout(height=320, yaxis=dict(title="% ESBL"))
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"<p class='note'>The 2025 hospital figure is {av['annual_hospital_esbl_2025']*100:.1f}% "
                f"(n = {av['n_2025']} first isolates). Urology's 28-day rate peaks at {r['pct'].max()*100:.0f}% "
                f"in {r.loc[r['pct'].idxmax(), 'date']:%B %Y}. Percentages are among species that can carry "
                "ESBL.</p>", unsafe_allow_html=True)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    st.markdown("#### Replay: when each detector fired")
    c1, c2, _ = st.columns([1, 1, 2])
    w = c1.selectbox("Ward", core.WARDS, index=core.WARDS.index("URO"), key="lp_w",
                     format_func=lambda w: f"{w} · {WARD_FULL[w]}")
    ph = c2.selectbox("Phenotype", detect.CLUSTER_PHENO, format_func=detect.PHENO_LABEL.get, key="lp_p")
    x = D["cd"][(D["cd"]["ward"] == w) & (D["cd"]["phenotype"] == ph) & D["cd"]["evaluated"]]
    fig = go.Figure(go.Bar(x=x["date"], y=x["cases"], name="New patients per day", marker_color="#9CA3AF"))
    top = max(x["cases"].max(), 1)
    for name, mask, colr, off in [("Manual rule (3 in 5 days)", x["rule3in5"], "#4B5563", 1.0),
                                  ("Watch", x["level"].isin(["watch", "warning"]), STATUS["amber"], 1.7),
                                  ("Warning", x["level"] == "warning", STATUS["red"], 2.4)]:
        y = x[mask]
        fig.add_trace(go.Scatter(x=y["date"], y=[top + off] * len(y), mode="markers", name=name,
                                 marker=dict(color=colr, size=7, symbol="square"),
                                 hovertemplate="%{x|%-d %b %Y}<extra>" + name + "</extra>"))
    fig.add_vline(x=asof, line_dash="dot", line_color=MUTED)
    fig.update_layout(height=300, yaxis=dict(title="new patients/day"))
    st.plotly_chart(fig, width="stretch")

    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("#### Known outbreaks: first alarm")
        d = lambda v: f"{pd.Timestamp(v):%-d %b %Y}" if v else "not caught"
        rows = "".join(f"<tr><td><b>{k['cluster']}</b></td><td>{d(k['Watch'])}</td><td>{d(k['Warning'])}</td>"
                       f"<td>{d(k['rule_3in5'])}</td></tr>" for k in S["known_clusters"])
        st.markdown(f"<table class='kt'><tr><th>Outbreak</th><th>Watch</th><th>Warning</th>"
                    f"<th>Manual rule</th></tr>{rows}</table>", unsafe_allow_html=True)
        st.markdown("#### Alarms per year")
        e = S["episodes_per_year"]
        labels = [DETECTOR_TXT[k] for k in e]
        colors = [STATUS["amber"], STATUS["red"], "#4B5563", ACCENT, STATUS["purple"]]
        fig = go.Figure(go.Bar(x=list(e.values()), y=labels, orientation="h", marker_color=colors,
                               text=[f"{v:.1f}" for v in e.values()], textposition="outside",
                               hovertemplate="%{y}: %{x:.1f} per year<extra></extra>"))
        fig.update_layout(height=260, yaxis=dict(autorange="reversed", showgrid=False),
                          xaxis=dict(title="episodes per year", showgrid=False, range=[0, max(e.values()) * 1.25]))
        st.plotly_chart(fig, width="stretch")
        st.markdown("<p class='note'>Episodes over " + f"{S['years']:.1f} years: " + ", ".join(
            f"{DETECTOR_TXT[k]} {v}" for k, v in S["episodes"].items()) + ". Alarm days on the same ward and "
            "phenotype count as one episode unless more than 28 quiet days apart.</p>", unsafe_allow_html=True)
    with b:
        st.markdown("#### Injected test outbreaks caught")
        inj = S["injection"]
        fig = go.Figure()
        for det, colr in [("Watch", STATUS["amber"]), ("Warning", STATUS["red"]), ("rule_3in5", "#4B5563")]:
            fig.add_trace(go.Bar(name=DETECTOR_TXT[det], x=[f"{k} patients" for k in inj],
                                 y=[inj[k][det]["sensitivity"] * 100 for k in inj], marker_color=colr,
                                 text=[f"{inj[k][det]['sensitivity']*100:.0f}%" for k in inj],
                                 textposition="outside",
                                 customdata=[inj[k][det]["median_delay_days"] for k in inj],
                                 hovertemplate="%{y:.0f}% caught, median %{customdata} days<extra></extra>"))
        fig.update_layout(barmode="group", height=320, yaxis=dict(range=[0, 118], title="% caught"))
        st.plotly_chart(fig, width="stretch")
        n_tr = sum(inj[k]["Watch"]["trials"] for k in inj)
        st.markdown(f"<p class='note'>{n_tr} trials. Each adds 3, 5 or 8 synthetic ESBL (70%) or MRSA "
                    "patients to a random ward over 14 days, starting between 1 Jan 2025 and 15 Aug 2026. "
                    "It counts as caught if the injection itself triggers an alarm within 28 days. Median days "
                    "to alarm: " + "; ".join(
                        f"{k} patients: Watch {inj[k]['Watch']['median_delay_days']:g}, Warning "
                        f"{inj[k]['Warning']['median_delay_days']:g}, manual rule "
                        f"{inj[k]['rule_3in5']['median_delay_days']:g}" for k in inj) + ".</p>",
                    unsafe_allow_html=True)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    st.markdown("#### Resistance trend")
    c = st.columns(4)
    orgs = sorted(D["af"]["organism"].unique())
    org = c[0].selectbox("Organism", orgs, index=orgs.index("Escherichia coli"), key="t_o")
    drugs = sorted(D["af"].loc[D["af"]["organism"] == org, "antibiotic_code"].unique())
    drug = c[1].selectbox("Drug", drugs, index=drugs.index("TMP") if "TMP" in drugs else 0, key="t_d",
                          format_func=lambda d: cap(drug_label(d)))
    specs = sorted(D["af"].loc[(D["af"]["organism"] == org) & (D["af"]["antibiotic_code"] == drug), "specimen"].unique())
    spec = c[2].selectbox("Specimen", specs, index=specs.index("urine") if "urine" in specs else 0, key="t_s",
                          format_func=str.capitalize)
    ward = c[3].selectbox("Ward", ["ALL"] + core.WARDS, key="t_w",
                          format_func=lambda w: "All wards" if w == "ALL" else f"{w} · {WARD_FULL[w]}")
    fig = rate_chart(org, drug, spec, ward, pd.Timestamp("2023-10-30"), height=340)
    for br in detect.BREAKS:
        fig.add_vline(x=pd.Timestamp(br), line_dash="dash", line_color="#D1D5DB")
        fig.add_annotation(x=pd.Timestamp(br), y=0.98, yref="paper", text=f" EUCAST {br[:4]}",
                           showarrow=False, font=dict(size=12, color=MUTED), xanchor="left", yanchor="top")
    thr = detect.THRESHOLDS.get((org, drug, spec))
    if thr:
        fig.add_hline(y=thr * 100, line_color=STATUS["red"], line_dash="dot",
                      annotation_text=f"Empiric-use threshold {thr*100:.0f}%", annotation_position="bottom left",
                      annotation_font=dict(color=STATUS["red"], size=12))
    fig.update_layout(margin=dict(l=8, r=8, t=56, b=8))
    st.plotly_chart(fig, width="stretch")
    dr = D["drift"]
    row = dr[(dr["organism"] == org) & (dr["antibiotic_code"] == drug) & (dr["specimen"] == spec)]
    if len(row):
        r0 = row.iloc[0]
        (st.error if r0["alert"] else st.info)(("Slow drift alarm. " if r0["alert"] else "No slow drift. ")
                                                + detect.drift_sentence(r0)
                                                + f" Three-year model to {pd.Timestamp(S['period'][1]):%-d %b %Y}, all wards.")
    else:
        st.info("Too few isolates for a three-year drift model (needs at least 300, with 15 resistant).")
    st.markdown(f"<p class='note'><b>Lab check:</b> {detect.lab_for(D['lab'], f'{org}|{drug}|{spec}', asof)}</p>",
                unsafe_allow_html=True)

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    st.markdown("#### Download alerts for My+")
    st.markdown("<p class='note'>The same alarms as structured data, ready for the lab system to pick up.</p>",
                unsafe_allow_html=True)
    fmt = lambda al, d: dict(as_of=str(d.date()), **{k: (str(v.date()) if isinstance(v, pd.Timestamp) else v)
                                                     for k, v in al.items()})
    hist = [fmt(al, d) for d in pd.date_range(asof - pd.Timedelta(days=90), asof, freq="7D")
            for al in alarms(d, level)]
    cur = [fmt(al, asof) for al in active]
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download active alerts (JSON)", json.dumps(cur, indent=2),
                       f"aei_alerts_{asof.date()}.json", "application/json", width="stretch")
    c2.download_button("Download active alerts (CSV)", pd.DataFrame(cur).to_csv(index=False),
                       f"aei_alerts_{asof.date()}.csv", "text/csv", width="stretch")
    c3.download_button("Download 90-day history (CSV)", pd.DataFrame(hist).to_csv(index=False),
                       f"aei_alert_history_{asof.date()}.csv", "text/csv", width="stretch")

    st.markdown("<div class='section'></div>", unsafe_allow_html=True)
    with st.expander("Method and sources", expanded=False):
        st.markdown("""
**Data rules.** First isolate per patient, organism and specimen, at least 30 days after the previous kept one
(CLSI M39). Hospital-acquired means an inpatient sample on hospital day 3 or later. Percentages are shown only
when n ≥ 30; smaller cells show an empirical-Bayes estimate (S + 10·p_hospital) / (n + 10). Wilson 95% intervals.
Cefoxitin is an MRSA screen and is left out of treatment views.

**Empiric coverage (WISCA-style).** Organism mix ~ Dirichlet(counts + 1), per-organism susceptibility
~ Beta(S + 1, R + 1), coverage = Σ mix × susceptibility over 2,000 draws. An organism with no reported result
counts as not covered.

**Cluster (ESBL, MRSA).** Daily per ward. New phenotype patients (the same patient counts again after 30 days) in
7- and 28-day windows, against a volume-adjusted expectation from the previous 365 days. Poisson upper tail,
Bonferroni ×2. Watch: p < 0.01 and at least 3 cases. Warning: p < 0.001 and at least 3 cases.
**Notifiable (VRE/CPE):** any new patient. **Resistance jump:** % resistant in the last 28 days against the
previous 365 days (beta-binomial, Benjamini–Hochberg); alarm if q < 0.05 and +10 points.
**Slow drift:** monthly binomial GLM over 3 years, Benjamini–Hochberg; alarm if q < 0.05 and +1.5 points a year.
**Lab check:** Fisher test 90 days before against 90 days after each 1 January EUCAST change; p < 0.01 and a
step over 5 points flags a possible lab or breakpoint effect. **Manual rule:** 3 patients on a ward within 5 days.

**Sources.** Natale et al., WHONET-SaTScan for AMR clusters, *Eurosurveillance* 22(11), 2017
([PMC5356424](https://pmc.ncbi.nlm.nih.gov/articles/PMC5356424)). Vivli AMR Data Challenge winners
[2024](https://amr.vivli.org/?p=9536) and [2025](https://amr.vivli.org/?p=9987). CLSI M39. EUCAST Expected
Resistant Phenotypes v1.2. THL Finres 2023 (dataset calibration). ECDC EARS-Net. WISCA: Hebert et al. 2012.
Empiric 20% trimethoprim threshold: IDSA/ESCMID cystitis guideline 2010.

*All data are synthetic. In production AEI would run nightly inside Mylab My+ on the lab system's own data.*
""")


{"Home": home, "Prescriber": prescriber, "Infection control": infection_control,
 "Lab & proof": lab_proof}[ss.page]()

if ss.playing:
    time.sleep({"slow": 0.8, "normal": 0.35, "fast": 0.05}[speed])
    st.rerun()
