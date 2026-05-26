from flask import Blueprint, render_template
from services.database import (
    get_connection,
    get_display_gameweek,
    get_gw_table_gameweek,
    get_current_season,
    get_league_table,
    get_league_table_excluding_gameweek,
    get_gameweek_fixtures,
    get_gameweek_table,
    get_gameweek_detail,
    get_active_player_count,
    get_fixture_prediction_counts,
)
from services.scoring import is_prediction_visible

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    with get_connection() as conn:
        season = get_current_season(conn)
        gameweek = get_display_gameweek(conn)
        gw_detail = get_gameweek_detail(conn, gameweek) if gameweek else None
        gw_deadline = gw_detail["deadline_dttm"] if gw_detail else None
        gw_table_gameweek = get_gw_table_gameweek(conn)
        table = get_league_table(conn, season)
        fixtures = get_gameweek_fixtures(conn, gameweek, season) if gameweek else []
        gw_table = get_gameweek_table(conn, gw_table_gameweek, season) if gw_table_gameweek else []

        # Merge GW points into the main table
        gw_points_by_player = {r["player_id"]: r["total_points"] for r in gw_table}
        for i, row in enumerate(table, start=1):
            row["position"] = i
            row["gw_points"] = gw_points_by_player.get(row["player_id"], 0)

        # Rank change indicators (only during a live unfinished gameweek)
        is_live_gameweek = bool(gw_detail and gw_detail.get("current_gameweek") == 1 and not gw_detail.get("finished"))
        if is_live_gameweek and gw_table_gameweek:
            prev_table = get_league_table_excluding_gameweek(conn, season, gw_table_gameweek)
            prev_positions = {r["player_id"]: i for i, r in enumerate(prev_table, start=1)}
            for row in table:
                prev_pos = prev_positions.get(row["player_id"])
                row["rank_change"] = None if prev_pos is None else prev_pos - row["position"]
        else:
            for row in table:
                row["rank_change"] = 0

        # Determine prediction visibility per fixture
        active_count = get_active_player_count(conn)
        fixture_ids = [f["fixture_id"] for f in fixtures]
        pred_counts = get_fixture_prediction_counts(conn, fixture_ids)

        for f in fixtures:
            count = pred_counts.get(f["fixture_id"], 0)
            f["predictions_visible"] = is_prediction_visible(f["kickoff_dttm"], count, active_count)

    return render_template(
        "home/index.html",
        table=table,
        gw_table_gameweek=gw_table_gameweek,
        fixtures=fixtures,
        gameweek=gameweek,
        gw_deadline=gw_deadline,
        season=season,
        is_live_gameweek=is_live_gameweek,
    )
