from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.mark.parametrize("page", ["Home", "Prescriber", "Infection control", "Lab & proof"])
def test_pages_render_during_demo(page):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["page"] = page
    at.session_state["asof"] = date(2025, 6, 8)
    at.run()
    assert not at.exception
    assert any("Hospital status on 8 June 2025" in m.value for m in at.markdown)
