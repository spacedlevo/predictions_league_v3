from collections import defaultdict

from flask import Blueprint, render_template, request

from services.database import (
    get_connection,
    get_current_season,
    get_players_by_season,
    get_predictions_for_custom_league,
    get_season_gw_ranges,
)

bp = Blueprint("custom_league", __name__, url_prefix="/custom-league")

TIEBREAK_OPTIONS = [
    ("scores", "Most correct scores"),
    ("results", "Most correct results"),
    ("alphabetical", "Alphabetical"),
]


def _calc_pts(row, pts_score, pts_result, nine_nine):
    if nine_nine == "exclude" and row["pred_home"] == 9 and row["pred_away"] == 9:
        return 0, False, False
    is_exact = row["pred_home"] == row["res_home"] and row["pred_away"] == row["res_away"]
    is_correct_result = row["predicted_result"] == row["res_result"]
    if is_exact:
        return pts_score, True, True
    if is_correct_result:
        return pts_result, False, True
    return 0, False, False


def _assign_positions(table, sort_key_fn):
    for i, row in enumerate(table):
        if i == 0:
            row["position"] = 1
        else:
            prev = table[i - 1]
            row["position"] = (
                prev["position"]
                if sort_key_fn(row) == sort_key_fn(prev)
                else i + 1
            )


@bp.route("/")
def index():
    with get_connection() as conn:
        season_ranges_rows = get_season_gw_ranges(conn)
        current_season = get_current_season(conn)
        player_rows = get_players_by_season(conn)

    season_ranges = {
        r["season"]: {"min": r["min_gw"], "max": r["max_gw"]}
        for r in season_ranges_rows
    }
    all_seasons = [r["season"] for r in season_ranges_rows]

    # Build {season: [{"player_id": ..., "web_name": ...}, ...]}
    season_players = {}
    for row in player_rows:
        s = row["season"]
        if s not in season_players:
            season_players[s] = []
        season_players[s].append({"player_id": row["player_id"], "web_name": row["web_name"]})

    # Flat name lookup across all seasons (for scoring label fallback)
    player_name_map = {}
    for players in season_players.values():
        for p in players:
            player_name_map[p["player_id"]] = p["web_name"]

    generate = bool(request.args.get("season"))

    fv_season = request.args.get("season") or current_season or (all_seasons[0] if all_seasons else "")
    gw_range = season_ranges.get(fv_season, {})

    try:
        fv_gw_start = int(request.args.get("gw_start") or gw_range.get("min", 1))
    except (ValueError, TypeError):
        fv_gw_start = gw_range.get("min", 1)

    try:
        fv_gw_end = int(request.args.get("gw_end") or gw_range.get("max", 38))
    except (ValueError, TypeError):
        fv_gw_end = gw_range.get("max", 38)

    try:
        fv_pts_score = max(0, min(10, int(request.args.get("pts_score") or 2)))
    except (ValueError, TypeError):
        fv_pts_score = 2

    try:
        fv_pts_result = max(0, min(10, int(request.args.get("pts_result") or 1)))
    except (ValueError, TypeError):
        fv_pts_result = 1

    fv_nine_nine = request.args.get("nine_nine", "include")
    if fv_nine_nine not in ("include", "exclude"):
        fv_nine_nine = "include"

    fv_tiebreak = request.args.get("tiebreak", "scores")
    if fv_tiebreak not in ("scores", "results", "alphabetical"):
        fv_tiebreak = "scores"

    # Player selection: all season players on first load; from URL on generate
    season_player_ids = [p["player_id"] for p in season_players.get(fv_season, [])]
    if generate:
        raw = request.args.getlist("players")
        fv_player_ids = [int(x) for x in raw if x.isdigit()]
    else:
        fv_player_ids = list(season_player_ids)

    table = None
    if generate and fv_player_ids:
        with get_connection() as conn:
            rows = get_predictions_for_custom_league(
                conn, fv_player_ids, fv_season, fv_gw_start, fv_gw_end
            )

        totals = {
            pid: {
                "player_id": pid,
                "web_name": player_name_map.get(pid, f"Player {pid}"),
                "total_points": 0,
                "correct_scores": 0,
                "correct_results": 0,
            }
            for pid in fv_player_ids
        }

        for row in rows:
            pid = row["player_id"]
            if pid not in totals:
                continue
            pts, is_exact, is_result = _calc_pts(row, fv_pts_score, fv_pts_result, fv_nine_nine)
            totals[pid]["total_points"] += pts
            if is_exact:
                totals[pid]["correct_scores"] += 1
            if is_result:
                totals[pid]["correct_results"] += 1

        table = list(totals.values())

        if fv_tiebreak == "scores":
            key = lambda r: (-r["total_points"], -r["correct_scores"], -r["correct_results"], r["web_name"])
            tie_key = lambda r: (-r["total_points"], -r["correct_scores"], -r["correct_results"])
        elif fv_tiebreak == "results":
            key = lambda r: (-r["total_points"], -r["correct_results"], -r["correct_scores"], r["web_name"])
            tie_key = lambda r: (-r["total_points"], -r["correct_results"], -r["correct_scores"])
        else:
            key = lambda r: (-r["total_points"], r["web_name"])
            tie_key = lambda r: (-r["total_points"], r["web_name"])

        table.sort(key=key)
        _assign_positions(table, tie_key)

    form_values = {
        "season": fv_season,
        "gw_start": fv_gw_start,
        "gw_end": fv_gw_end,
        "pts_score": fv_pts_score,
        "pts_result": fv_pts_result,
        "nine_nine": fv_nine_nine,
        "tiebreak": fv_tiebreak,
        "player_ids": set(fv_player_ids),
    }

    return render_template(
        "custom_league/index.html",
        all_seasons=all_seasons,
        season_ranges=season_ranges,
        season_players=season_players,
        tiebreak_options=TIEBREAK_OPTIONS,
        form_values=form_values,
        table=table,
        generate=generate,
        season=fv_season,
    )
