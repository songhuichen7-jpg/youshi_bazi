"""Unit tests for app.core.config.Settings."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_settings_requires_database_url(monkeypatch):
    """Missing DATABASE_URL → ValidationError at construction time."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENCRYPTION_KEK", "00" * 32)
    # Clear cached settings module
    import sys
    sys.modules.pop("app.core.config", None)
    with pytest.raises(ValidationError):
        from app.core.config import Settings
        Settings()


def test_settings_requires_encryption_kek(monkeypatch):
    """Missing ENCRYPTION_KEK → ValidationError."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
    monkeypatch.delenv("ENCRYPTION_KEK", raising=False)
    import sys
    sys.modules.pop("app.core.config", None)
    with pytest.raises(ValidationError):
        from app.core.config import Settings
        Settings()


def test_settings_loads_valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
    monkeypatch.setenv("ENCRYPTION_KEK", "aa" * 32)
    monkeypatch.setenv("ENV", "test")
    import sys
    sys.modules.pop("app.core.config", None)
    from app.core.config import Settings
    s = Settings()
    assert s.env == "test"
    assert str(s.database_url).startswith("postgresql+asyncpg://")
    assert s.encryption_kek == "aa" * 32


def test_plan5_llm_config_defaults(monkeypatch):
    for k in ("LLM_API_KEY", "LLM_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
              "MIMO_API_KEY", "MIMO_BASE_URL", "LLM_MODEL", "LLM_FAST_MODEL",
              "LLM_FALLBACK_MODEL", "LLM_STREAM_FIRST_DELTA_MS", "LLM_THINKING",
              "BAZI_REPO_ROOT"):
        monkeypatch.delenv(k, raising=False)
    import importlib
    from app.core import config as cfg
    importlib.reload(cfg)
    s = cfg.Settings()
    assert s.llm_api_key == ""
    assert s.llm_base_url == "https://token-plan-sgp.xiaomimimo.com/v1"
    assert s.mimo_api_key == ""
    assert s.mimo_base_url == "https://token-plan-sgp.xiaomimimo.com/v1"
    assert s.llm_model == "mimo-v2.5-pro"
    assert s.llm_fast_model == "mimo-v2.5"
    assert s.llm_fallback_model == "mimo-v2.5"
    assert s.llm_thinking == "enabled"
    assert s.llm_stream_first_delta_ms == 0
    assert s.bazi_repo_root == ""


def test_plan5_llm_config_env_override(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.deepseek.test")
    monkeypatch.setenv("LLM_MODEL", "custom-pro")
    monkeypatch.setenv("LLM_STREAM_FIRST_DELTA_MS", "8000")
    monkeypatch.setenv("LLM_THINKING", "disabled")
    import importlib
    from app.core import config as cfg
    importlib.reload(cfg)
    s = cfg.Settings()
    assert s.llm_api_key == "sk-test"
    assert s.llm_base_url == "https://example.deepseek.test"
    assert s.llm_model == "custom-pro"
    assert s.llm_stream_first_delta_ms == 8000
    assert s.llm_thinking == "disabled"


def test_plan5_llm_config_legacy_mimo_env_still_supported(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setenv("MIMO_API_KEY", "legacy-key")
    monkeypatch.setenv("MIMO_BASE_URL", "https://legacy.example/v1")
    from app.core.config import Settings
    s = Settings()
    assert s.llm_api_key == "legacy-key"
    assert s.llm_base_url == "https://legacy.example/v1"
