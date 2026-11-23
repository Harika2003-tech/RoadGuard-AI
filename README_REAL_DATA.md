# RoadGuard AI - Real-World ML Test Version

This version preserves the original RoadGuard academic website and the metrics-update UI.
It adds a more robust CSV upload endpoint for the real-world RoadGuard-compatible dataset.

## Run

1. Create/activate a Python virtual environment.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Start:
   `python server.py`
4. Open the local URL shown by Flask.
5. Register/login.
6. Open **AI Model Laboratory**.
7. Select `roadguard_realworld_derived.csv`.
8. Click **Upload and train**.

The endpoint accepts CSV files up to 100 MB and auto-detects common CSV separators.
