"""One-command database initialization for a fresh checkout.

    python -m scripts.init_db                  # create db -> migrate -> seed
    python -m scripts.init_db --no-seed        # schema only
    python -m scripts.init_db --sample-tenant  # also add local-dev fixtures

Equivalent to `flask init-db`; provided so a new developer can initialize the
complete database right after cloning without needing FLASK_APP set. Idempotent
and safe to run multiple times. Exits non-zero with a clear message on failure.
"""
from __future__ import annotations

import argparse
import logging
import sys

from app import create_app, db_init


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the chatbot database.")
    parser.add_argument("--no-seed", dest="seed", action="store_false",
                        help="Skip inserting default seed data.")
    parser.add_argument("--sample-tenant", action="store_true",
                        help="Also create a local-dev sample tenant + knowledge base.")
    parser.set_defaults(seed=True)
    args = parser.parse_args()

    app = create_app()
    try:
        db_init.initialize_database(app, seed=args.seed, sample_tenant=args.sample_tenant)
    except db_init.DatabaseInitError as exc:
        logging.getLogger("scripts.init_db").error("Database initialization failed: %s", exc)
        print(f"\nDatabase initialization failed:\n{exc}", file=sys.stderr)
        sys.exit(1)
    print("Database is ready.")


if __name__ == "__main__":
    main()
