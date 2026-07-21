"""Import all models so SQLAlchemy/Alembic can discover them."""
from app.models.audit_log import AuditLog
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession, ChatSessionKnowledgeBase
from app.models.chat_source import ChatSource
from app.models.document import Document
from app.models.kb_assignment import KnowledgeBaseAssignment
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.usage_log import UsageLog
from app.models.user import User
from app.models.user_kb_assignment import UserKnowledgeBaseAssignment
from app.models.user_token import UserToken
from app.models.voice_setting import VoiceSetting

__all__ = [
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "ChatSessionKnowledgeBase",
    "ChatSource",
    "Document",
    "KnowledgeBase",
    "KnowledgeBaseAssignment",
    "Tenant",
    "UsageLog",
    "User",
    "UserKnowledgeBaseAssignment",
    "UserToken",
    "VoiceSetting",
]
