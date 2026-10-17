"""History replay + spike injection -> cache/*.parquet + cache/summary.json.
Run once; the app only reads the cache."""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import core
import detect

warnings.filterwarnings("ignore")
CACHE = Path(__file__).parent / "cache"
START, END = "2023-10-02", "2026-09-27"
KNOWN = [  # (label, ward, phenotype, search window)
    ("Urology ESBL (Jun 2025)", "URO", "esbl", "2025-05-01", "2025-07-31"),
    ("ICU MRSA (Mar 2026)", "ICU", "mrsa", "2026-02-01", "2026-04-30"),
]
N_TRIALS, KS, SEED = 120, (3, 5, 8), 2026


def first_date(df, mask):
    d = df.loc[mask, "date"]
    return d.min().date().isoformat() if len(d) else None


def replay(cul, iso, ast):
    cd = detect.all_cluster_daily(cul, iso, START, END)
    ev = cd[cd["evaluated"]]
    p0, p1 = ev["date"].min(), ev["date"].max()
    years = ((p1 - p0).days + 1) / 365.25

    # SHIFT weekly over the same period
    af = ast[ast["first"]]
    shift_all = pd.concat([detect.shift_test(af, d) for d in pd.date_range(p0, p1, freq="7D")],
                          ignore_index=True)
    shift_alerts = shift_all[shift_all["alert"]].copy()
    sent = detect.sentinel_events(iso)
    sent = sent[(sent["date"] >= p0) & (sent["date"] <= p1)]

    def n_eps(df, mask, keys=("ward", "phenotype")):
        return sum(len(detect.episodes(g["date"])) for _, g in df[mask].groupby(list(keys)))

    eps = {
        "Watch": n_eps(ev, ev["level"].isin(["watch", "warning"])),
        "Warning": n_eps(ev, ev["level"] == "warning"),
        "rule_3in5": n_eps(ev, ev["rule3in5"]),
        "SHIFT": n_eps(shift_alerts, shift_alerts["alert"],
                       ("organism", "antibiotic_code", "specimen", "ward")),
        "SENTINEL": len(sent),
    }
    known = []
    for label, w, ph, a, b in KNOWN:
        x = ev[(ev["ward"] == w) & (ev["phenotype"] == ph) & ev["date"].between(a, b)]
        known.append(dict(cluster=label, ward=w, phenotype=ph,
                          Watch=first_date(x, x["level"].isin(["watch", "warning"])),
                          Warning=first_date(x, x["level"] == "warning"),
                          rule_3in5=first_date(x, x["rule3in5"])))
    shift_keys = (shift_alerts.groupby(["organism", "antibiotic_code", "specimen", "ward"])["date"]
                  .agg(first="min", last="max", weeks="count").reset_index())
    shift_keys["first"] = shift_keys["first"].dt.date.astype(str)
    shift_keys["last"] = shift_keys["last"].dt.date.astype(str)
    summary = dict(period=[p0.date().isoformat(), p1.date().isoformat()], years=round(years, 3),
                   episodes=eps, episodes_per_year={k: round(v / years, 2) for k, v in eps.items()},
                   known_clusters=known, shift_alert_keys=shift_keys.to_dict("records"))
    return cd, shift_all, sent, summary


def inject(cul, iso):
    """120 trials: k synthetic ESBL (70%) or MRSA patients on a random ward over 14 days."""
    rng = np.random.default_rng(SEED)
    events = {ph: detect.case_events(iso, ph) for ph in detect.CLUSTER_PHENO}
    wards = sorted(cul["ward_code"].unique())
    lo, hi = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-08-15")
    base_cache, rows = {}, []
    for trial in range(N_TRIALS):
        k = KS[trial % len(KS)]
        ph = "esbl" if rng.random() < 0.7 else "mrsa"
        w = wards[rng.integers(len(wards))]
        start = lo + pd.Timedelta(days=int(rng.integers((hi - lo).days + 1)))
        add = pd.Series(sorted(start + pd.to_timedelta(rng.integers(0, 14, k), unit="D")))
        cases = events[ph].loc[events[ph]["ward_code"] == w, "sample_date"]
        cults = cul.loc[cul["ward_code"] == w, "sample_date"]
        if (w, ph) not in base_cache:
            base_cache[(w, ph)] = detect.cluster_daily(cases, cults, START, END, w, ph)
        base = base_cache[(w, ph)]
        inj = detect.cluster_daily(pd.concat([cases, add]), pd.concat([cults, add]), START, END, w, ph)
        win = inj["date"].between(start, start + pd.Timedelta(days=28))
        row = dict(trial=trial, k=k, phenotype=ph, ward=w, start=start.date().isoformat())
        for name, on, off in [
            ("Watch", inj["level"].isin(["watch", "warning"]), base["level"].isin(["watch", "warning"])),
            ("Warning", inj["level"] == "warning", base["level"] == "warning"),
            ("rule_3in5", inj["rule3in5"], base["rule3in5"]),
        ]:
            hit = inj.loc[win & on & ~off.values, "date"]  # only alarms the injection itself caused
            row[f"{name}_detected"] = bool(len(hit))
            row[f"{name}_delay"] = (hit.min() - start).days if len(hit) else None
        rows.append(row)
    df = pd.DataFrame(rows)
    sens = {}
    for k in KS:
        x = df[df["k"] == k]
        sens[str(k)] = {n: dict(sensitivity=round(x[f"{n}_detected"].mean(), 3),
                                median_delay_days=(float(x[f"{n}_delay"].dropna().median())
                                                   if x[f"{n}_detected"].any() else None),
                                trials=len(x))
                        for n in ["Watch", "Warning", "rule_3in5"]}
    return df, sens


def lab_table(iso, ast):
    fi, af = iso[iso["first"]], ast[ast["first"]]
    rows = []
    for ph in detect.PHENO_LABEL:
        rows += detect.lab_check_rows(detect.phenotype_events(fi, ph), END, f"pheno:{ph}")
    for (o, a, s), x in af.groupby(["organism", "antibiotic_code", "specimen"]):
        rows += detect.lab_check_rows(x[["sample_date", "R"]], END, f"{o}|{a}|{s}")
    return pd.DataFrame(rows)


def annual_vs_ward(iso):
    """Hospital-level annual ESBL % vs Urology rolling 28-day ESBL % (2025)."""
    fi = iso[iso["first"]]
    ev = detect.phenotype_events(fi, "esbl")
    yr = ev[ev["sample_date"].dt.year == 2025]
    annual = yr["R"].mean()
    days = pd.date_range("2025-01-01", "2025-12-31")
    uro = ev[ev["ward_code"] == "URO"]
    roll = []
    for d in days:
        x = core.window(uro, d, 28)
        lo, hi = core.wilson(x["R"].sum(), len(x))
        roll.append(dict(date=d, pct=x["R"].mean() if len(x) else np.nan, n=len(x),
                         lo=float(lo), hi=float(hi)))
    return pd.DataFrame(roll), dict(annual_hospital_esbl_2025=round(float(annual), 4),
                                    n_2025=int(len(yr)))


def main():
    CACHE.mkdir(exist_ok=True)
    cul, iso, ast = core.load()
    cd, shift_all, sent, summary = replay(cul, iso, ast)
    cd.to_parquet(CACHE / "cluster_daily.parquet")
    shift_all.to_parquet(CACHE / "shift.parquet")
    sent.to_parquet(CACHE / "sentinel.parquet")

    dr = detect.drift(ast[ast["first"]], END)
    dr.to_parquet(CACHE / "drift.parquet")
    summary["drift_alerts"] = dr[dr["alert"]].round(4).to_dict("records")
    summary["drift_thresholds"] = dr[dr["threshold"].notna()][
        ["organism", "antibiotic_code", "specimen", "now", "pp_per_year", "q", "threshold_status"]
    ].round(4).to_dict("records")

    inj, sens = inject(cul, iso)
    inj.to_parquet(CACHE / "injection.parquet")
    summary["injection"] = sens

    lab_table(iso, ast).to_parquet(CACHE / "lab.parquet")
    roll, annual = annual_vs_ward(iso)
    roll.to_parquet(CACHE / "annual_vs_ward.parquet")
    summary["annual_vs_ward"] = annual

    cov = core.coverage(iso, ast, END, ward="URO", specimen="urine")
    summary["coverage_uro_urine"] = {r.drug: round(r.mean, 3) for r in cov.itertuples()}
    summary["first_isolate_share"] = round(float(iso["first"].mean()), 4)

    (CACHE / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
