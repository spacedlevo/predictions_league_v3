"""
All database query functions live here.
Supports SQLite (local dev via SQLITE_PATH) and MySQL (production via DB_* vars).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from flask import current_app

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None


@contextmanager
def get_connection():
    cfg = current_app.config
    if cfg.get("SQLITE_PATH"):
        conn = sqlite3.connect(cfg["SQLITE_PATH"])
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    else:
        conn = pymysql.connect(
            host=cfg["DB_HOST"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            database=cfg["DB_NAME"],
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4",
        )
        try:
            yield conn
        finally:
            conn.close()


def _sql(conn, sql):
    """Translate SQLite-style ? placeholders to %s for MySQL."""
    if not isinstance(conn, sqlite3.Connection):
        return sql.replace("?", "%s")
    return sql


def _fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(_sql(conn, sql), params)
    rows = cur.fetchall()
    # sqlite3.Row → plain dict for consistent access
    if rows and isinstance(rows[0], sqlite3.Row):
        return [dict(r) for r in rows]
    return rows


def _fetchone(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(_sql(conn, sql), params)
    row = cur.fetchone()
    if row and isinstance(row, sqlite3.Row):
        return dict(row)
    return row


# ---------------------------------------------------------------------------
# Gameweek helpers
# ---------------------------------------------------------------------------

def get_display_gameweek(conn):
    """Return the gameweek number to display on the homepage.
    Prefers the live (current) unfinished gameweek; falls back to next gameweek."""
    row = _fetchone(conn, """
        SELECT gameweek FROM gameweeks
        WHERE current_gameweek = 1 AND finished = 0
        LIMIT 1
    """)
    if row:
        return row["gameweek"]
    row = _fetchone(conn, """
        SELECT gameweek FROM gameweeks
        WHERE next_gameweek = 1
        LIMIT 1
    """)
    return row["gameweek"] if row else None


def get_gw_table_gameweek(conn):
    """Return the gameweek number to use for the homepage GW standings table.
    Prefers current_gameweek=1; falls back to the most recently finished gameweek."""
    row = _fetchone(conn, """
        SELECT gameweek FROM gameweeks
        WHERE current_gameweek = 1
        LIMIT 1
    """)
    if row:
        return row["gameweek"]
    row = _fetchone(conn, """
        SELECT gameweek FROM gameweeks
        WHERE finished = 1
        ORDER BY gameweek DESC
        LIMIT 1
    """)
    return row["gameweek"] if row else None


def get_current_season(conn):
    """Return the season string (e.g. '2025/2026') for the active gameweek."""
    row = _fetchone(conn, """
        SELECT f.season
        FROM fixtures f
        JOIN gameweeks g ON f.gameweek = g.gameweek
        WHERE g.current_gameweek = 1 OR g.next_gameweek = 1
        ORDER BY f.season DESC
        LIMIT 1
    """)
    if row:
        return row["season"]
    # Fallback: most recent season in fixtures
    row = _fetchone(conn, "SELECT MAX(season) AS season FROM fixtures")
    return row["season"] if row else None


# ---------------------------------------------------------------------------
# Homepage queries
# ---------------------------------------------------------------------------

def get_league_table_excluding_gameweek(conn, season, exclude_gameweek):
    """Overall standings for the season, excluding fixtures from a specific gameweek.
    Used to compute pre-GW positions for rank change indicators."""
    return _fetchall(conn, """
        SELECT
            p.player_id,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS correct_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1
          AND f.season = ?
          AND f.gameweek != ?
        GROUP BY p.player_id
        ORDER BY total_points DESC, correct_results DESC, correct_scores DESC, p.player_name ASC
    """, (season, exclude_gameweek))


def get_league_table(conn, season):
    """Overall standings for the season.
    Returns list of dicts sorted by total_points desc, then correct_results desc,
    then correct_scores desc.
    correct_results = all fixtures where result (H/D/A) was correct.
    correct_scores  = fixtures where exact score was correct.
    total_points    = correct_results + correct_scores
                      (exact score earns 2pts: 1 for result + 1 bonus)
    """
    return _fetchall(conn, """
        SELECT
            p.player_id,
            p.player_name,
            p.web_name,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS correct_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1
          AND f.season = ?
        GROUP BY p.player_id, p.player_name, p.web_name
        ORDER BY total_points DESC, correct_results DESC, correct_scores DESC, p.player_name ASC
    """, (season,))


def get_gameweek_fixtures(conn, gameweek, season):
    """Fixtures for a gameweek/season with results (if available)."""
    return _fetchall(conn, """
        SELECT
            f.fixture_id,
            f.kickoff_dttm,
            f.finished,
            f.started,
            f.provisional_finished,
            ht.team_name AS home_team,
            at.team_name AS away_team,
            r.home_goals,
            r.away_goals,
            r.result
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.gameweek = ?
          AND f.season = ?
        ORDER BY f.kickoff_dttm ASC
    """, (gameweek, season))


# ---------------------------------------------------------------------------
# Player page queries
# ---------------------------------------------------------------------------

def get_player(conn, player_id):
    """Return a single active player row or None."""
    return _fetchone(conn, """
        SELECT player_id, player_name, web_name
        FROM players
        WHERE player_id = ? AND active = 1
    """, (player_id,))


def get_all_active_players(conn):
    """All active players ordered by name."""
    return _fetchall(conn, """
        SELECT player_id, player_name, web_name
        FROM players
        WHERE active = 1
        ORDER BY player_name ASC
    """)


def get_player_predicted_table(conn, player_id, season):
    """Build a predicted PL table from a player's predictions for the season.
    Treats each prediction as if it were the real result. Excludes 9-9 placeholders.
    Returns rows ordered by Pts DESC, GD DESC, GF DESC (standard PL order).
    """
    return _fetchall(conn, """
        SELECT
            team_id,
            team_name,
            SUM(P)  AS P,
            SUM(W)  AS W,
            SUM(D)  AS D,
            SUM(L)  AS L,
            SUM(GF) AS GF,
            SUM(GA) AS GA,
            SUM(GF) - SUM(GA)   AS GD,
            SUM(W) * 3 + SUM(D) AS Pts
        FROM (
            SELECT
                ht.team_id,
                ht.team_name,
                1 AS P,
                CASE WHEN pred.predicted_result = 'H' THEN 1 ELSE 0 END AS W,
                CASE WHEN pred.predicted_result = 'D' THEN 1 ELSE 0 END AS D,
                CASE WHEN pred.predicted_result = 'A' THEN 1 ELSE 0 END AS L,
                pred.home_goals AS GF,
                pred.away_goals AS GA
            FROM predictions pred
            JOIN fixtures f  ON pred.fixture_id  = f.fixture_id
            JOIN teams    ht ON f.home_teamid     = ht.team_id
            WHERE pred.player_id = ?
              AND f.season       = ?
              AND f.finished     = 1
              AND NOT (pred.home_goals = 9 AND pred.away_goals = 9)

            UNION ALL

            SELECT
                at.team_id,
                at.team_name,
                1 AS P,
                CASE WHEN pred.predicted_result = 'A' THEN 1 ELSE 0 END AS W,
                CASE WHEN pred.predicted_result = 'D' THEN 1 ELSE 0 END AS D,
                CASE WHEN pred.predicted_result = 'H' THEN 1 ELSE 0 END AS L,
                pred.away_goals AS GF,
                pred.home_goals AS GA
            FROM predictions pred
            JOIN fixtures f  ON pred.fixture_id  = f.fixture_id
            JOIN teams    at ON f.away_teamid     = at.team_id
            WHERE pred.player_id = ?
              AND f.season       = ?
              AND f.finished     = 1
              AND NOT (pred.home_goals = 9 AND pred.away_goals = 9)
        ) sub
        GROUP BY team_id, team_name
        ORDER BY Pts DESC, GD DESC, GF DESC
    """, (player_id, season, player_id, season))


def get_player_prediction_history(conn, player_id, season):
    """All predictions a player has made in a season, with fixture and result data.
    Returns rows ordered by kickoff newest-first."""
    return _fetchall(conn, """
        SELECT
            f.fixture_id,
            f.gameweek,
            f.kickoff_dttm,
            f.finished,
            f.started,
            ht.team_name  AS home_team,
            at.team_name  AS away_team,
            pred.home_goals      AS pred_home,
            pred.away_goals      AS pred_away,
            pred.predicted_result,
            r.home_goals         AS result_home,
            r.away_goals         AS result_away,
            r.result
        FROM predictions pred
        JOIN fixtures f  ON pred.fixture_id  = f.fixture_id
        JOIN teams    ht ON f.home_teamid     = ht.team_id
        JOIN teams    at ON f.away_teamid     = at.team_id
        LEFT JOIN results r ON f.fixture_id  = r.fixture_id
        WHERE pred.player_id = ?
          AND f.season        = ?
        ORDER BY f.kickoff_dttm ASC
    """, (player_id, season))


def get_gameweek_table(conn, gameweek, season):
    """Standings for a single gameweek: correct results, correct scores, points."""
    return _fetchall(conn, """
        SELECT
            p.player_id,
            p.player_name,
            p.web_name,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS correct_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1
          AND f.gameweek = ?
          AND f.season = ?
        GROUP BY p.player_id, p.player_name, p.web_name
        ORDER BY total_points DESC, correct_results DESC, correct_scores DESC, p.player_name ASC
    """, (gameweek, season))


def get_all_gameweeks(conn):
    """All gameweeks ordered descending."""
    return _fetchall(conn, """
        SELECT gameweek, deadline_dttm, current_gameweek, next_gameweek, finished
        FROM gameweeks
        ORDER BY gameweek DESC
    """)


def get_gw_winners(conn, season):
    """Return the top scorer(s) for each finished gameweek in the season.
    Returns dict {gameweek: {"web_name", "player_id", "total_points", "is_tie"}}.
    Ties are flagged but only the first player (alphabetically) is named.
    """
    rows = _fetchall(conn, """
        SELECT
            f.gameweek,
            p.player_id,
            p.web_name,
            p.player_name,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END) AS total_points,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) AS correct_results
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1 AND f.season = ?
        GROUP BY f.gameweek, p.player_id, p.web_name, p.player_name
        ORDER BY f.gameweek ASC, total_points DESC, correct_results DESC, p.player_name ASC
    """, (season,))

    winners = {}
    for row in rows:
        gw = row["gameweek"]
        if gw not in winners:
            winners[gw] = {
                "web_name": row["web_name"],
                "player_id": row["player_id"],
                "total_points": row["total_points"],
                "is_tie": False,
            }
        elif not winners[gw]["is_tie"] and row["total_points"] == winners[gw]["total_points"]:
            winners[gw]["is_tie"] = True
    return winners


def get_gameweek_detail(conn, gw_number):
    """Single gameweek row or None."""
    return _fetchone(conn, """
        SELECT gameweek, deadline_dttm, current_gameweek, next_gameweek, finished
        FROM gameweeks
        WHERE gameweek = ?
    """, (gw_number,))


def get_gameweek_predictions(conn, gameweek, season):
    """All active-player predictions for fixtures in a gameweek/season."""
    return _fetchall(conn, """
        SELECT
            pred.player_id,
            pred.fixture_id,
            pred.home_goals,
            pred.away_goals,
            pred.predicted_result
        FROM predictions pred
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN players p ON pred.player_id = p.player_id
        WHERE f.gameweek = ?
          AND f.season = ?
          AND p.active = 1
    """, (gameweek, season))


def get_active_player_count(conn):
    """Total number of active players."""
    row = _fetchone(conn, "SELECT COUNT(*) AS cnt FROM players WHERE active = 1")
    return row["cnt"] if row else 0


def get_fixture_by_id(conn, fixture_id):
    """Fetch a single fixture with team names and result (if available)."""
    return _fetchone(conn, """
        SELECT
            f.fixture_id,
            f.gameweek,
            f.kickoff_dttm,
            f.finished,
            f.started,
            f.season,
            f.provisional_finished,
            ht.team_name AS home_team,
            at.team_name AS away_team,
            r.home_goals,
            r.away_goals,
            r.result
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.fixture_id = ?
    """, (fixture_id,))


def get_fixture_predictions_detail(conn, fixture_id):
    """All active-player predictions for a fixture, with player info."""
    return _fetchall(conn, """
        SELECT
            p.player_id,
            p.player_name,
            p.web_name,
            pred.home_goals,
            pred.away_goals,
            pred.predicted_result
        FROM predictions pred
        JOIN players p ON pred.player_id = p.player_id
        WHERE pred.fixture_id = ?
          AND p.active = 1
        ORDER BY p.player_name ASC
    """, (fixture_id,))


def get_gameweek_leaderboard(conn, gameweek, season):
    """Per-player breakdown for a single gameweek, ordered by points.
    breakdown.correct_results = correct H/D/A but NOT exact score (1pt each)
    breakdown.exact_scores    = exact score match (2pts each)
    These two are mutually exclusive and sum with incorrect + pending = predictions_made.
    """
    return _fetchall(conn, """
        SELECT
            p.player_id,
            p.player_name,
            COUNT(pred.prediction_id) AS predictions_made,
            COUNT(CASE WHEN r.result IS NOT NULL
                            AND pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS exact_scores,
            COUNT(CASE WHEN r.result IS NOT NULL
                            AND pred.predicted_result = r.result
                            AND NOT (pred.home_goals = r.home_goals
                                     AND pred.away_goals = r.away_goals) THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN r.result IS NOT NULL
                            AND pred.predicted_result != r.result THEN 1 END)
                AS incorrect_predictions,
            COUNT(CASE WHEN r.result IS NULL THEN 1 END)
                AS pending_results,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS _correct_for_sort,
            COUNT(CASE WHEN r.result IS NOT NULL
                            AND pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END) * 2 +
            COUNT(CASE WHEN r.result IS NOT NULL
                            AND pred.predicted_result = r.result
                            AND NOT (pred.home_goals = r.home_goals
                                     AND pred.away_goals = r.away_goals) THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1
          AND f.gameweek = ?
          AND f.season = ?
        GROUP BY p.player_id, p.player_name
        ORDER BY total_points DESC, _correct_for_sort DESC, exact_scores DESC, p.player_name ASC
    """, (gameweek, season))


def get_fixture_prediction_counts(conn, fixture_ids):
    """For a list of fixture IDs, return how many active players have submitted
    a valid (non 9-9) prediction. Returns dict {fixture_id: count}."""
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = _fetchall(conn, f"""
        SELECT pred.fixture_id, COUNT(*) AS cnt
        FROM predictions pred
        JOIN players p ON pred.player_id = p.player_id
        WHERE pred.fixture_id IN ({placeholders})
          AND p.active = 1
          AND NOT (pred.home_goals = 9 AND pred.away_goals = 9)
        GROUP BY pred.fixture_id
    """, fixture_ids)
    return {r["fixture_id"]: r["cnt"] for r in rows}


def get_season_gw_scores(conn, season):
    """Per-player per-GW totals for a season, for finished GWs only (INNER JOIN results).
    Returns all rows sorted by gameweek ASC, total_points DESC.
    Used to derive records: best GW, most exact scores, GW wins, hardest/easiest GW."""
    return _fetchall(conn, """
        SELECT
            f.gameweek,
            p.player_id,
            p.web_name,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END) AS exact_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END) AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN gameweeks g ON f.gameweek = g.gameweek
        WHERE p.active = 1 AND f.season = ? AND g.finished = 1
        GROUP BY f.gameweek, p.player_id, p.web_name
        ORDER BY f.gameweek ASC, total_points DESC, p.player_name ASC
    """, (season,))


def get_fixture_accuracy_counts(conn, fixture_ids):
    """For a list of fixture IDs, return aggregate accuracy across all active players.
    Returns dict {fixture_id: {"exact_scores": int, "correct_results": int}}.
    Only includes fixtures that have results (INNER JOIN on results table)."""
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = _fetchall(conn, f"""
        SELECT
            pred.fixture_id,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END) AS exact_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) AS correct_results
        FROM predictions pred
        JOIN players p ON pred.player_id = p.player_id
        JOIN results r ON pred.fixture_id = r.fixture_id
        WHERE pred.fixture_id IN ({placeholders})
          AND p.active = 1
        GROUP BY pred.fixture_id
    """, fixture_ids)
    return {r["fixture_id"]: {"exact_scores": r["exact_scores"], "correct_results": r["correct_results"]} for r in rows}


# ---------------------------------------------------------------------------
# Cup competition queries
# ---------------------------------------------------------------------------

def get_cup_config(conn, season):
    """Return the cup_config row for a season, or None if not set up."""
    return _fetchone(conn, """
        SELECT config_id, season, num_rounds, start_gameweek, generated_at
        FROM cup_config
        WHERE season = ?
    """, (season,))


def get_cup_matches(conn, season):
    """All cup_matches for a season, joined with player names.
    Ordered by round_number then match_number."""
    return _fetchall(conn, """
        SELECT
            cm.match_id,
            cm.season,
            cm.round_number,
            cm.match_number,
            cm.player1_id,
            cm.player2_id,
            cm.player1_seed,
            cm.player2_seed,
            cm.is_bye,
            cm.gameweek,
            cm.next_match_id,
            cm.next_match_slot,
            p1.player_name AS player1_name,
            p1.web_name    AS player1_web_name,
            p2.player_name AS player2_name,
            p2.web_name    AS player2_web_name
        FROM cup_matches cm
        LEFT JOIN players p1 ON cm.player1_id = p1.player_id
        LEFT JOIN players p2 ON cm.player2_id = p2.player_id
        WHERE cm.season = ?
        ORDER BY cm.round_number ASC, cm.match_number ASC
    """, (season,))


def get_cup_gw_data(conn, season, gameweeks):
    """Predictions + results for all active players across the given gameweeks.

    Returns a nested dict:
        {gameweek: {player_id: [fixture_rows]}}
    Each fixture row contains pred_home, pred_away, predicted_result,
    result, result_home, result_away, fixture_id, gameweek.
    """
    if not gameweeks:
        return {}
    placeholders = ",".join("?" * len(gameweeks))
    params = list(gameweeks) + [season]
    rows = _fetchall(conn, f"""
        SELECT
            f.gameweek,
            pred.player_id,
            pred.fixture_id,
            pred.home_goals    AS pred_home,
            pred.away_goals    AS pred_away,
            pred.predicted_result,
            r.home_goals       AS result_home,
            r.away_goals       AS result_away,
            r.result
        FROM predictions pred
        JOIN fixtures f  ON pred.fixture_id = f.fixture_id
        JOIN players  p  ON pred.player_id  = p.player_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.gameweek IN ({placeholders})
          AND f.season = ?
          AND p.active = 1
        ORDER BY f.gameweek, pred.player_id, pred.fixture_id
    """, params)

    result = {}
    for row in rows:
        gw = row["gameweek"]
        pid = row["player_id"]
        result.setdefault(gw, {}).setdefault(pid, []).append(row)
    return result


# ---------------------------------------------------------------------------
# History queries
# ---------------------------------------------------------------------------

def get_all_time_table(conn):
    """All-time standings across all seasons. Excludes pundits. No active filter."""
    return _fetchall(conn, """
        SELECT
            p.player_id,
            p.player_name,
            p.web_name,
            COUNT(DISTINCT f.season) AS seasons_played,
            COUNT(r.result)          AS games_played,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS correct_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.pundit = 0
        GROUP BY p.player_id, p.player_name, p.web_name
        ORDER BY total_points DESC, correct_results DESC, correct_scores DESC, p.player_name ASC
    """)


def get_all_season_standings(conn, exclude_season):
    """Per-season standings for all non-pundit players, excluding the current season."""
    return _fetchall(conn, """
        SELECT
            f.season,
            p.player_id,
            p.player_name,
            p.web_name,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END)
                AS correct_results,
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS correct_scores,
            COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
            COUNT(CASE WHEN pred.home_goals = r.home_goals
                            AND pred.away_goals = r.away_goals THEN 1 END)
                AS total_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.pundit = 0
          AND f.season != ?
        GROUP BY f.season, p.player_id, p.player_name, p.web_name
        ORDER BY f.season DESC, total_points DESC, correct_results DESC, correct_scores DESC, p.player_name ASC
    """, (exclude_season,))
