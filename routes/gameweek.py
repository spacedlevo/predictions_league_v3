from flask import Blueprint, render_template, abort
from services.database import (
    get_connection,
    get_current_season,
    get_all_gameweeks,
    get_gw_winners,
    get_gameweek_detail,
    get_gameweek_fixtures,
    get_gameweek_table,
    get_gameweek_predictions,
    get_all_active_players,
    get_active_player_count,
    get_fixture_prediction_counts,
    get_fixture_accuracy_counts,
)
from services.scoring import is_prediction_visible, calc_points

bp = Blueprint("gameweek", __name__, url_prefix="/gameweek")

def _short_team(name):
    lower = name.lower()
    if "manchester" in lower or "man " in lower:
        if "united" in lower or "utd" in lower:
            return "MUN"
        if "city" in lower:
            return "MCI"
    return name[:3].upper()


@bp.route("/")
def list_gameweeks():
    with get_connection() as conn:
        season = get_current_season(conn)
        gameweeks = get_all_gameweeks(conn)
        gw_winners = get_gw_winners(conn, season)

    for gw in gameweeks:
        gw["winner"] = gw_winners.get(gw["gameweek"])

    featured_gw = (
        next((gw for gw in gameweeks if gw["current_gameweek"]), None)
        or next((gw for gw in gameweeks if gw["next_gameweek"]), None)
    )
    rest = sorted(
        [gw for gw in gameweeks if gw is not featured_gw],
        key=lambda g: g["gameweek"],
    )
    return render_template("gameweek/list.html", featured_gw=featured_gw, gameweeks=rest, season=season)


@bp.route("/<int:gw_number>")
def view(gw_number):
    with get_connection() as conn:
        gw = get_gameweek_detail(conn, gw_number)
        if not gw:
            abort(404)

        all_gws = {row["gameweek"] for row in get_all_gameweeks(conn)}
        prev_gw = gw_number - 1 if (gw_number - 1) in all_gws else None
        next_gw = gw_number + 1 if (gw_number + 1) in all_gws else None

        season = get_current_season(conn)
        fixtures = get_gameweek_fixtures(conn, gw_number, season)
        gw_table = get_gameweek_table(conn, gw_number, season)
        players = get_all_active_players(conn)
        raw_preds = get_gameweek_predictions(conn, gw_number, season)

        # Visibility per fixture
        active_count = get_active_player_count(conn)
        fixture_ids = [f["fixture_id"] for f in fixtures]
        pred_counts = get_fixture_prediction_counts(conn, fixture_ids)

        for f in fixtures:
            f["home_team_short"] = _short_team(f["home_team"])
            f["away_team_short"] = _short_team(f["away_team"])

        accuracy_counts = get_fixture_accuracy_counts(conn, fixture_ids)
        fixture_map = {}
        for f in fixtures:
            count = pred_counts.get(f["fixture_id"], 0)
            f["visible"] = is_prediction_visible(f["kickoff_dttm"], count, active_count)
            f["accuracy"] = accuracy_counts.get(f["fixture_id"])
            fixture_map[f["fixture_id"]] = f

        # Build prediction grid: {player_id: {fixture_id: cell_dict}}
        pred_grid = {}
        for pred in raw_preds:
            pid = pred["player_id"]
            fid = pred["fixture_id"]
            fixture = fixture_map.get(fid, {})
            visible = fixture.get("visible", False)
            is_placeholder = pred["home_goals"] == 9 and pred["away_goals"] == 9
            cell = {"visible": visible, "placeholder": is_placeholder}
            if visible:
                cell["home"] = pred["home_goals"]
                cell["away"] = pred["away_goals"]
                cell["predicted_result"] = pred["predicted_result"]
                cell["pts"] = calc_points(pred["predicted_result"], pred["home_goals"], pred["away_goals"], fixture.get("result"), fixture.get("home_goals"), fixture.get("away_goals"))
            if pid not in pred_grid:
                pred_grid[pid] = {}
            pred_grid[pid][fid] = cell

        # Order players: GW-ranked first, then remaining active players
        ranked_ids = [r["player_id"] for r in gw_table]
        all_player_ids = [p["player_id"] for p in players]
        unranked = [pid for pid in all_player_ids if pid not in ranked_ids]
        player_map = {p["player_id"]: p for p in players}
        ordered_players = [
            player_map[pid] for pid in ranked_ids + unranked if pid in player_map
        ]

        gw_points_map = {r["player_id"]: r for r in gw_table}
        for p in ordered_players:
            row = gw_points_map.get(p["player_id"])
            p["gw_pts"] = row["total_points"] if row else 0
            p["gw_results"] = row["correct_results"] if row else 0
            p["gw_scores"] = row["correct_scores"] if row else 0

        alpha_players = sorted(ordered_players, key=lambda p: p["web_name"].lower())

        # Stats cards
        total_fixtures = len(fixtures)
        total_possible = active_count * total_fixtures if total_fixtures else 0
        total_submitted = sum(pred_counts.get(f["fixture_id"], 0) for f in fixtures)
        pct_submitted = round(100 * total_submitted / total_possible) if total_possible else None

        total_exact_scores = sum(p["gw_scores"] for p in ordered_players)
        total_correct_results = sum(p["gw_results"] for p in ordered_players)

        has_results = any(f.get("result") for f in fixtures)
        if has_results and ordered_players:
            avg_pts = round(sum(p["gw_pts"] for p in ordered_players) / len(ordered_players), 1)
        else:
            avg_pts = None

        gw_stats = {
            "pct_submitted": pct_submitted,
            "total_exact_scores": total_exact_scores,
            "total_correct_results": total_correct_results,
            "avg_pts": avg_pts,
        }

    return render_template(
        "gameweek/view.html",
        gw=gw,
        gw_number=gw_number,
        prev_gw=prev_gw,
        next_gw=next_gw,
        season=season,
        fixtures=fixtures,
        ordered_players=ordered_players,
        alpha_players=alpha_players,
        pred_grid=pred_grid,
        gw_stats=gw_stats,
    )
