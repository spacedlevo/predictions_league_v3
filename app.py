import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask, render_template
from dotenv import load_dotenv
from config import Config

_LOCAL_TZ = ZoneInfo("Europe/London")

load_dotenv(Path(__file__).resolve().parent / ".env")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config())

    def _parse_kickoff(value):
        """Parse a UTC kickoff string and return a timezone-aware datetime in Europe/London."""
        if not value:
            return None
        s = str(value).replace("Z", "").replace("T", " ").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt_utc = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                return dt_utc.astimezone(_LOCAL_TZ)
            except ValueError:
                continue
        return None

    @app.template_filter("format_kickoff")
    def format_kickoff(value):
        dt = _parse_kickoff(value)
        return dt.strftime("%a %d %b, %H:%M") if dt else str(value)

    @app.template_filter("format_kickoff_day")
    def format_kickoff_day(value):
        dt = _parse_kickoff(value)
        return dt.strftime("%a %d %b") if dt else ""

    @app.template_filter("format_kickoff_time")
    def format_kickoff_time(value):
        dt = _parse_kickoff(value)
        return dt.strftime("%H:%M") if dt else ""

    from routes.home import bp as home_bp
    from routes.player import bp as player_bp
    from routes.gameweek import bp as gameweek_bp
    from routes.fixture import bp as fixture_bp
    from routes.api import bp as api_bp
    from routes.cup import bp as cup_bp
    app.register_blueprint(home_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(gameweek_bp)
    app.register_blueprint(fixture_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(cup_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
