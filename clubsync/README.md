# ClubSync — Campus Club Management (SQLite + Flask)

## Run it (5 steps)
1. `pip install -r requirements.txt`
2. `cp .env.example .env` (never commit the real one)
3. `python seed.py` — rebuilds `campus.db` from `schema.sql` with demo data
4. `python app.py` → open http://localhost:5000
5. `python smoke_test.py` — 20 automated checks of the approval gate, RBAC, OD and certificates

Demo logins (password `demo123`): super@demo.in, admin@demo.in, club@demo.in, faculty@demo.in (mentor + coordinator),
stu@demo.in (RA2211003010001), vol@demo.in (RA2211003010002, holds the dynamic role "Logistics Lead" = can edit events only).

## What makes it different
- **ProofOD**: attendance comes from a 30-second rotating QR token, not hand marking. The mentor sees "QR-verified attendance" on every OD, and only checked-in students get certificates.
- **Approval gate enforced in the database**: a trigger rejects registration for any event that is not approved/ongoing and blocks overbooking, so even a buggy API cannot bypass it.
- **Academic-impact preview**: every event card shows the class periods it overlaps before it is submitted.
- **OD period snapshot**: periods are stored on each OD, so timetable edits never rewrite history.

## Build guide (36 h)
| Hours | Do this | Files |
|---|---|---|
| 0–2 | Role/permission matrix, ER diagram (draw from `schema.sql`) | schema.sql |
| 2–8 | Auth, RA validation, users, clubs, timetable + validation | `/api/signup`, `/api/timetable` |
| 8–16 | Event state machine + faculty approval | `/api/events/*` |
| 16–24 | Registration, OD with periods, notifications | `/api/od` |
| 24–30 | QR check-in, certificates, analytics, dynamic roles | `/api/stats` |
| 30–36 | Freeze features, screenshots, workflow diagrams, video (≤25 min), zip without `.env`, form submit | — |

## Demo script
1. Club admin tries `POST /api/timetable` → 403; super admin adds an overlapping period → validation error.
2. Club admin creates an event; student cannot register (draft). Submit → faculty rejects with reason → resubmit → approve.
3. Student registers, applies OD → periods shown → mentor approves; student cannot self-approve.
4. Start event → organiser token → student checks in → complete → issue certificates → open `/cert/<code>` and `/api/verify/<code>`.
5. Log in as vol@demo.in: can create events, cannot issue certificates (403).

## Step-by-step: how to access it
1. Install Python 3.10+ (python.org). Check with `python --version`.
2. Unzip `clubsync.zip`, open a terminal in the `clubsync` folder.
3. `pip install -r requirements.txt`
4. `python seed.py` (Windows: `py seed.py`) - prints "seeded".
5. `python app.py` - leave it running.
6. Open http://localhost:5000 in a browser. On a phone on the same Wi-Fi use `http://<your-PC-IP>:5000` after changing the last line of `app.py` to `app.run(host="0.0.0.0", port=5000)`.
7. Sign in with the demo accounts below (password `demo123`). Use two browsers (or one normal + one private window) to be two users at once.

| Role | Login | Use it to |
|---|---|---|
| Super Admin | super@demo.in | Timetable form, create users/clubs, dashboard |
| Admin | admin@demo.in | Create club admins, dashboard, archive clubs |
| Club Admin | club@demo.in | Create events, roles, members, badges, certificates |
| Faculty | faculty@demo.in | Approve events and ODs, message staff |
| Student | stu@demo.in | Register, check in, apply OD |
| Student + dynamic role | vol@demo.in | Can edit events only; certificate/badge actions return 403 |

## Try the full flow in the UI
1. Club Admin -> "Create event" (club_id 1, a future weekday date, 10:30-13:00, capacity 1). The card shows the impacted periods.
2. Club Admin -> Submit for approval. Faculty -> Reject (with reason), Club Admin resubmits, Faculty approves.
3. Student -> Register -> Apply for OD. Faculty -> Approve the OD (periods are listed).
4. Club Admin -> Start -> "Show check-in token" -> Student -> "Check in" and paste the token (valid 30 s).
5. Club Admin -> Complete -> Issue certificates -> Student opens the certificate link; verify at `/api/verify/<code>`.
6. Club Admin -> Create badge (club_id 1) -> Award badge (badge_id 1, student RA) -> Student sees it under "My badges".
7. Super Admin -> New timetable with an overlapping line -> validation error. Club Admin has no timetable form and gets 403 through the API.

## Google Sign-In (optional)
Create an OAuth Web client at console.cloud.google.com, add `http://localhost:5000` as an authorised origin, put the ID in `.env` as `GOOGLE_CLIENT_ID=...`, and start with `export $(cat .env | xargs) && python app.py` (Windows: set the variable first). Students sign up once with their RA Number, then can use Google.

## Still not built (state honestly in the report)
Timetable edit/reorder of an existing structure (create new + activate replaces the old one), PDF file download (use browser Print -> Save as PDF on the certificate page), student portfolio export, feedback, budget tracker, venue booking, leaderboard. The ER diagram and workflow diagrams must be drawn by you from `schema.sql`.
