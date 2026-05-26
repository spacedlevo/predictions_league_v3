from flask import Blueprint, jsonify
from services.database import (
    get_connection,
    get_all_active_players,
    get_current_season,
    get_gameweek_detail,
    get_gameweek_leaderboard,
)

bp = Blueprint("api", __name__, url_prefix="/api/v1")


@bp.route("/gameweek/<int:gw_number>/leaderboard")
def gameweek_leaderboard(gw_number):
    with get_connection() as conn:
        gw = get_gameweek_detail(conn, gw_number)
        if not gw:
            return jsonify({
                "success": False,
                "status_code": 404,
                "message": f"Gameweek {gw_number} not found",
            }), 404

        season = get_current_season(conn)
        rows = get_gameweek_leaderboard(conn, gw_number, season)

    leaderboard = [
        {
            "position": i,
            "player": {"id": r["player_id"], "name": r["player_name"].lower()},
            "total_points": r["total_points"],
            "predictions_made": r["predictions_made"],
            "breakdown": {
                "exact_scores": r["exact_scores"],
                "correct_results": r["correct_results"],
                "incorrect_predictions": r["incorrect_predictions"],
                "pending_results": r["pending_results"],
            },
        }
        for i, r in enumerate(rows, 1)
    ]

    points = [r["total_points"] for r in rows]
    summary = {
        "highest_score": max(points) if points else 0,
        "lowest_score": min(points) if points else 0,
        "average_score": round(sum(points) / len(points), 1) if points else 0,
    }

    total = len(leaderboard)
    return jsonify({
        "success": True,
        "status_code": 200,
        "message": f"Successfully retrieved gameweek {gw_number} leaderboard with {total} players",
        "data": {
            "gameweek": gw_number,
            "leaderboard": leaderboard,
            "summary": summary,
            "total_players": total,
        },
    }), 200


@bp.route("/players")
def players():
    with get_connection() as conn:
        rows = get_all_active_players(conn)

    player_list = [
        {"id": r["player_id"], "name": r["player_name"].lower()}
        for r in rows
    ]
    total = len(player_list)

    return jsonify({
        "success": True,
        "status_code": 200,
        "message": f"Successfully retrieved {total} active players",
        "data": {
            "players": player_list,
            "total_count": total,
        },
    }), 200
