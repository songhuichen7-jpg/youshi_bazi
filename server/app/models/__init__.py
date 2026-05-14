"""SQLAlchemy declarative Base + model re-exports for Alembic autodiscovery."""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# NOTE: naming convention keeps generated constraint names deterministic so
# Alembic autogenerate diffs stay stable.
_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


# Import all models so Base.metadata is populated when Alembic imports us.
from app.models.user import InviteCode, SmsCode, User, UserSession  # noqa: E402
from app.models.chart import Chart, ChartCache  # noqa: E402
from app.models.conversation import Conversation, ConversationSummary, Message  # noqa: E402
from app.models.quota import LlmUsageLog, QuotaUsage  # noqa: E402
from app.models.card_share import CardShare  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.hepan_invite import HepanInvite  # noqa: E402
from app.models.hepan_message import HepanMessage  # noqa: E402
from app.models.subscription import Payment, Subscription  # noqa: E402

__all__ = [
    "Base",
    "User", "InviteCode", "UserSession", "SmsCode",
    "Chart", "ChartCache",
    "Conversation", "Message", "ConversationSummary",
    "QuotaUsage", "LlmUsageLog",
    "CardShare", "Event",
    "HepanInvite", "HepanMessage",
    "Subscription", "Payment",
]
