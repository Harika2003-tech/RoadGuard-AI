# Firebase and data-isolation setup

## Keep these private

Never commit, upload, email, or paste these files into a chat:

- `.env`
- Firebase service-account JSON
- `roadguard.db`
- personal trip, contact, location, or telemetry data

## Firebase Admin setup

1. In Firebase Console, select the RoadGuard project.
2. Go to **Project settings → Service accounts**.
3. Generate a private key and save the JSON outside this repository, for example:
   `C:/RoadGuard-Secrets/firebase-service-account.json`.
4. Copy `.env.example` to `.env` and update
   `FIREBASE_SERVICE_ACCOUNT_PATH` with that location.
5. Enable **Email/Password** under Firebase Authentication providers.
6. Add local development domains (`localhost` and `127.0.0.1`) to Firebase
   Authentication authorized domains.

## How records are separated

The server uses the Firebase ID token only after server verification. It maps the
verified Firebase UID to `users.id`. Every user-owned row is filtered by that ID:

- `driver_profiles`
- `user_preferences`
- `contacts`
- `trips`
- `telemetry`
- `incidents`

Old rows created by the earlier shared-data version remain unassigned. They are
not automatically given to a newly signed-in account.

## Two-account test

Use two test Firebase accounts:

1. Sign in as Account A and create a contact and a trip.
2. Sign out, then sign in as Account B.
3. Confirm Account B cannot see Account A's contact or trip.
4. Repeat the test after restarting the server.

## Deployment note

For public hosting, use HTTPS, set `COOKIE_SECURE=true`, use a production WSGI
server, add rate limiting, configure backups, and conduct a security review.
