"""baseline: create all 10 tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-17 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- users ----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("phone_hash", sa.LargeBinary, nullable=True, unique=True),
        sa.Column("phone_last4", sa.String(4), nullable=True),
        sa.Column("nickname", sa.String(40), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("role", sa.String(16), nullable=False, server_default=sa.text("'user'")),
        sa.Column("plan", sa.String(16), nullable=False, server_default=sa.text("'free'")),
        sa.Column("plan_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("used_invite_code_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wechat_openid", sa.String(64), nullable=True, unique=True),
        sa.Column("wechat_unionid", sa.String(64), nullable=True, unique=True),
        sa.Column("dek_ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("dek_key_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_users_status_enum"),
        sa.CheckConstraint("role IN ('user','admin')", name="ck_users_role_enum"),
        sa.CheckConstraint("plan IN ('free','pro')", name="ck_users_plan_enum"),
    )

    # ---- invite_codes ---------------------------------------------------
    op.create_table(
        "invite_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT",
                                name="fk_invite_codes_created_by_users"),
                  nullable=False),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("used_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Now that invite_codes exists, backfill FKs on users.
    op.create_foreign_key(
        "fk_users_invited_by_user_id_users",
        "users", "users",
        ["invited_by_user_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_used_invite_code_id_invite_codes",
        "users", "invite_codes",
        ["used_invite_code_id"], ["id"], ondelete="RESTRICT",
    )

    # ---- sessions -------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE",
                                name="fk_sessions_user_id_users"),
                  nullable=False),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("ip", postgresql.INET, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ---- sms_codes ------------------------------------------------------
    op.create_table(
        "sms_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("ip", postgresql.INET, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("purpose IN ('register','login','bind')",
                           name="ck_sms_codes_purpose_enum"),
    )
    op.create_index("ix_sms_phone_created", "sms_codes",
                    ["phone", sa.text("created_at DESC")])

    # ---- charts ---------------------------------------------------------
    op.create_table(
        "charts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT",
                                name="fk_charts_user_id_users"),
                  nullable=False),
        sa.Column("label", sa.LargeBinary, nullable=True),
        sa.Column("birth_input", sa.LargeBinary, nullable=False),
        sa.Column("paipan", sa.LargeBinary, nullable=False),
        sa.Column("engine_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_charts_user_created", "charts",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---- chart_cache ----------------------------------------------------
    op.create_table(
        "chart_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("chart_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("charts.id", ondelete="CASCADE",
                                name="fk_chart_cache_chart_id_charts"),
                  nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key", sa.String(40), nullable=False, server_default=sa.text("''")),
        sa.Column("content", sa.LargeBinary, nullable=True),
        sa.Column("model_used", sa.String(32), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("regen_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("kind IN ('verdicts','section','dayun_step','liunian')",
                           name="ck_chart_cache_kind_enum"),
        sa.UniqueConstraint("chart_id", "kind", "key", name="uq_chart_cache_slot"),
    )

    # ---- conversations --------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("chart_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("charts.id", ondelete="RESTRICT",
                                name="fk_conversations_chart_id_charts"),
                  nullable=False),
        sa.Column("label", sa.LargeBinary, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- messages -------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE",
                                name="fk_messages_conversation_id_conversations"),
                  nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=True),
        sa.Column("meta", sa.LargeBinary, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant','gua','cta')",
                           name="ck_messages_role_enum"),
    )
    op.create_index("ix_messages_conv_created", "messages",
                    ["conversation_id", sa.text("created_at ASC")])

    # ---- quota_usage ----------------------------------------------------
    op.create_table(
        "quota_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT",
                                name="fk_quota_usage_user_id_users"),
                  nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "kind IN ('chat_message','section_regen','verdicts_regen',"
            "'dayun_regen','liunian_regen','gua','sms_send')",
            name="ck_quota_usage_kind_enum",
        ),
        sa.UniqueConstraint("user_id", "period", "kind", name="uq_quota_usage_slot"),
    )

    # ---- llm_usage_logs -------------------------------------------------
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL",
                                name="fk_llm_usage_logs_user_id_users"),
                  nullable=True),
        sa.Column("chart_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("charts.id", ondelete="SET NULL",
                                name="fk_llm_usage_logs_chart_id_charts"),
                  nullable=True),
        sa.Column("endpoint", sa.String(32), nullable=False),
        sa.Column("model", sa.String(32), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("intent", sa.String(24), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_llm_usage_logs_user_created", "llm_usage_logs",
                    ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    # Reverse order; CASCADE FKs on messages / chart_cache handle themselves.
    op.drop_index("ix_llm_usage_logs_user_created", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")
    op.drop_table("quota_usage")
    op.drop_index("ix_messages_conv_created", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("chart_cache")
    op.drop_index("ix_charts_user_created", table_name="charts")
    op.drop_table("charts")
    op.drop_index("ix_sms_phone_created", table_name="sms_codes")
    op.drop_table("sms_codes")
    op.drop_table("sessions")
    # FKs on users → invite_codes must drop before invite_codes table.
    op.drop_constraint("fk_users_used_invite_code_id_invite_codes",
                       "users", type_="foreignkey")
    op.drop_constraint("fk_users_invited_by_user_id_users",
                       "users", type_="foreignkey")
    op.drop_table("invite_codes")
    op.drop_table("users")
