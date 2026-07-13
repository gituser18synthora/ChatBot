"""Idempotent seed script (thin CLI over app.db_init).

    python -m scripts.seed --super-admin
    python -m scripts.seed --sample-tenant
    python -m scripts.seed --create-all      # dev-only shortcut, prefer migrations

Creates the first Super Admin (credentials from env, never hardcoded) and,
optionally, a sample tenant + KB for local development. The actual seeding logic
lives in app/db_init.py so the CLI, `flask seed`, and `flask init-db` all share
one idempotent implementation.

Env used:
    SEED_SUPERADMIN_EMAIL, SEED_SUPERADMIN_PASSWORD, SEED_SUPERADMIN_NAME
    SEED_TENANT_ADMIN_PASSWORD (optional, for the sample tenant admin)
"""
from __future__ import annotations

import argparse

from app import create_app, db_init
from app.extensions import db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--super-admin", action="store_true")
    parser.add_argument("--sample-tenant", action="store_true")
    parser.add_argument("--create-all", action="store_true",
                        help="Create tables directly (dev only; prefer `flask db upgrade`).")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.create_all:
            db.create_all()
            print("Tables created.")
        if args.super_admin:
            db_init.seed_default_data(app, sample_tenant=False)
        if args.sample_tenant:
            db_init._seed_sample_tenant()
        if not any([args.super_admin, args.sample_tenant, args.create_all]):
            parser.print_help()


if __name__ == "__main__":
    main()
