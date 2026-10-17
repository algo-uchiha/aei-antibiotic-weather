import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

ASOF = "2026-09-27"


@pytest.fixture(scope="session")
def data():
    return core.load()


def test_row_counts(data):
    cul, iso, ast = data
    assert (len(cul), len(iso), len(ast)) == (46792, 24571, 172381)


def test_first_isolate_share(data):
    _, iso, _ = data
    assert abs(iso["first"].mean() - 0.969) < 0.005


def test_first_isolate_rule_on_toy():
    d = pd.DataFrame({
        "isolate_id": list("abcde"), "patient_id": ["p"] * 4 + ["q"],
        "organism": ["E"] * 5, "specimen": ["urine"] * 5,
        "sample_date": pd.to_datetime(["2025-01-01", "2025-01-20", "2025-02-05", "2025-02-10", "2025-01-02"]),
    })
    # day 0 kept, day 19 dropped, day 35 kept (≥30 after the kept one), day 40 dropped
    assert core.first_isolate_flag(d).tolist() == [True, False, True, False, True]


def test_origin_rule(data):
    cul, _, _ = data
    hosp = cul[cul["origin"] == "hospital"]
    assert (hosp["ward_type"] == "in").all() and (hosp["hospital_day"] >= 3).all()
    assert (cul.loc[cul["ward_type"] == "out", "origin"] == "community").all()


def test_age_bands():
    assert core.age_band(pd.Series([0, 17, 18, 64, 65, 79, 80, 101])).tolist() == \
        ["0–17", "0–17", "18–64", "18–64", "65–79", "65–79", "80+", "80+"]


def test_wilson():
    lo, hi = core.wilson(8, 10)
    assert round(float(lo), 3) == 0.490 and round(float(hi), 3) == 0.943


def test_antibiogram_excludes_fox_and_flags_small_n(data):
    _, _, ast = data
    ab = core.antibiogram(ast, ASOF, 28, ward="URO")
    assert "FOX" not in set(ab["antibiotic_code"])
    assert (ab["enough"] == (ab["n"] >= 30)).all()
    small = ab[~ab["enough"]]
    assert ((small["shrunk"] >= 0) & (small["shrunk"] <= 1)).all()


def test_coverage_uro_urine_matches_expected(data):
    _, iso, ast = data
    cov = core.coverage(iso, ast, ASOF, ward="URO", specimen="urine").set_index("drug")["mean"]
    expected = {"NIT": 0.84, "MEM": 0.82, "TZP": 0.78, "CIP": 0.76, "TMP": 0.66}
    for drug, val in expected.items():
        assert abs(cov[drug] - val) < 0.015, (drug, cov[drug])
    assert "FOX" not in cov.index
    assert cov.index[0] == "NIT"


def test_coverage_unreported_counts_as_not_covering(data):
    _, iso, ast = data
    cov = core.coverage(iso, ast, ASOF, ward="URO", specimen="urine").set_index("drug")
    # vancomycin is only reported for gram-positives, so coverage is far below any gram-negative drug
    assert cov.loc["VAN", "mean"] < 0.3
    assert np.all(cov["lo"] <= cov["mean"]) and np.all(cov["mean"] <= cov["hi"])
