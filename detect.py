"""Detectors: CLUSTER, SENTINEL, SHIFT, DRIFT, LAB CHECK, rule_3in5, episodes, alert sentences.
Parameters are the validated ones from CLAUDE.md; do not tune them here."""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import betabinom, fisher_exact, poisson

WINDOWS = (7, 28)
BASE_DAYS = 365
DEDUP_DAYS = 30
WATCH_P, WARNING_P, MIN_CASES = 0.01, 0.001, 3
SHIFT_MIN_RECENT, SHIFT_MIN_BASE, SHIFT_Q, SHIFT_PP = 8, 30, 0.05, 0.10
DRIFT_MIN_N, DRIFT_MIN_R, DRIFT_Q, DRIFT_PP = 300, 15, 0.05, 0.015
EPISODE_GAP = 28
BREAKS = ["2024-01-01", "2025-01-01", "2026-01-01"]  # EUCAST version changes
LAB_P, LAB_PP = 0.01, 0.05
THRESHOLDS = {("Escherichia coli", "TMP", "urine"): 0.20,
              ("Escherichia coli", "CIP", "urine"): 0.10,
              ("Escherichia coli", "CRO", "blood"): 0.10}
CLUSTER_PHENO = ["esbl", "mrsa"]
SENTINEL_PHENO = ["vre", "cpe"]
PHENO_LABEL = {"esbl": "ESBL", "mrsa": "MRSA", "vre": "VRE", "cpe": "CPE"}
PHENO_ORGS = {"esbl": None, "mrsa": ["Staphylococcus aureus"], "vre": None, "cpe": None}


def bh(p):
    """Benjamini–Hochberg q-values."""
    p = np.asarray(p, float)
    if len(p) == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1)
    out = np.empty_like(q)
    out[order] = q
    return out


# ---------- phenotype case events ----------

def case_events(iso, phenotype, dedup_days=DEDUP_DAYS):
    """Distinct new phenotype patients per ward: the same patient on the same ward counts
    again only after dedup_days since their last counted case."""
    d = iso.loc[iso[phenotype] == 1, ["ward_code", "patient_id", "sample_date"]]
    d = d.sort_values(["ward_code", "patient_id", "sample_date"]).reset_index(drop=True)
    keep, last = [], {}
    for w, p, t in d.itertuples(index=False):
        prev = last.get((w, p))
        if prev is None or (t - prev).days >= dedup_days:
            keep.append(True)
            last[(w, p)] = t
        else:
            keep.append(False)
    return d[keep].reset_index(drop=True)


# ---------- CLUSTER and rule_3in5 ----------

def _wsum(cum, t, w):
    """Sum of daily values over (t-w, t] given cum = concat([0], cumsum)."""
    return cum[t + 1] - cum[np.maximum(t + 1 - w, 0)]


def cluster_daily(cases, cultures, start, end, ward, phenotype):
    """Daily CLUSTER and rule_3in5 for one ward × phenotype.
    cases: Series of case dates; cultures: Series of culture dates (this ward)."""
    days = pd.date_range(start, end, freq="D")
    D = len(days)
    idx = lambda s: ((s - days[0]).dt.days).values
    c = np.bincount(idx(cases), minlength=D)[:D] if len(cases) else np.zeros(D, int)
    v = np.bincount(idx(cultures), minlength=D)[:D] if len(cultures) else np.zeros(D, int)
    cc, cv = np.concatenate([[0], np.cumsum(c)]), np.concatenate([[0], np.cumsum(v)])
    t = np.arange(D)
    ok = t - WINDOWS[-1] - BASE_DAYS + 1 >= 0  # a full year of baseline before the 28-day window
    tb = np.where(ok, t - WINDOWS[-1], 0)  # baseline (t-28-365, t-28]
    base_cases, base_cult = _wsum(cc, tb, BASE_DAYS), _wsum(cv, tb, BASE_DAYS)
    out = pd.DataFrame({"date": days, "ward": ward, "phenotype": phenotype, "cases": c,
                        "cultures": v, "evaluated": ok})
    pmin = np.ones(D)
    obs_at_min = np.zeros(D, int)
    rate = (base_cases + 0.5) / np.maximum(base_cult, 1)
    for w in WINDOWS:
        obs, vol = _wsum(cc, t, w), _wsum(cv, t, w)
        exp = rate * vol
        p = poisson.sf(obs - 1, np.maximum(exp, 1e-12))
        out[f"obs{w}"], out[f"exp{w}"] = obs, exp
        better = p < pmin
        obs_at_min = np.where(better, obs, obs_at_min)
        pmin = np.minimum(pmin, p)
    out["p"] = np.minimum(pmin * 2, 1)
    out["obs_sel"] = obs_at_min
    level = np.where((out["p"] < WARNING_P) & (obs_at_min >= MIN_CASES), "warning",
                     np.where((out["p"] < WATCH_P) & (obs_at_min >= MIN_CASES), "watch", ""))
    out["level"] = np.where(ok, level, "")
    out["rule3in5"] = ok & (_wsum(cc, t, 5) >= 3)
    return out


def all_cluster_daily(cul, iso, start, end):
    frames = []
    for ph in CLUSTER_PHENO:
        ev = case_events(iso, ph)
        for w in sorted(cul["ward_code"].unique()):
            frames.append(cluster_daily(ev.loc[ev["ward_code"] == w, "sample_date"],
                                        cul.loc[cul["ward_code"] == w, "sample_date"],
                                        start, end, w, ph))
    return pd.concat(frames, ignore_index=True)


# ---------- SENTINEL ----------

def sentinel_events(iso):
    frames = []
    for ph in SENTINEL_PHENO:
        ev = case_events(iso, ph)
        ev["phenotype"] = ph
        frames.append(ev)
    return pd.concat(frames, ignore_index=True).rename(columns={"ward_code": "ward",
                                                               "sample_date": "date"})


# ---------- episodes ----------

def episodes(dates, gap=EPISODE_GAP):
    """Merge alert dates into episodes unless separated by more than `gap` quiet days.
    Returns list of (start, end)."""
    dates = sorted(pd.to_datetime(pd.Series(dates)).unique())
    eps = []
    for d in dates:
        if eps and (d - eps[-1][1]).days - 1 <= gap:
            eps[-1][1] = d
        else:
            eps.append([d, d])
    return [tuple(e) for e in eps]


# ---------- SHIFT ----------

def shift_test(ast_first, asof):
    """%R last 28 days vs the previous 365 days per organism × antibiotic × specimen × ward
    (each ward and ALL). Beta-binomial upper tail, BH across all tests."""
    asof = pd.Timestamp(asof)
    r0, b0 = asof - pd.Timedelta(days=28), asof - pd.Timedelta(days=28 + BASE_DAYS)
    d = ast_first[(ast_first["sample_date"] > b0) & (ast_first["sample_date"] <= asof)]
    d = d.assign(recent=d["sample_date"] > r0)
    keys = ["organism", "antibiotic_code", "specimen"]
    g = pd.concat([d.groupby(keys + ["ward_code", "recent"])["R"].agg(["sum", "count"]),
                   d.assign(ward_code="ALL").groupby(keys + ["ward_code", "recent"])["R"]
                   .agg(["sum", "count"])]).unstack("recent", fill_value=0)
    g.columns = [f"{a}_{'rec' if b else 'base'}" for a, b in g.columns]
    g = g.reindex(columns=["sum_base", "count_base", "sum_rec", "count_rec"], fill_value=0)
    g = g[(g["count_rec"] >= SHIFT_MIN_RECENT) & (g["count_base"] >= SHIFT_MIN_BASE)].reset_index()
    g = g.rename(columns={"ward_code": "ward", "sum_base": "R_base", "count_base": "n_base",
                          "sum_rec": "R_rec", "count_rec": "n_rec"})
    a = g["R_base"] + 0.5
    b = g["n_base"] - g["R_base"] + 0.5
    g["p"] = betabinom.sf(g["R_rec"] - 1, g["n_rec"], a, b)
    g["q"] = bh(g["p"].values)
    g["pR_base"], g["pR_rec"] = g["R_base"] / g["n_base"], g["R_rec"] / g["n_rec"]
    g["alert"] = (g["q"] < SHIFT_Q) & (g["pR_rec"] - g["pR_base"] >= SHIFT_PP)
    g["date"] = asof
    return g


# ---------- DRIFT ----------

def drift(ast_first, asof, years=3):
    """Monthly binomial GLM of R on time per organism × antibiotic × specimen."""
    asof = pd.Timestamp(asof)
    d = ast_first[(ast_first["sample_date"] > asof - pd.DateOffset(years=years)) &
                  (ast_first["sample_date"] <= asof)]
    d = d.assign(month=d["sample_date"].dt.to_period("M"))
    rows = []
    for (org, ab, sp), x in d.groupby(["organism", "antibiotic_code", "specimen"]):
        n, R = len(x), int(x["R"].sum())
        if n < DRIFT_MIN_N or R < DRIFT_MIN_R:
            continue
        m = x.groupby("month")["R"].agg(["sum", "count"])
        tyear = np.array([(p.start_time - asof).days / 365.25 for p in m.index])
        X = sm.add_constant(tyear)
        fit = sm.GLM(np.column_stack([m["sum"], m["count"] - m["sum"]]), X,
                     family=sm.families.Binomial()).fit()
        b0, b1 = fit.params
        expit = lambda z: 1 / (1 + np.exp(-z))
        now, year_ago = expit(b0), expit(b0 - b1)
        rows.append(dict(organism=org, antibiotic_code=ab, specimen=sp, n=n, R=R,
                         logit_slope=b1, p=fit.pvalues[1], now=now,
                         pp_per_year=now - year_ago, raw_now=None))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q"] = bh(out["p"].values)
    out["alert"] = (out["q"] < DRIFT_Q) & (out["pp_per_year"] >= DRIFT_PP)
    out["threshold"] = [THRESHOLDS.get((o, a, s)) for o, a, s in
                        zip(out["organism"], out["antibiotic_code"], out["specimen"])]
    out["threshold_status"] = [_threshold_status(r) for r in out.itertuples()]
    return out.drop(columns="raw_now")


def _threshold_status(r):
    if r.threshold is None or (isinstance(r.threshold, float) and np.isnan(r.threshold)):
        return ""
    if r.now >= r.threshold:
        return "crossed"
    if r.logit_slope <= 0:
        return "not rising"
    logit = lambda p: np.log(p / (1 - p))
    months = (logit(r.threshold) - logit(r.now)) / r.logit_slope * 12
    return f"~{months:.0f} months to threshold"


# ---------- LAB CHECK ----------

def lab_check_rows(events, asof, label):
    """events: DataFrame with sample_date and binary column 'R'. Fisher test 90 days before vs
    90 days after each EUCAST change up to asof."""
    asof = pd.Timestamp(asof)
    rows = []
    for br in BREAKS:
        br = pd.Timestamp(br)
        if br > asof:
            continue
        pre = events[(events["sample_date"] >= br - pd.Timedelta(days=90)) & (events["sample_date"] < br)]
        post = events[(events["sample_date"] >= br) & (events["sample_date"] < min(br + pd.Timedelta(days=90), asof + pd.Timedelta(days=1)))]
        if len(pre) == 0 or len(post) == 0:
            continue
        a, b = int(pre["R"].sum()), len(pre)
        c, d = int(post["R"].sum()), len(post)
        _, p = fisher_exact([[a, b - a], [c, d - c]])
        rows.append(dict(key=label, break_date=br.date().isoformat(), pre=a / b, post=c / d,
                         n_pre=b, n_post=d, delta=c / d - a / b, p=p))
    return rows


def lab_verdict(rows):
    flagged = [r for r in rows if r["p"] < LAB_P and abs(r["delta"]) > LAB_PP]
    if flagged:
        r = flagged[0]
        return (f"Possible lab/breakpoint effect — check with the lab "
                f"({r['delta']*100:+.0f} pp step at {r['break_date']}).")
    return "No step at breakpoint changes → looks biological."


def phenotype_events(iso_first, phenotype):
    """For the lab check of a phenotype alarm: phenotype share among the organisms that carry it."""
    orgs = PHENO_ORGS.get(phenotype)
    if orgs is None:
        orgs = iso_first.loc[iso_first[phenotype] == 1, "organism"].unique()
    x = iso_first[iso_first["organism"].isin(orgs)]
    return x[["sample_date", "ward_code"]].assign(R=x[phenotype].values)


# ---------- sentences ----------

WARD_NAME = {"ED": "the Emergency department", "MED-A": "Internal medicine A",
             "MED-B": "Internal medicine B", "SURG": "Surgery", "URO": "Urology", "ICU": "the ICU",
             "GER": "Geriatrics", "PHC-N": "Health centre North", "PHC-S": "Health centre South",
             "ALL": "the whole hospital area"}
DRUG_NAME = {"AMP": "ampicillin", "MEC": "mecillinam", "TZP": "piperacillin-tazobactam",
             "FOX": "cefoxitin (MRSA screen)", "CXM": "cefuroxime", "CRO": "ceftriaxone",
             "CAZ": "ceftazidime", "MEM": "meropenem", "CIP": "ciprofloxacin",
             "TMP": "trimethoprim", "NIT": "nitrofurantoin", "VAN": "vancomycin",
             "CLI": "clindamycin"}


def cluster_sentence(row):
    w = 28 if row["obs28"] == row["obs_sel"] and row["exp28"] > 0 else 7
    obs, exp = int(row[f"obs{w}"]), row[f"exp{w}"]
    period = "last 4 weeks" if w == 28 else "last 7 days"
    ratio = obs / exp if exp > 0 else float("inf")
    exp_s = f"{exp:.1f}" if exp >= 0.1 else f"{exp:.2f}"
    ratio_s = f"{ratio:.0f}× usual" if ratio < 20 else "over 20× usual"
    return (f"{obs} {PHENO_LABEL[row['phenotype']]} patients in {WARD_NAME[row['ward']]} in the "
            f"{period}; ~{exp_s} expected from this ward's last year ({ratio_s}). "
            f"Possible transmission — review contact precautions.")


def sentinel_sentence(row):
    return (f"New {PHENO_LABEL[row['phenotype']]} patient in {WARD_NAME[row['ward']]} on "
            f"{pd.Timestamp(row['date']).date()}. Notifiable in Finland — isolate and inform "
            f"infection control.")


def _q(q):
    return "q<0.001" if q < 0.001 else f"q={q:.3f}"


def shift_sentence(row):
    return (f"{row['organism']} ({row['specimen']}) resistance to {DRUG_NAME[row['antibiotic_code']]} "
            f"in {WARD_NAME[row['ward']]}: {row['pR_rec']*100:.0f}% in the last 4 weeks "
            f"(n={int(row['n_rec'])}) vs {row['pR_base']*100:.0f}% over the previous year "
            f"(n={int(row['n_base'])}), {_q(row['q'])}.")


def drift_sentence(row):
    s = (f"{row['organism']} ({row['specimen']}) resistance to {DRUG_NAME[row['antibiotic_code']]} "
         f"is rising {row['pp_per_year']*100:+.1f} pp/year, now ≈{row['now']*100:.0f}% ({_q(row['q'])}).")
    if row.get("threshold_status"):
        s += f" Empiric threshold {row['threshold']*100:.0f}%: {row['threshold_status']}."
    return s


# ---------- active alarms for a given as-of date ----------

LEVEL_RANK = {"": 0, "watch": 1, "warning": 2, "sentinel": 3}


def lab_for(lab, key, asof):
    """Lab verdict using only EUCAST changes whose 90-day after-window is complete by asof."""
    asof = pd.Timestamp(asof)
    rows = lab[(lab["key"] == key) &
               (pd.to_datetime(lab["break_date"]) + pd.Timedelta(days=90) <= asof)]
    if rows.empty:
        return "No completed breakpoint change to compare yet."
    return lab_verdict(rows.to_dict("records"))


def active_alarms(cd, shift, sent, lab, asof, min_level="watch", lookback=14):
    """Alarms that fired in the `lookback` days up to and including asof."""
    asof = pd.Timestamp(asof)
    lo = asof - pd.Timedelta(days=lookback - 1)
    allowed = ["warning"] if min_level == "warning" else ["watch", "warning"]
    out = []
    x = cd[cd["date"].between(lo, asof) & cd["level"].isin(allowed)]
    for (w, ph), g in x.groupby(["ward", "phenotype"]):
        last = g.iloc[-1]
        worst = max(g["level"], key=LEVEL_RANK.get)
        out.append(dict(kind="CLUSTER", ward=w, what=PHENO_LABEL[ph], phenotype=ph, level=worst,
                        date=last["date"], sentence=cluster_sentence(last),
                        lab=lab_for(lab, f"pheno:{ph}", asof)))
    for r in sent[sent["date"].between(lo, asof)].to_dict("records"):
        out.append(dict(kind="SENTINEL", ward=r["ward"], what=PHENO_LABEL[r["phenotype"]],
                        phenotype=r["phenotype"], level="sentinel", date=r["date"],
                        sentence=sentinel_sentence(r), lab=lab_for(lab, f"pheno:{r['phenotype']}", asof)))
    if min_level != "warning":
        s = shift[shift["date"].between(lo, asof) & shift["alert"]]
        s = s.sort_values("date").groupby(["organism", "antibiotic_code", "specimen", "ward"]).tail(1)
        for r in s.to_dict("records"):
            out.append(dict(kind="SHIFT", ward=r["ward"], what=f"{r['organism']} {r['antibiotic_code']}",
                            organism=r["organism"], antibiotic_code=r["antibiotic_code"],
                            specimen=r["specimen"], level="watch", date=r["date"],
                            sentence=shift_sentence(r),
                            lab=lab_for(lab, f"{r['organism']}|{r['antibiotic_code']}|{r['specimen']}", asof)))
    return sorted(out, key=lambda a: (-LEVEL_RANK[a["level"]], a["ward"]))
