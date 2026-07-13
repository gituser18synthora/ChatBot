"""Custom Flask CLI commands for database setup.

Registered in the app factory so they are available as:

    flask init-db                 # full bootstrap: create db -> migrate -> seed
    flask init-db --no-seed       # schema only
    flask init-db --sample-tenant # also create local-dev sample fixtures
    flask seed --super-admin      # (re)run the required Super Admin seed
    flask seed --sample-tenant    # local-dev fixtures only

These wrap app/db_init.py so the same idempotent logic backs the CLI, the
`python -m scripts.init_db` script, and the optional boot-time auto-upgrade.
"""
from __future__ import annotations

import sys

import click
from flask import Flask
from flask.cli import with_appcontext

from app import db_init


def register_commands(app: Flask) -> None:
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)


@click.command("init-db")
@click.option("--seed/--no-seed", "seed", default=True,
              help="Insert required default data after migrating (default: yes).")
@click.option("--sample-tenant", is_flag=True,
              help="Also create a local-dev sample tenant + knowledge base.")
def init_db_command(seed: bool, sample_tenant: bool) -> None:
    """Create the database if needed, run migrations, and seed default data."""
    from flask import current_app

    try:
        db_init.initialize_database(current_app._get_current_object(),
                                    seed=seed, sample_tenant=sample_tenant)
    except db_init.DatabaseInitError as exc:
        click.secho(f"\nDatabase initialization failed:\n{exc}", fg="red", err=True)
        sys.exit(1)
    click.secho("Database is ready.", fg="green")


@click.command("seed")
@click.option("--super-admin", "super_admin", is_flag=True,
              help="Create the Super Admin from SEED_SUPERADMIN_* env vars.")
@click.option("--sample-tenant", is_flag=True,
              help="Create a local-dev sample tenant + knowledge base.")
@with_appcontext
def seed_command(super_admin: bool, sample_tenant: bool) -> None:
    """Insert required/optional default data (idempotent)."""
    from flask import current_app

    if not (super_admin or sample_tenant):
        click.echo("Nothing to do. Pass --super-admin and/or --sample-tenant.")
        return
    app = current_app._get_current_object()
    if super_admin:
        db_init.seed_default_data(app, sample_tenant=False)
    if sample_tenant:
        db_init._seed_sample_tenant()
    click.secho("Seeding complete.", fg="green")
