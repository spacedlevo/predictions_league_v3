from collections import defaultdict
from flask import Blueprint, render_template, abort
from services.database import (
    get_connection,
    get_current_season,
    get_player,
    get_player_predicted_table,
    get_player_prediction_history,
    get_active_player_count,
    get_fixture_prediction_counts,
)
from services.scoring import is_prediction_visible, calc_points

bp = Blueprint("player", __name__, url_prefix="/player")


@bp.route("/<int:player_id>")
def profile(player_id):
    with get_connection() as conn:
        player = get_player(conn, player_id)
        if not player:
            abort(404)

        season = get_current_season(conn)
        predicted_table = get_player_predicted_table(conn, player_id, season)
        history = get_player_prediction_history(conn, player_id, season)

        # Add position to predicted table
        for i, row in enumerate(predicted_table, start=1):
            row["position"] = i

        # Visibility + points for history
        active_count = get_active_player_count(conn)
        fixture_ids = [h["fixture_id"] for h in history]
        pred_counts = get_fixture_prediction_counts(conn, fixture_ids)

        for h in history:
            count = pred_counts.get(h["fixture_id"], 0)
            h["visible"] = is_prediction_visible(h["kickoff_dttm"], count, active_count)
            h["placeholder"] = h["pred_home"] == 9 and h["pred_away"] == 9
            h["points"] = calc_points(h["predicted_result"], h["pred_home"], h["pred_away"], h["result"], h["result_home"], h["result_away"]) if h["visible"] else None

        # Group history by gameweek, newest GW first
        gw_map = {}
        for h in history:
            gw = h["gameweek"]
            if gw not in gw_map:
                gw_map[gw] = {"fixtures": [], "total_pts": 0, "finished_count": 0}
            gw_map[gw]["fixtures"].append(h)
            if h["points"] is not None:
                gw_map[gw]["total_pts"] += h["points"]
                gw_map[gw]["finished_count"] += 1
        history_by_gw = sorted(gw_map.items(), key=lambda x: x[0], reverse=True)

        # Summary stats (finished fixtures only)
        total_points = sum(h["points"] for h in history if h["points"] is not None)
        correct_scores = sum(1 for h in history if h["points"] == 2)
        correct_results = sum(1 for h in history if h["points"] is not None and h["points"] >= 1)
        gws_with_results = sum(1 for gw_data in gw_map.values() if gw_data["finished_count"] > 0)
        avg_ppg = round(total_points / gws_with_results, 1) if gws_with_results else None
        stats = {
            "total_points": total_points,
            "correct_scores": correct_scores,
            "correct_results": correct_results,
            "avg_ppg": avg_ppg,
        }

    return render_template(
        "player/profile.html",
        player=player,
        season=season,
        predicted_table=predicted_table,
        history_by_gw=history_by_gw,
        stats=stats,
    )
