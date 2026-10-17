# CLAUDE.md — AEI · Antibiotic Efficacy Indicator ("the antibiotic weather report")

JunctionX Turku 2026 · Tyks × Mylab challenge · solo developer · **hard deadline Sun 18 Oct 2026, 11:00 Europe/Helsinki**
Goal: top 3 of 13 teams. Round 1 is Gavel pairwise voting; the top 5 then pitch to Tyks and Mylab domain experts.

## Working rules for Claude Code
- Ship working increments. After every stage: run the app or the tests, then `git add -A && git commit -m "<stage>" && git push`.
- Keep the code small and readable. No new frameworks or dependencies beyond the stack below.
- **Never invent numbers.** Every figure shown in the UI comes from the computation. If a result differs from the "expected results" section, report it; don't tune parameters to force a match.
- Keep the statistics in `core.py` and `detect.py`. `app.py` only displays.
- If a stage runs more than 30 min over its time box, cut scope and tell me.
- Feature freeze at **07:30**. After that, only bug fixes and copy changes.

## The challenge (official brief, condensed)
Tyks compiles resistance reports **annually at hospital level, which is too imprecise and infrequent**. Doctors want **up-to-date susceptibility for their own ward**. Build a continuously updated tool showing the **previous 4 weeks and annual results**, filterable by dataset parameters. *"This is not a basic BI dashboard task… the hard part is a continuously updated tool which is highly usable and versatile."*
**Judging criteria:** (1) understanding of the challenge, (2) suitability for the brief and its insight, (3) usability, (4) **detects deviations and anomalies**.
External data is allowed only from certified sources (THL, ECDC, WHO, EUCAST).

## Product
A **web app** (Streamlit, public URL). In production it would be a module inside Mylab's **My+** lab system, recomputed nightly from the lab system's own data.
The app opens on a **role choice**:

| Role | Their question | Screen |
|---|---|---|
| **Prescriber** | "Culture pending: what should I give on my ward?" | Ranked empiric coverage, plus a 28-day vs 12-month antibiogram for that ward |
| **Infection control** | "Is something spreading?" | Ward weather map, alarm cards, live replay |
| **Lab & proof** | "Is it real or a lab artefact? Can I trust the alarms?" | Validation, lab check, trends, annual-vs-ward comparison, method and sources |

## Tech stack (final)
Python 3.11+ · pandas ≥2.1 · numpy · scipy · statsmodels · Streamlit ≥1.38 · Plotly · pyarrow · pytest.
Hosting: public GitHub repo → Streamlit Community Cloud (commit `cache/` so the cloud app never recomputes).
**Not used:** DuckDB, R, LLM APIs, FHIR libraries, chatbots.

## Repo layout
```
data/            6 CSVs from synthetic_microbiology_dataset.zip (synthetic, safe to commit)
core.py          load, clean, first-isolate, filters, antibiogram, empiric coverage
detect.py        CLUSTER, SENTINEL, SHIFT, DRIFT, LAB CHECK, rule_3in5, episodes, alert sentences
precompute.py    history replay + spike injection -> cache/*.parquet + cache/summary.json
app.py           Streamlit UI
tests/test_numbers.py
.streamlit/config.toml
requirements.txt  README.md  CLAUDE.md
```

## Data
**Files:** `cultures.csv`, `isolates.csv`, `susceptibility.csv`, `patients.csv`, `antibiotics.csv`, `wards.csv`.
**Size and span:** 10,000 patients, 46,792 cultures, 24,571 isolates and 172,381 S/R results, covering 2023-10-02 → 2026-09-27.
**Joins:** susceptibility → isolates on `isolate_id`; isolates → cultures on `culture_id`; cultures → patients on `patient_id`.

**Key columns:**
- `cultures`: sample_date, ward_code, ward_type (in/out), institution, admission_date, specimen (urine/blood/wound), result, age_years
- `isolates`: organism, esbl/mrsa/vre/cpe (0/1)
- `susceptibility`: antibiotic_code (WHONET), result S/R, guideline ("EUCAST 2023"…"EUCAST 2026")
- `patients`: sex (F/M), birth_year

**Wards:** ED, MED-A, MED-B, SURG, URO, ICU, GER (hospital); PHC-N, PHC-S (primary care).

**Rules (mandatory):**
1. **First isolate:** per patient × organism × specimen, keep an isolate only if it is ≥30 days after the previous *kept* one (CLSI M39 style). Expect about 96.9% kept.
2. **Origin:** "hospital-acquired" if ward_type == "in" and hospital day ≥3, where hospital day = sample_date − admission_date + 1. Otherwise "community".
3. **Age bands:** 0–17, 18–64, 65–79, 80+. Use sex as a filter: the README notes urinary E. coli resistance differs by sex.
4. **Show a percentage only when n ≥ 30.** Smaller cells are greyed out and show an empirical-Bayes shrunk value `(S + 10·p_hospital12m)/(n + 10)` in italics.
5. Use Wilson 95% confidence intervals.
6. FOX (cefoxitin) is an MRSA screen. Exclude it from treatment and coverage views.
7. Intrinsic-resistance pairs are absent from the data. In coverage, "not reported for this organism" counts as **not covering** it.
8. EUCAST version changes every 1 January. Use this for the lab check.

## Indicators
- **Antibiogram:** %S per organism × antibiotic for **the last 28 days** and **the last 12 months** up to the as-of date, first isolates only, after filters. Colours: ≥90% green, 80–89% amber, <80% red, n<30 grey.
- **Empiric coverage (WISCA-style, Bayesian):** for a filter (ward, specimen, sex, age, origin), over the last 12 months:
  - organism mix ~ Dirichlet(counts+1);
  - per-organism %S ~ Beta(S+1, R+1);
  - coverage = Σ mix × %S over 2,000 draws, reported as mean and 95% interval;
  - drugs ranked by coverage.

## Detectors (parameters validated on this dataset; keep them)
1. **CLUSTER (ESBL, MRSA), evaluated daily per ward:**
   - Count distinct new phenotype patients; the same patient on the same ward counts again only after 30 days.
   - Windows are 7 and 28 days. Expected count = (baseline count over the previous 365 days, ending before the 28-day window, + 0.5) ÷ baseline cultures × cultures in the window (volume-adjusted).
   - p = Poisson upper tail; take the smaller p over the two windows, ×2 (Bonferroni).
   - **WATCH** if p<0.01 and ≥3 cases; **WARNING** if p<0.001 and ≥3 cases. The wording mirrors weather services.
2. **SENTINEL (VRE, CPE):** any single new case is an alert (notifiable in Finland).
3. **SHIFT:**
   - Compare %R over the last 28 days with the previous 365 days, per organism × antibiotic × specimen × (each ward and ALL).
   - Test only if recent n≥8 and baseline n≥30.
   - p = beta-binomial upper tail with a = R_base+0.5, b = S_base+0.5. Apply **Benjamini–Hochberg across all tests**.
   - Alert if q<0.05 **and** %R rose ≥10 percentage points.
4. **DRIFT:**
   - Monthly binomial GLM of R on time over the last 3 years per organism × antibiotic × specimen (skip if n<300 or fewer than 15 R). Apply BH.
   - Alert if q<0.05 and the slope is ≥ +1.5 pp/year.
   - Thresholds: E. coli urine TMP 20%, E. coli urine CIP 10%, E. coli blood CRO 10%. Report "crossed" or "~N months to threshold".
5. **LAB CHECK, attached to every alert:** Fisher test of %R for 90 days before vs 90 days after each 1 January EUCAST change. If p<0.01 and |Δ| >5 pp, say "possible lab/breakpoint effect — check with the lab". Otherwise say "no step at breakpoint changes → looks biological".
6. **Baseline comparator `rule_3in5`:** ≥3 distinct phenotype patients on the same ward within 5 days (the classic manual rule).
7. **Episodes:** alert days for the same ward × phenotype merge into one episode unless separated by >28 quiet days.

**Alert sentences:** use deterministic templates, e.g. *"6 ESBL patients in Urology in the last 4 weeks; ~1.5 expected from this ward's last year (4× usual). Possible transmission — review contact precautions."*

## Validation (precompute.py → cache/summary.json)
- **Replay:**
  - Run CLUSTER and rule_3in5 daily and SHIFT weekly over all history.
  - Only dates with ≥1 year of baseline count. **Compare every detector over that same period.**
  - Report: first-alert date for each known cluster, alarm episodes per year for each detector, and SHIFT alert keys.
- **Spike injection:**
  - 120 trials; inject k ∈ {3,5,8} synthetic ESBL (70%) or MRSA patients onto a random ward, spread over 14 days, at a random start between 2025-01-01 and 2026-08-15.
  - A trial counts as detected if the alert fires within start + 28 days.
  - Report sensitivity and median delay for Watch, Warning and rule_3in5.

**Expected results** (from an earlier validated run). Use them as acceptance checks; investigate any large deviation.
- Urology ESBL cluster (Jun 2025): Watch fires **2025-06-04**, Warning 2025-06-08, rule_3in5 2025-06-04.
- ICU MRSA cluster (Mar 2026): all three fire **2026-03-07**.
- SHIFT fires **only** during those two outbreaks: Urology E. coli urine CRO/CIP/CXM/TMP/AMP (Jun–Jul 2025) and ICU/ALL S. aureus FOX/CLI (Mar–Apr 2026). Otherwise 0 false alarms.
- DRIFT: only E. coli urine **TMP**, ≈21% now, ≈+2.0 pp/yr, q≈0.002, crossed 20%.
- Injection sensitivity at k=3: Watch ≈78%, Warning ≈33%, rule_3in5 ≈45%. At k=5: ≈100% / 93% / 100%.
- Episodes: Watch ≈11, Warning ≈5. Recompute rule_3in5 over the **same** period; the earlier figure of 15 covered the full 3 years and is not comparable.
- Coverage, URO + urine, 12 months to 2026-09-27: NIT ≈84%, MEM ≈82%, TZP ≈78%, CIP ≈76%, TMP ≈66%.

## UI spec (app.py)
- **Global:**
  - `layout="wide"`, title "AEI — Antibiotic weather report"; cache data with `@st.cache_data`.
  - **Sidebar:** **As-of date** slider (default 2026-09-27) = the time machine; **▶ Play** button that advances the date day by day from a chosen start, so cells recolour and alarms appear live (this demonstrates "continuously updated"); alert level Watch/Warning.
  - **Top banner:** "As of {date}: {n} warnings · {n} watches · {n} drugs below 80% coverage".
- **Home:** three large role buttons and one sentence each. Keep navigation state in `st.session_state`.
- **Prescriber:**
  - Inputs: ward, specimen, sex, age band, origin.
  - Output: a **ranked coverage list** (drug, %, CI bar, traffic light, n). Title: "Culture pending? Chance each drug covers what grows here."
  - Expander: 28-day and 12-month antibiogram heatmaps side by side (Plotly, cell text "92% / n=41", hover with CI).
- **Infection control:**
  - A **ward weather map**: 9 tiles coloured by worst active status (green/amber/red, purple for sentinel).
  - Then alarm cards: sentence, small trend chart, lab verdict. An alarm is active if it fired in the 14 days before the as-of date.
- **Lab & proof:**
  - (a) replay timeline for ward × phenotype, with daily cases and Watch, Warning and 3-in-5 markers;
  - (b) a known-cluster table of first-alert dates per detector;
  - (c) spike-injection sensitivity bars;
  - (d) alarms per year;
  - (e) **annual hospital-level ESBL % vs Urology rolling 28-day ESBL % in 2025**, showing that the annual report hides the outbreak;
  - (f) a trend chart for organism × drug (rolling 28-day %R with CI, dashed lines at EUCAST changes, threshold line, drift sentence);
  - (g) "Download alerts (CSV/JSON)" — the integration hook for My+;
  - (h) method and sources.
- **Style:** light theme, one accent colour, the same red/amber/green everywhere, large readable numbers, no emoji clutter.

**Demo path (the app must support it smoothly):**
1. Set the as-of date to 2025-05-25 and press Play.
2. The Urology tile turns amber on 4 Jun and red on 8 Jun.
3. The alarm card explains it.
4. The Prescriber view shows Urology urine coverage dropping.
5. Lab & proof shows the annual report hiding it, plus the validation numbers.
6. Reset to 2026-09-27; the trend shows trimethoprim crossing 20%.

## Build plan (Sat 23:15 → Sun 11:00)
| Time | Stage | Done when |
|---|---|---|
| 23:15–23:35 | Repo + GitHub + env + data | First commit pushed |
| 23:35–00:15 | core.py + tests for cleaning/coverage | Coverage numbers ≈ expected |
| 00:15–01:15 | detect.py + precompute.py | summary.json ≈ expected |
| 01:15–02:45 | app: global, Home, Prescriber, Infection control | Demo steps 1–4 work |
| 02:45–03:30 | app: Lab & proof | Demo steps 5–6 work |
| 03:30–04:00 | Deploy to Streamlit Cloud | Public URL works in incognito |
| 04:00–06:30 | Sleep | — |
| 06:30–07:30 | Bug fixes, polish, stretch items | **Freeze at 07:30** |
| 07:30–10:30 | Video, thumbnail, submission page (outside Claude Code) | — |
| 10:45 | Submit | — |

**Stretch items, only after the freeze checklist passes:** a THL Finres national reference value on the trend chart (hard-coded with its source); a Finnish/English UI toggle.
**If behind at 02:45:** drop (f), and drop Play in favour of the plain slider. **Never drop** the Proof screen or the Prescriber coverage list.

## Sources (cite in the app's method section)
- Natale et al., WHONET-SaTScan for AMR clusters in a hospital in Italy, *Eurosurveillance* 22(11), 2017 — https://pmc.ncbi.nlm.nih.gov/articles/PMC5356424
- Vivli AMR Data Challenge winners 2024 (https://amr.vivli.org/?p=9536) and 2025 (https://amr.vivli.org/?p=9987)
- CLSI M39 (first isolate, n≥30); EUCAST Expected Resistant Phenotypes v1.2; THL Finres 2023 (the dataset calibration source); ECDC EARS-Net
- WISCA: Hebert et al. 2012; empiric TMP 20% threshold: IDSA/ESCMID cystitis guideline 2010. Both are marked "verify before quoting".
