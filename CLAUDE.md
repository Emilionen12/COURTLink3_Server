# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

COURTLink3_Server is a Python Flask backend for a padel tennis tournament management app. It handles teams, players, tournaments, and match results. The UI is German-language. Deployed on Railway.app.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Production (Railway)
gunicorn app:app --bind 0.0.0.0:$PORT
```

No test suite exists in this project.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | auto-generated | Flask session secret |
| `PORT` | `5000` | Server port |
| `DB_PATH` | `courtlink.db` | SQLite database path |

## Architecture

Two source files:

- **`app.py`** — Flask app with all REST API routes; handles session auth, request parsing, and calls into `datenbank.py`
- **`datenbank.py`** — All SQLite logic; direct SQL queries via `sqlite3`; no ORM
- **`templates/index.html`** — Single-page frontend (German UI, dark theme, bottom-nav layout)

### Database Schema

Four tables (in German):

- `teams` — team id, name, unique join code, password hash, timestamp
- `spieler` — players with stats: `punkte` (points), `spiele` (games played), `siege` (wins), guest flag, claim code
- `spieltage` — tournament days: round tracking, game mode, status
- `matches` — 2v2 match data: team slots, scores, round number, status

### Authentication

Session-based (`flask.session`). Keys: `team_id`, `spieler_id`. Passwords hashed with `werkzeug.security.generate_password_hash` / `check_password_hash`.

### Tournament Logic

- Tournaments are created as `spieltage` with Round-Robin scheduling
- Two modes: `random` (random pairing) and `ranked` (ELO-style pairing by current ranking)
- Scoring: Win=3pts, Draw=1pt each, Loss=0pts
- Rounds advance automatically when all matches in the current round are complete

### Guest Player System

Players can be added as guests. Guests have a `claim_code` that allows a real user to take over the account.

## Known Issues

`spieltag_team_ranking()` is defined twice in `datenbank.py` (around lines 479 and 540). The second definition shadows the first.
