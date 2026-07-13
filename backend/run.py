"""Development entrypoint + CLI.

    flask --app run.py run           # dev server
    flask --app run.py db upgrade    # migrations (Flask-Migrate)
    python run.py                    # also starts the dev server
"""
from __future__ import annotations

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
