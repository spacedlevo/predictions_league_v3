# Predictions League v3 — Project Context

## Overview

A read-only public website for a friends' Premier League score predictions competition. Players submit predicted scores for each gameweek's fixtures. Points are awarded for correct results and exact scores. The site displays overall standings, individual player history, and per-gameweek breakdowns.

Data is managed entirely by a separate external script (`prediction_league_script`) which syncs fixture/result/prediction data to the MySQL database. This website only reads from that database — it never writes to it.

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3 |
| Framework | Flask (Jinja2 templates) |
| Database | MySQL (PythonAnywhere hosted) |
| DB driver | PyMySQL |
| Frontend | Bootstrap 5 (CDN), plain HTML/CSS |
| Hosting | PythonAnywhere (WSGI) |

No JavaScript frameworks. No build step. No admin section.

## Project Structure

```
predictions_league_v3/
├── app.py                  # Flask app factory: create_app()
├── wsgi.py                 # PythonAnywhere entry point: application = create_app()
├── config.py               # Config class — reads from environment variables
├── requirements.txt
├── routes/
│   ├── home.py             # Blueprint: /
│   ├── player.py           # Blueprint: /player/
│   └── gameweek.py         # Blueprint: /gameweek/
├── services/
│   └── database.py         # All DB query functions (no queries elsewhere)
├── templates/
│   ├── base.html           # Shared layout, Bootstrap 5 CDN
│   ├── home/index.html
│   ├── player/profile.html
│   ├── gameweek/view.html
│   └── gameweek/list.html
└── static/             # (currently empty — CSS and JS are inlined in base.html)
```

## Database Schema

MySQL database on PythonAnywhere. These are the tables and columns used by the site:

### `players`
| Column | Type | Notes |
|---|---|---|
| `player_id` | INT PK | |
| `player_name` | TEXT | Full name |
| `web_name` | TEXT | Short display name |
| `active` | INT | 1 = active, filter to active=1 only |
| `paid` | INT | |

### `teams`
| Column | Type | Notes |
|---|---|---|
| `team_id` | INT PK | |
| `team_name` | TEXT | |
| `fpl_id` | INT | |

### `gameweeks`
| Column | Type | Notes |
|---|---|---|
| `gameweek` | INT PK | |
| `deadline_dttm` | DATETIME | UTC |
| `current_gameweek` | INT | 1 if this is the live GW |
| `next_gameweek` | INT | 1 if this is the upcoming GW |
| `finished` | INT | 1 if all fixtures complete |

### `fixtures`
| Column | Type | Notes |
|---|---|---|
| `fixture_id` | INT PK | |
| `kickoff_dttm` | DATETIME | UTC |
| `home_teamid` | INT | FK → teams.team_id |
| `away_teamid` | INT | FK → teams.team_id |
| `gameweek` | INT | |
| `season` | TEXT | Format: `2025/2026` |
| `finished` | INT | 1 if played |
| `started` | INT | 1 if kicked off |

### `results`
| Column | Type | Notes |
|---|---|---|
| `result_id` | INT PK | |
| `fixture_id` | INT | FK → fixtures.fixture_id |
| `home_goals` | INT | |
| `away_goals` | INT | |
| `result` | TEXT | H, D, or A |

### `predictions`
| Column | Type | Notes |
|---|---|---|
| `prediction_id` | INT PK | |
| `player_id` | INT | FK → players.player_id |
| `fixture_id` | INT | FK → fixtures.fixture_id |
| `home_goals` | INT | |
| `away_goals` | INT | |
| `predicted_result` | TEXT | H, D, or A |

## Pages & Routes

### `/` — Home
- Overall league table for the current season: columns are player name, correct results, correct scores, total points
- Fixtures panel showing results/fixtures for the **current live gameweek** (`current_gameweek=1`); if no gameweek is live, show the **next gameweek** (`next_gameweek=1`)

### `/player/<int:player_id>` — Player Profile
- "Predicted Premier League table": what the PL table would look like if all this player's predicted scores were real results. Columns: pos, team, P, W, D, L, GF, GA, GD, Pts
- Full prediction history: every fixture the player has a prediction for, showing: fixture, their prediction, actual result, points earned

### `/gameweek/<int:gw_number>` — Gameweek Detail
- Gameweek-only rankings: player, correct results this GW, correct scores this GW, points this GW
- Prediction comparison grid: players as rows, fixtures as columns — each cell shows the player's predicted score (hidden per visibility rules below)

### `/gameweek/` — Gameweek List
- List of all gameweeks with links to their detail pages

## Business Logic

### 9-9 Placeholder Predictions
- A prediction of `9-9` (home_goals=9, away_goals=9) means the player did not submit a real prediction
- **Scoring**: 9-9 predictions are included in points calculation — they can score 1 point if the game ends in a draw (correct result), but will never score 2 points (no PL game has ever ended 9-9)
- **Visibility**: 9-9 predictions count as non-submissions — a fixture is not considered "all players have submitted" if any active player has a 9-9 prediction

### Points Calculation
- **2 points** — exact correct score (e.g. predicted 2-1, result was 2-1)
- **1 point** — correct result only (H/D/A), wrong exact score
- **0 points** — wrong result

### Prediction Visibility
A player's prediction for a specific fixture is visible if **either** condition is true:
1. `kickoff_dttm` for that fixture is in the past (UTC now > kickoff), OR
2. Every active player (`active=1`) has submitted a valid (non-9-9) prediction for that fixture

### Season Filtering
- Always filter fixtures/predictions to the current season
- Derive current season from the gameweek that has `current_gameweek=1` or `next_gameweek=1`
- Season string format: `2025/2026`

### Active Players
All queries involving players filter to `active = 1` only.

## Development Guidelines

- **All DB queries in `services/database.py`** — no inline SQL in routes or templates
- **DB credentials via environment variables** — never hardcoded. Variables: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- **PyMySQL** for MySQL connection: `pymysql.connect(...)` with `cursorclass=pymysql.cursors.DictCursor`
- **Templates stay logic-free** — pass pre-computed data from route handlers, do not calculate points or visibility in Jinja2
- **Bootstrap 5 CDN** — no local assets, no npm, no build step
- **Mobile-first design** — the site must look good and be fully usable on mobile. Use Bootstrap's responsive grid and utilities. Tables (league table, prediction grids) must be horizontally scrollable on small screens rather than breaking layout. Ensure tap targets are large enough and text is readable without zooming.
- **No over-engineering** — one function per query need, no class hierarchies, no caching layer unless a real performance issue is observed
- Keep routes thin: fetch data → pass to template

## PythonAnywhere Deployment

### WSGI entry point (`wsgi.py`)
```python
from app import create_app
application = create_app()
```

### MySQL connection
- Hostname format: `yourusername.mysql.pythonanywhere-services.com`
- Set credentials in the PythonAnywhere **Web tab → Environment variables** section (or a `.env` file excluded from git)

### Static files
- Map `/static/` → `<project_path>/static` in the PythonAnywhere Web tab

### Reloading
- After any code change, hit **Reload** in the PythonAnywhere Web tab

## Out of Scope (not in v3)

- Admin section / login
- Graphs or charts
- Player vs player comparison
- Stats / submission analysis page
- Mini-league or second-chance league tables
- Write operations of any kind

These may be revisited in a future version if needed.
