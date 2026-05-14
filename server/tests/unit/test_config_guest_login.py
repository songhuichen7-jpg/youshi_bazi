from app.core.config import Settings


def test_guest_login_can_be_enabled_explicitly_in_prod():
    settings = Settings(
        env="prod",
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        encryption_kek="00" * 32,
        guest_login_enabled=True,
    )

    assert settings.guest_login_enabled is True


def test_session_cookie_secure_can_be_disabled_for_http_beta_server():
    settings = Settings(
        env="prod",
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        encryption_kek="00" * 32,
        session_cookie_secure=False,
    )

    assert settings.session_cookie_secure is False
