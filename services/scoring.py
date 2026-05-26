from datetime import datetime, timezone


def is_prediction_visible(kickoff_str, prediction_count, active_player_count):
    """Return True if a prediction should be shown to users.

    Visible when kickoff has passed OR every active player has submitted a real prediction.
    """
    s = str(kickoff_str).replace("Z", "").replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            kickoff = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    else:
        return True  # unparseable kickoff — show it
    if datetime.now(timezone.utc) >= kickoff:
        return True
    return active_player_count > 0 and prediction_count >= active_player_count


def calc_points(predicted_result, pred_home, pred_away, actual_result, actual_home, actual_away):
    """Return points earned for a prediction (0, 1, or 2), or None if no result yet."""
    if actual_result is None:
        return None
    pts = 0
    if predicted_result == actual_result:
        pts += 1
    if pred_home == actual_home and pred_away == actual_away:
        pts += 1
    return pts
