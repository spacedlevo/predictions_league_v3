from flask import Blueprint, render_template, abort
from services.database import (
    get_connection,
    get_current_season,
    get_fixture_by_id,
    get_fixture_predictions_detail,
    get_active_player_count,
    get_fixture_prediction_counts,
)
from services.scoring import is_prediction_visible, calc_points

bp = Blueprint("fixture", __name__, url_prefix="/fixture")


@bp.route("/<int:fixture_id>")
def detail(fixture_id):
    with get_connection() as conn:
        fixture = get_fixture_by_id(conn, fixture_id)
        if not fixture:
            abort(404)

        season = get_current_season(conn)
        raw_preds = get_fixture_predictions_detail(conn, fixture_id)
        active_count = get_active_player_count(conn)
        pred_counts = get_fixture_prediction_counts(conn, [fixture_id])
        pred_count = pred_counts.get(fixture_id, 0)
        visible = is_prediction_visible(fixture["kickoff_dttm"], pred_count, active_count)

        # Per-player data with points
        players_data = []
        for pred in raw_preds:
            is_placeholder = pred["home_goals"] == 9 and pred["away_goals"] == 9
            row = {
                "player_id": pred["player_id"],
                "web_name": pred["web_name"],
                "player_name": pred["player_name"],
            }
            if visible and not is_placeholder:
                row.update({
                    "visible": True,
                    "home": pred["home_goals"],
                    "away": pred["away_goals"],
                    "predicted_result": pred["predicted_result"],
                    "pts": calc_points(pred["predicted_result"], pred["home_goals"], pred["away_goals"], fixture.get("result"), fixture.get("home_goals"), fixture.get("away_goals")),
                })
            else:
                row.update({"visible": False, "placeholder": is_placeholder})
            players_data.append(row)

        # Vote counts and score frequency (visible, non-placeholder predictions only)
        vote_counts = {"H": 0, "D": 0, "A": 0}
        score_freq = {}
        score_freq_by_result = {"H": {}, "D": {}, "A": {}}
        for row in players_data:
            if row.get("visible"):
                result_key = row["predicted_result"]
                vote_counts[result_key] = vote_counts.get(result_key, 0) + 1
                score_key = f"{row['home']}–{row['away']}"
                score_freq[score_key] = score_freq.get(score_key, 0) + 1
                if result_key in score_freq_by_result:
                    score_freq_by_result[result_key][score_key] = score_freq_by_result[result_key].get(score_key, 0) + 1

        total_votes = sum(vote_counts.values())

        popular_scores = sorted(
            [{"score": s, "count": c} for s, c in score_freq.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
        for s in popular_scores:
            s["pct"] = round(s["count"] / total_votes * 100) if total_votes else 0

    return render_template(
        "fixture/detail.html",
        fixture=fixture,
        season=season,
        visible=visible,
        players_data=players_data,
        vote_counts=vote_counts,
        total_votes=total_votes,
        popular_scores=popular_scores,
        score_freq=score_freq,
        score_freq_by_result=score_freq_by_result,
    )
