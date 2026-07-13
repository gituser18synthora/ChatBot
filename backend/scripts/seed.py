"""Idempotent seed script.

    python -m scripts.seed --super-admin
    python -m scripts.seed --sample-tenant

Creates the first Super Admin (credentials from env, never hardcoded) and,
optionally, a sample tenant + KB for local development.

Env used:
    SEED_SUPERADMIN_EMAIL, SEED_SUPERADMIN_PASSWORD, SEED_SUPERADMIN_NAME
"""
from __future__ import annotations

import argparse
import os
import sys

from app import create_app
from app.constants import KBStatus, Role, TenantStatus
from app.extensions import db
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.user import User
from app.utils.uuid_utils import new_uuid


def ensure_super_admin() -> None:
    email = os.getenv("SEED_SUPERADMIN_EMAIL")
    password = os.getenv("SEED_SUPERADMIN_PASSWORD")
    name = os.getenv("SEED_SUPERADMIN_NAME", "Super Admin")
    if not email or not password:
        print("ERROR: set SEED_SUPERADMIN_EMAIL and SEED_SUPERADMIN_PASSWORD in the environment.")
        sys.exit(1)

    existing = User.query.filter_by(email=email.lower()).first()
    if existing:
        print(f"Super Admin already exists: {email}")
        return
    user = User(id=new_uuid(), tenant_id=None, name=name, email=email.lower(),
                role=Role.SUPER_ADMIN, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created Super Admin: {email}")


def ensure_sample_tenant() -> None:
    tenant = Tenant.query.filter_by(tenant_code="sample").first()
    if not tenant:
        tenant = Tenant(id=new_uuid(), tenant_name="Sample Tenant", tenant_code="sample",
                        status=TenantStatus.ACTIVE, contact_name="Ops", contact_email="ops@example.com")
        db.session.add(tenant)
        db.session.flush()
        print(f"Created sample tenant: {tenant.id}")

    if not KnowledgeBase.query.filter_by(tenant_id=tenant.id).first():
        kb = KnowledgeBase(id=new_uuid(), tenant_id=tenant.id, kb_name="Product Manuals",
                           description="Sample knowledge base", status=KBStatus.PENDING,
                           status_message="Upload documents to start indexing this Knowledge Base.")
        db.session.add(kb)
        print(f"Created sample KB: {kb.id}")

    # A sample tenant admin (password from env, optional).
    admin_pw = os.getenv("SEED_TENANT_ADMIN_PASSWORD")
    if admin_pw and not User.query.filter_by(email="admin@sample.example").first():
        admin = User(id=new_uuid(), tenant_id=tenant.id, name="Sample Admin",
                     email="admin@sample.example", role=Role.TENANT_ADMIN, is_active=True)
        admin.set_password(admin_pw)
        db.session.add(admin)
        print("Created sample tenant admin: admin@sample.example")

    db.session.commit()


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
            ensure_super_admin()
        if args.sample_tenant:
            ensure_sample_tenant()
        if not any([args.super_admin, args.sample_tenant, args.create_all]):
            parser.print_help()


if __name__ == "__main__":
    main()
