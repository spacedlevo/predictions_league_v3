from collections import defaultdict

from flask import Blueprint, render_template, request

from services.database import (
    get_all_seasons,
    get_all_seasons_gw_scores,
    get_connection,
    get_current_season,
    get_season_gw_scores,
)

bp = Blueprint("records", __name__, url_prefix="/records")


def _compute_records(rows, multi_season=False):
    by_gw = defaultdict(list)
    for row in rows:
        key = (row["season"], row["gameweek"])
        by_gw[key].append(row)

    best_gw_score = None
    best_gw_exact = None
    gw_wins = defaultdict(int)
    player_names = {}
    gw_averages = []

    for (season_str, gw), players in sorted(by_gw.items()):
        if not players:
            continue

        top_pts = players[0]["total_points"]
        top_exact = max(p["exact_scores"] for p in players)

        # Apply tiebreaker chain: points > correct_results > exact_scores
        candidates = [p for p in players if p["total_points"] == top_pts]
        top_results = max(p["correct_results"] for p in candidates)
        candidates = [p for p in candidates if p["correct_results"] == top_results]
        top_winner_exact = max(p["exact_scores"] for p in candidates)
        top_scorers = [p for p in candidates if p["exact_scores"] == top_winner_exact]
        if best_gw_score is None or top_pts > best_gw_score["points"]:
            best_gw_score = {
                "players": top_scorers,
                "points": top_pts,
                "gameweek": gw,
                "gw_season": season_str if multi_season else None,
            }
        elif top_pts == best_gw_score["points"]:
            best_gw_score["players"] += top_scorers
            best_gw_score["gameweek"] = None
            best_gw_score["gw_season"] = None

        top_exact_scorers = [p for p in players if p["exact_scores"] == top_exact]
        if best_gw_exact is None or top_exact > best_gw_exact["exact_scores"]:
            best_gw_exact = {
                "players": top_exact_scorers,
                "exact_scores": top_exact,
                "gameweek": gw,
                "gw_season": season_str if multi_season else None,
            }
        elif top_exact == best_gw_exact["exact_scores"]:
            best_gw_exact["players"] += top_exact_scorers
            best_gw_exact["gameweek"] = None
            best_gw_exact["gw_season"] = None

        for p in top_scorers:
            player_names[p["player_id"]] = p["web_name"]
            gw_wins[p["player_id"]] += 1

        for p in players:
            player_names[p["player_id"]] = p["web_name"]

        avg = sum(p["total_points"] for p in players) / len(players)
        gw_averages.append({
            "gameweek": gw,
            "gw_season": season_str if multi_season else None,
            "avg": avg,
            "player_count": len(players),
        })

    wins_table = sorted(
        [{"player_id": pid, "web_name": player_names[pid], "wins": w} for pid, w in gw_wins.items()],
        key=lambda r: (-r["wins"], r["web_name"]),
    )

    scored_gws = [g for g in gw_averages if g["player_count"] > 1]
    hardest_gw = min(scored_gws, key=lambda g: g["avg"]) if scored_gws else None
    easiest_gw = max(scored_gws, key=lambda g: g["avg"]) if scored_gws else None

    for record in [best_gw_score, best_gw_exact]:
        if record:
            seen = set()
            record["players"] = [
                p for p in record["players"]
                if not (p["player_id"] in seen or seen.add(p["player_id"]))
            ]

    return best_gw_score, best_gw_exact, wins_table, hardest_gw, easiest_gw


@bp.route("/")
def index():
    with get_connection() as conn:
        seasons = get_all_seasons(conn)
        current_season = get_current_season(conn)

    selected_season = request.args.get("season", current_season)
    all_seasons = selected_season == "all"

    with get_connection() as conn:
        if all_seasons:
            rows = get_all_seasons_gw_scores(conn)
        else:
            rows = get_season_gw_scores(conn, selected_season)

    multi_season = all_seasons
    best_gw_score, best_gw_exact, wins_table, hardest_gw, easiest_gw = _compute_records(rows, multi_season)

    return render_template(
        "records/index.html",
        seasons=seasons,
        selected_season=selected_season,
        all_seasons=all_seasons,
        best_gw_score=best_gw_score,
        best_gw_exact=best_gw_exact,
        wins_table=wins_table,
        hardest_gw=hardest_gw,
        easiest_gw=easiest_gw,
    )
