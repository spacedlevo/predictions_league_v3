from collections import defaultdict

from flask import Blueprint, render_template

from services.database import (
    get_all_season_standings,
    get_all_time_table,
    get_connection,
    get_current_season,
)

bp = Blueprint("history", __name__, url_prefix="/history")


@bp.route("/")
def index():
    with get_connection() as conn:
        current_season = get_current_season(conn)
        all_time = get_all_time_table(conn)
        season_rows = get_all_season_standings(conn, current_season or "")

    # Add PPG and tied positions to the all-time table
    for i, row in enumerate(all_time):
        gp = row["games_played"] or 0
        row["ppg"] = round(row["total_points"] / gp, 2) if gp else 0.0
        if i == 0:
            row["position"] = 1
        else:
            prev = all_time[i - 1]
            if (
                row["total_points"] == prev["total_points"]
                and row["correct_results"] == prev["correct_results"]
                and row["correct_scores"] == prev["correct_scores"]
            ):
                row["position"] = prev["position"]
            else:
                row["position"] = i + 1

    # Group by season and identify winner(s) per season
    by_season = defaultdict(list)
    for row in season_rows:
        by_season[row["season"]].append(row)

    season_winners = []
    seasons_table = []
    for season in sorted(by_season.keys(), reverse=True):
        players = by_season[season]
        if not players:
            continue
        top = players[0]
        winners = [top]
        for p in players[1:]:
            if (
                p["total_points"] == top["total_points"]
                and p["correct_results"] == top["correct_results"]
                and p["correct_scores"] == top["correct_scores"]
            ):
                winners.append(p)
            else:
                break
        season_winners.append({"season": season, "winners": winners})

        for i, row in enumerate(players):
            if i == 0:
                row["position"] = 1
            else:
                prev = players[i - 1]
                if (
                    row["total_points"] == prev["total_points"]
                    and row["correct_results"] == prev["correct_results"]
                    and row["correct_scores"] == prev["correct_scores"]
                ):
                    row["position"] = prev["position"]
                else:
                    row["position"] = i + 1
        seasons_table.append({"season": season, "players": players})

    return render_template(
        "history/index.html",
        all_time=all_time,
        season_winners=season_winners,
        seasons_table=seasons_table,
        season=current_season,
    )
