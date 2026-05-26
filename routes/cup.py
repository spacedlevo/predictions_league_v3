from flask import Blueprint, render_template
from services.database import (
    get_connection,
    get_current_season,
    get_cup_config,
    get_cup_matches,
    get_cup_gw_data,
)
from services.cup_logic import resolve_bracket, round_name

bp = Blueprint("cup", __name__, url_prefix="/cup")


@bp.route("/")
def index():
    try:
        with get_connection() as conn:
            season = get_current_season(conn)
            config = get_cup_config(conn, season)

            if not config:
                return render_template("cup/bracket.html", season=season, config=None)

            raw_matches = get_cup_matches(conn, season)
            cup_gameweeks = list(range(config["start_gameweek"], 39))
            gw_data = get_cup_gw_data(conn, season, cup_gameweeks)

    except Exception as e:
        # Cup tables don't exist yet — treat as not configured
        import logging
        logging.getLogger(__name__).warning("Cup tables not available: %s", e)
        return render_template("cup/bracket.html", season=None, config=None)

    # Determine which gameweeks are fully finished (all fixtures have results)
    finished_gameweeks = set()
    for gw, player_map in gw_data.items():
        gw_complete = all(
            row.get("result") is not None
            for fixtures in player_map.values()
            for row in fixtures
        )
        if gw_complete and player_map:
            finished_gameweeks.add(gw)

    matches = resolve_bracket(raw_matches, gw_data, finished_gameweeks)

    num_rounds = config["num_rounds"]

    rounds = []
    for rnd in range(1, num_rounds + 1):
        rnd_matches = sorted(
            [m for m in matches if m["round_number"] == rnd],
            key=lambda m: m["match_number"],
        )
        if not rnd_matches:
            continue

        gw = rnd_matches[0]["gameweek"]
        any_live     = any(m["status"] == "live"     for m in rnd_matches)
        any_complete = any(m["status"] == "complete"  for m in rnd_matches)
        any_pending  = any(m["status"] in ("upcoming", "tbd") for m in rnd_matches)

        if any_live:
            rnd_status = "live"
        elif any_complete and not any_pending:
            rnd_status = "done"
        else:
            rnd_status = "upcoming"

        rounds.append({
            "round_number": rnd,
            "name":         round_name(rnd, num_rounds),
            "gameweek":     gw,
            "status":       rnd_status,
            "matches":      rnd_matches,
        })

    return render_template(
        "cup/bracket.html",
        season=season,
        config=config,
        rounds=rounds,
    )
