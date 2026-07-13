"""Blueprint registration."""
from __future__ import annotations


def register_blueprints(app) -> None:
    from app.api.analytics.routes import bp as analytics_bp
    from app.api.assignments.routes import bp as assignments_bp
    from app.api.audit_logs.routes import bp as audit_bp
    from app.api.auth.routes import bp as auth_bp
    from app.api.chat.routes import bp as chat_bp
    from app.api.conversations.routes import bp as conversations_bp
    from app.api.documents.routes import bp as documents_bp
    from app.api.knowledge_bases.routes import bp as kb_bp
    from app.api.profile.routes import bp as profile_bp
    from app.api.tenants.routes import bp as tenants_bp
    from app.api.users.routes import bp as users_bp
    from app.api.voice_settings.routes import bp as voice_bp

    for bp in (auth_bp, tenants_bp, users_bp, kb_bp, documents_bp, chat_bp,
               conversations_bp, analytics_bp, audit_bp, assignments_bp, profile_bp,
               voice_bp):
        app.register_blueprint(bp)
