# RoadGuard AI

RoadGuard AI is an academic software prototype for driver-profile management,
browser-based driving telemetry, voice guidance, trip history, emergency-workflow
simulation, and a Random Forest classification laboratory.

> **Safety boundary:** This is not a certified accident-detection or emergency
> dispatch system. The emergency workflow only records a prepared notification;
> it never sends SMS messages or contacts hospitals, ambulances, police, or other
> emergency services.

## What this updated version fixes

- Firebase identity is verified by the Flask server using a Firebase ID token;
  the browser's UID and email are no longer trusted directly.
- Firebase email verification is required before a RoadGuard session is created.
- Driver profiles, preferences, contacts, trips, telemetry, and incident records
  are isolated by the signed-in user's local `user_id`.
- Stateful requests use a per-session CSRF token.
- Private files, databases, backup folders, and local datasets are excluded by
  `.gitignore` for a safer GitHub repository.
- The dashboard is described honestly as a browser safety indicator. Its live
  heuristic is separate from the Random Forest experiment in **AI Lab**.

## Prerequisites

- Python 3.11 is recommended.
- A Firebase project with **Email/Password** sign-in enabled.
- A Firebase **service-account JSON** file for the Flask server. Keep it outside
  this folder and never commit or share it.

## Local setup in VS Code (Windows)

1. Open this project folder in VS Code.
2. Create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install packages:

   ```powershell
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to a new file named `.env` in this folder. Replace both
   example values:

   ```powershell
   Copy-Item .env.example .env
   ```

   - Set `ROADGUARD_SECRET_KEY` to a long random secret.
   - Set `FIREBASE_SERVICE_ACCOUNT_PATH` to the full path of the private Firebase
     service-account JSON file stored outside this project.

5. In Firebase Authentication, add `localhost` and `127.0.0.1` to **Authorized
   domains**. Do not use a production domain until HTTPS is configured.
6. Start the server:

   ```powershell
   python server.py
   ```

7. Open <http://127.0.0.1:5000>.

The application intentionally stops at startup if the secret key or service
account path is missing. This prevents accidentally running a version that
pretends Firebase verification is enabled when it is not.

## Account flow

1. Register with Firebase email/password.
2. Open the Firebase verification email and confirm the address.
3. Sign in. The browser sends a short-lived Firebase ID token to Flask.
4. Flask verifies the token and verified-email claim using Firebase Admin SDK.
5. Flask creates a local session tied to the verified Firebase UID.

## Research-model scope

The AI Lab accepts a labelled CSV with these columns:

```text
speed, acceleration, braking, duration, weather, traffic, road_condition, risk_label
```

The bundled Random Forest experiment is an academic classification workflow.
Read [`research/EXPERIMENT_NOTES.md`](research/EXPERIMENT_NOTES.md) before using
its results in a paper. In particular, do not call derived labels confirmed
accident outcomes, and do not claim that the live dashboard's browser heuristic
is the Random Forest prediction.

## GitHub checklist

Before publishing:

1. Confirm `git status` does not list `.env`, any Firebase service-account JSON,
   `roadguard.db`, backups, or personal datasets.
2. Keep the repository **private** until you finish functional testing.
3. Include source attribution and confirm redistribution terms before committing
   any dataset.
4. See [`GITHUB_SETUP.md`](GITHUB_SETUP.md) for commands.

## Current limitations

- No real SMS, ambulance, hospital, traffic, or weather-service integration.
- Browser GPS/motion data require user permission and supported devices.
- The live dashboard uses a transparent heuristic; it is not a medical or
  collision-prediction system.
- The original dataset-to-label transformation must be fully documented before
  publishing research results from the processed CSV.
