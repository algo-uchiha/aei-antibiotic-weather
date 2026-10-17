"""Load, clean and summarise the microbiology data: first isolates, filters,
antibiogram and empiric (WISCA-style) coverage. All statistics live here and in detect.py."""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
AGE_BANDS = ["0–17", "18–64", "65–79", "80+"]
EXCLUDE_TREATMENT = {"FOX"}  # cefoxitin is an MRSA screen, not a treatment
WARDS = ["ED", "MED-A", "MED-B", "SURG", "URO", "ICU", "GER", "PHC-N", "PHC-S"]
PHENOTYPES = ["esbl", "mrsa", "vre", "cpe"]
SHRINK_K = 10
MIN_N = 30


def wilson(s, n, z=1.959964):
    """Wilson 95% interval for s successes of n. Works on scalars or arrays; NaN where n == 0."""
    s, n = np.asarray(s, float), np.asarray(n, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = s / n
        den = 1 + z**2 / n
        mid = (p + z**2 / (2 * n)) / den
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return mid - half, mid + half


def age_band(age):
    return pd.cut(age, [-1, 17, 64, 79, 200], labels=AGE_BANDS).astype(str)


def first_isolate_flag(iso, gap_days=30):
    """CLSI M39 style: per patient × organism × specimen keep an isolate only if it is
    ≥gap_days after the previous *kept* one."""
    iso = iso.sort_values(["patient_id", "organism", "specimen", "sample_date", "isolate_id"])
    keep = np.zeros(len(iso), bool)
    days = (iso["sample_date"].values.astype("datetime64[D]")).astype(np.int64)
    keys = iso[["patient_id", "organism", "specimen"]].astype(str).agg("|".join, axis=1).values
    last_key, last_day = None, None
    for i in range(len(iso)):
        if keys[i] != last_key or days[i] - last_day >= gap_days:
            keep[i] = True
            last_key, last_day = keys[i], days[i]
    return pd.Series(keep, index=iso.index)


def load(data_dir=DATA):
    """Return (cultures, isolates, ast). isolates and ast carry culture/patient metadata,
    origin, age band and the first-isolate flag."""
    cul = pd.read_csv(data_dir / "cultures.csv", parse_dates=["sample_date", "admission_date"])
    pat = pd.read_csv(data_dir / "patients.csv")
    iso = pd.read_csv(data_dir / "isolates.csv")
    ast = pd.read_csv(data_dir / "susceptibility.csv")

    cul = cul.merge(pat[["patient_id", "sex"]], on="patient_id", how="left")
    cul["hospital_day"] = (cul["sample_date"] - cul["admission_date"]).dt.days + 1
    cul["origin"] = np.where((cul["ward_type"] == "in") & (cul["hospital_day"] >= 3),
                             "hospital", "community")
    cul["age_band"] = age_band(cul["age_years"])

    meta = ["culture_id", "patient_id", "sample_date", "ward_code", "ward_type", "institution",
            "specimen", "sex", "age_band", "origin"]
    iso = iso.merge(cul[meta], on="culture_id", how="left")
    iso["first"] = first_isolate_flag(iso)

    ast = ast.merge(iso[["isolate_id", "first"] + [m for m in meta if m != "culture_id"]],
                    on="isolate_id", how="left")
    ast["R"] = (ast["result"] == "R").astype(int)
    return cul, iso, ast


def apply_filters(df, ward=None, specimen=None, sex=None, age=None, origin=None):
    """Filter any table carrying the culture metadata. None or 'ALL' means no filter."""
    for col, val in [("ward_code", ward), ("specimen", specimen), ("sex", sex),
                     ("age_band", age), ("origin", origin)]:
        if val not in (None, "ALL", "All"):
            df = df[df[col] == val]
    return df


def window(df, asof, days):
    """Rows with sample_date in (asof - days, asof]."""
    asof = pd.Timestamp(asof)
    return df[(df["sample_date"] > asof - pd.Timedelta(days=days)) & (df["sample_date"] <= asof)]


def antibiogram(ast, asof, days, **filters):
    """%S per organism × antibiotic over the last `days` up to asof, first isolates only.
    Cells with n < 30 get an empirical-Bayes value shrunk toward the hospital 12-month rate."""
    first = ast[ast["first"] & ~ast["antibiotic_code"].isin(EXCLUDE_TREATMENT)]
    hosp = window(first, asof, 365).groupby(["organism", "antibiotic_code"])["R"].agg(["sum", "count"])
    hosp_p = (1 - hosp["sum"] / hosp["count"]).rename("p_hosp")

    sub = window(apply_filters(first, **filters), asof, days)
    g = sub.groupby(["organism", "antibiotic_code"])["R"].agg(R="sum", n="count").reset_index()
    g["S"] = g["n"] - g["R"]
    g["pct"] = g["S"] / g["n"]
    g["lo"], g["hi"] = wilson(g["S"], g["n"])
    g = g.merge(hosp_p.reset_index(), on=["organism", "antibiotic_code"], how="left")
    g["shrunk"] = (g["S"] + SHRINK_K * g["p_hosp"]) / (g["n"] + SHRINK_K)
    g["enough"] = g["n"] >= MIN_N
    return g


def coverage(iso, ast, asof, days=365, draws=2000, seed=0, **filters):
    """WISCA-style Bayesian empiric coverage for the filtered population.
    mix ~ Dirichlet(counts+1); per-organism %S ~ Beta(S+1, R+1); coverage = Σ mix·%S.
    An organism with no reports for a drug counts as not covered."""
    fi = window(apply_filters(iso[iso["first"]], **filters), asof, days)
    counts = fi["organism"].value_counts()
    if counts.empty:
        return pd.DataFrame(columns=["drug", "mean", "lo", "hi", "n_isolates", "n_tested"])
    orgs = counts.index.tolist()
    rng = np.random.default_rng(seed)
    mix = rng.dirichlet(counts.values + 1, size=draws)  # draws × K

    fa = ast[ast["isolate_id"].isin(fi["isolate_id"]) & ~ast["antibiotic_code"].isin(EXCLUDE_TREATMENT)]
    tab = fa.groupby(["antibiotic_code", "organism"])["R"].agg(R="sum", n="count")
    rows = []
    for drug in sorted(fa["antibiotic_code"].unique()):
        t = tab.loc[drug].reindex(orgs)
        reported = t["n"].notna().values
        R = t["R"].fillna(0).values
        S = (t["n"] - t["R"]).fillna(0).values
        ps = rng.beta(S + 1, R + 1, size=(draws, len(orgs))) * reported
        cov = (mix * ps).sum(axis=1)
        rows.append(dict(drug=drug, mean=cov.mean(), lo=np.quantile(cov, 0.025),
                         hi=np.quantile(cov, 0.975), n_isolates=int(counts.sum()),
                         n_tested=int(t["n"].fillna(0).sum())))
    return pd.DataFrame(rows).sort_values("mean", ascending=False).reset_index(drop=True)


def traffic(p):
    """Same colour rule everywhere: ≥90% green, 80–89% amber, <80% red."""
    if p is None or np.isnan(p):
        return "grey"
    return "green" if p >= 0.9 else "amber" if p >= 0.8 else "red"



def rolling_rate(df, start, end, days=28, step=7, col="R"):
    """Rolling `days`-window rate of binary `col` evaluated every `step` days, with Wilson CI."""
    grid = pd.date_range(pd.Timestamp(start) - pd.Timedelta(days=days), end, freq="D")
    idx = (df["sample_date"] - grid[0]).dt.days.values
    ok = (idx >= 0) & (idx < len(grid))
    k = np.bincount(idx[ok], weights=df[col].values[ok], minlength=len(grid))
    n = np.bincount(idx[ok], minlength=len(grid))
    ck, cn = np.concatenate([[0], np.cumsum(k)]), np.concatenate([[0], np.cumsum(n)])
    t = np.arange(days, len(grid), step)
    t = t[grid[t] >= pd.Timestamp(start)] if len(t) else t
    kk, nn = ck[t + 1] - ck[t + 1 - days], cn[t + 1] - cn[t + 1 - days]
    lo, hi = wilson(kk, nn)
    with np.errstate(invalid="ignore", divide="ignore"):
        pct = kk / nn
    return pd.DataFrame({"date": grid[t], "k": kk, "n": nn, "pct": pct, "lo": lo, "hi": hi})
