"""
Cup competition logic: bracket resolution and match winner calculation.

All functions are pure (no DB calls) — they operate on dicts already fetched
by database.py query functions and passed in from the route.
"""

import math
from services.scoring import calc_points


def round_name(round_number, num_rounds):
    """Return the display name for a round (e.g. 'Final', 'Semi-Final')."""
    rounds_from_final = num_rounds - round_number
    if rounds_from_final == 0:
        return "Final"
    if rounds_from_final == 1:
        return "Semi-Final"
    if rounds_from_final == 2:
        return "Quarter-Final"
    players_in_round = 2 ** (rounds_from_final + 1)
    return f"Round of {players_in_round}"


def calc_match_stats(player_id, fixtures_for_player):
    """Calculate tiebreak stats for one player across their fixtures in a GW.

    fixtures_for_player: list of fixture rows from get_cup_gw_data,
        each with keys pred_home, pred_away, predicted_result,
        result, result_home, result_away.

    Returns dict with keys: points, correct_results, correct_scores, goals_variance.
    Only counts fixtures where a result is available.
    """
    points = 0
    correct_results = 0
    correct_scores = 0
    goals_variance = 0

    for row in fixtures_for_player:
        result = row.get("result")
        result_home = row.get("result_home")
        result_away = row.get("result_away")

        if result is None:
            continue  # result not yet available

        pred_home = row["pred_home"]
        pred_away = row["pred_away"]
        predicted_result = row["predicted_result"]

        pts = calc_points(predicted_result, pred_home, pred_away, result, result_home, result_away)
        if pts is not None:
            points += pts

        if predicted_result == result:
            correct_results += 1

        if pred_home == result_home and pred_away == result_away:
            correct_scores += 1

        # Goals variance: includes 9-9 (large variance punishes non-submission)
        goals_variance += abs(pred_home - result_home) + abs(pred_away - result_away)

    return {
        "points":          points,
        "correct_results": correct_results,
        "correct_scores":  correct_scores,
        "goals_variance":  goals_variance,
    }


def resolve_match_winner(match, p1_stats, p2_stats):
    """Determine winner using the tiebreak order.

    Tiebreak order (all within the match's gameweek):
      1. Most GW points
      2. Most correct results (H/D/A)
      3. Most correct exact scores
      4. Lowest total goals variance
      5. Lower seed number (set at bracket draw time)

    Returns the winning player_id, or None if truly undecidable
    (should not happen given rule 5).
    """
    def compare(key, higher_wins=True):
        v1 = p1_stats[key]
        v2 = p2_stats[key]
        if v1 == v2:
            return None
        if higher_wins:
            return match["player1_id"] if v1 > v2 else match["player2_id"]
        else:
            return match["player1_id"] if v1 < v2 else match["player2_id"]

    for key, higher_wins in [
        ("points",          True),
        ("correct_results", True),
        ("correct_scores",  True),
        ("goals_variance",  False),  # lower variance = better
    ]:
        winner = compare(key, higher_wins)
        if winner is not None:
            return winner

    # Final tiebreak: lower seed wins (seed 1 = best, so lower number = better)
    s1 = match.get("player1_seed") or 999
    s2 = match.get("player2_seed") or 999
    if s1 != s2:
        return match["player1_id"] if s1 < s2 else match["player2_id"]

    return None  # absolute tie — cannot happen in practice


def _gw_is_complete(player_fixtures_map, gw_data_for_gw):
    """Return True if every fixture in this GW has a result."""
    for fixtures in gw_data_for_gw.values():
        for row in fixtures:
            if row.get("result") is None:
                return False
    return bool(gw_data_for_gw)


def resolve_bracket(cup_matches, gw_data, finished_gameweeks):
    """Resolve all cup match winners and propagate players through the bracket.

    cup_matches: list of match dicts from get_cup_matches()
    gw_data: nested dict from get_cup_gw_data() → {gw: {player_id: [fixtures]}}
    finished_gameweeks: set of gameweek numbers where all fixtures are done

    Returns a list of enriched match dicts with extra keys:
        winner_id, player1_stats, player2_stats,
        status ('bye'|'complete'|'live'|'upcoming'|'tbd')
    """
    # Work on mutable copies indexed by match_id
    by_id = {m["match_id"]: dict(m) for m in cup_matches}

    max_round = max(m["round_number"] for m in cup_matches) if cup_matches else 0

    for rnd in range(1, max_round + 1):
        round_matches = sorted(
            [m for m in by_id.values() if m["round_number"] == rnd],
            key=lambda m: m["match_number"],
        )

        for match in round_matches:
            winner_id = None
            p1_stats = None
            p2_stats = None

            if match["is_bye"]:
                winner_id = match["player1_id"]
                status = "bye"

            elif match["player1_id"] and match["player2_id"]:
                gw = match["gameweek"]
                gw_players = gw_data.get(gw, {})
                p1_fixtures = gw_players.get(match["player1_id"], [])
                p2_fixtures = gw_players.get(match["player2_id"], [])

                if gw in finished_gameweeks:
                    p1_stats = calc_match_stats(match["player1_id"], p1_fixtures)
                    p2_stats = calc_match_stats(match["player2_id"], p2_fixtures)
                    winner_id = resolve_match_winner(match, p1_stats, p2_stats)
                    status = "complete"
                elif gw_players:
                    status = "live"
                else:
                    status = "upcoming"

            else:
                status = "tbd"

            match["winner_id"] = winner_id
            match["player1_stats"] = p1_stats
            match["player2_stats"] = p2_stats
            match["status"] = status

            # Propagate winner into next-round match
            if winner_id and match.get("next_match_id"):
                next_m = by_id.get(match["next_match_id"])
                if next_m:
                    slot = match["next_match_slot"]
                    winner_seed = (
                        match["player1_seed"]
                        if match["player1_id"] == winner_id
                        else match["player2_seed"]
                    )
                    # Retrieve name fields from the winning side
                    if match["player1_id"] == winner_id:
                        winner_name = match.get("player1_name")
                        winner_web_name = match.get("player1_web_name")
                    else:
                        winner_name = match.get("player2_name")
                        winner_web_name = match.get("player2_web_name")

                    if slot == 1:
                        next_m["player1_id"]       = winner_id
                        next_m["player1_seed"]      = winner_seed
                        next_m["player1_name"]      = winner_name
                        next_m["player1_web_name"]  = winner_web_name
                    else:
                        next_m["player2_id"]       = winner_id
                        next_m["player2_seed"]      = winner_seed
                        next_m["player2_name"]      = winner_name
                        next_m["player2_web_name"]  = winner_web_name

    return list(by_id.values())
