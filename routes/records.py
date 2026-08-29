from collections import defaultdict

from flask import Blueprint, render_template

from services.database import get_connection, get_current_season, get_season_gw_scores

bp = Blueprint("records", __name__, url_prefix="/records")


@bp.route("/")
def index():
    with get_connection() as conn:
        season = get_current_season(conn)
        rows = get_season_gw_scores(conn, season)

    # Group rows by gameweek
    by_gw = defaultdict(list)
    for row in rows:
        by_gw[row["gameweek"]].append(row)

    best_gw_score = None        # {"players": [...], "points": int, "gameweek": int}
    best_gw_exact = None        # {"players": [...], "exact_scores": int, "gameweek": int}
    gw_wins = defaultdict(int)  # player_id -> win count
    player_names = {}           # player_id -> web_name
    gw_averages = []            # [(gameweek, avg_pts)]

    for gw, players in sorted(by_gw.items()):
        if not players:
            continue

        top_pts = players[0]["total_points"]
        top_exact = max(p["exact_scores"] for p in players)

        # Best single-GW score
        top_scorers = [p for p in players if p["total_points"] == top_pts]
        if best_gw_score is None or top_pts > best_gw_score["points"]:
            best_gw_score = {"players": top_scorers, "points": top_pts, "gameweek": gw}
        elif top_pts == best_gw_score["points"]:
            best_gw_score["players"] += top_scorers
            best_gw_score["gameweek"] = None  # spans multiple GWs

        # Most exact scores in a single GW
        top_exact_scorers = [p for p in players if p["exact_scores"] == top_exact]
        if best_gw_exact is None or top_exact > best_gw_exact["exact_scores"]:
            best_gw_exact = {"players": top_exact_scorers, "exact_scores": top_exact, "gameweek": gw}
        elif top_exact == best_gw_exact["exact_scores"]:
            best_gw_exact["players"] += top_exact_scorers
            best_gw_exact["gameweek"] = None

        # GW wins (top scorer wins; ties = all tied players share the win)
        for p in top_scorers:
            player_names[p["player_id"]] = p["web_name"]
            gw_wins[p["player_id"]] += 1

        # Track all player names
        for p in players:
            player_names[p["player_id"]] = p["web_name"]

        # GW average
        avg = sum(p["total_points"] for p in players) / len(players)
        gw_averages.append({"gameweek": gw, "avg": avg, "player_count": len(players)})

    # GW wins leaderboard
    wins_table = sorted(
        [{"player_id": pid, "web_name": player_names[pid], "wins": w} for pid, w in gw_wins.items()],
        key=lambda r: (-r["wins"], r["web_name"]),
    )

    # Hardest / easiest GW (only when multiple players participated)
    scored_gws = [g for g in gw_averages if g["player_count"] > 1]
    hardest_gw = min(scored_gws, key=lambda g: g["avg"]) if scored_gws else None
    easiest_gw = max(scored_gws, key=lambda g: g["avg"]) if scored_gws else None

    # Deduplicate best_gw_score and best_gw_exact player lists
    if best_gw_score:
        seen = set()
        best_gw_score["players"] = [
            p for p in best_gw_score["players"] if not (p["player_id"] in seen or seen.add(p["player_id"]))
        ]
    if best_gw_exact:
        seen = set()
        best_gw_exact["players"] = [
            p for p in best_gw_exact["players"] if not (p["player_id"] in seen or seen.add(p["player_id"]))
        ]

    return render_template(
        "records/index.html",
        season=season,
        best_gw_score=best_gw_score,
        best_gw_exact=best_gw_exact,
        wins_table=wins_table,
        hardest_gw=hardest_gw,
        easiest_gw=easiest_gw,
    )
