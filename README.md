# AEI · Antibiotic weather report

**Up-to-date antibiotic susceptibility for your own ward, with alarms when something starts spreading.**

JunctionX Turku 2026 · Tyks × Mylab challenge. Synthetic data only (see `data/README.md`).

## Run locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python precompute.py        # builds cache/ (already committed)
streamlit run app.py
pytest -q
```
