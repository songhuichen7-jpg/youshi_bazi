"""Application settings loaded from environment.

Settings are instantiated at module import time — tests must set env vars
BEFORE importing any app module. See server/tests/conftest.py.
"""
from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "prod", "test"] = "dev"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # Postgres (asyncpg driver)
    database_url: PostgresDsn

    # 32 字节 KEK，以 64 hex 字符传入；load_kek() 校验并转 bytes
    encryption_kek: str

    # B 阶段邀请制开关；C 阶段设 false 开放注册
    require_invite: bool = True
    # Internal beta switch: lets production deployments expose the no-phone
    # guest entry without pretending the whole app is a dev environment.
    guest_login_enabled: bool = False
    # Override when a beta deployment is intentionally served over plain HTTP
    # (for example a direct Tencent CVM IP before a domain/HTTPS cutover).
    session_cookie_secure: bool | None = None

    # Plan 3+ 预留；Plan 2 不使用
    aliyun_sms_access_key: str | None = None
    aliyun_sms_secret: str | None = None
    aliyun_sms_template: str | None = None

    # Plan 5 LLM config. MiMo Token Plan uses the OpenAI-compatible API.
    llm_api_key: str = Field(
        "",
        validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY", "MIMO_API_KEY"),
    )
    llm_base_url: str = Field(
        "https://token-plan-sgp.xiaomimimo.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "DEEPSEEK_BASE_URL", "MIMO_BASE_URL"),
    )
    llm_model: str = "mimo-v2.5-pro"
    llm_fast_model: str = "mimo-v2.5"
    llm_fallback_model: str = "mimo-v2.5"
    llm_thinking: Literal["enabled", "disabled"] = "enabled"
    # Offline tagger 多 key 池(round-robin),仅在 retrieval2 索引重建时使用。
    # 同一物理 endpoint(MiMo Token Plan)下不同账号的 key,通过逗号分隔。
    # 主 key 已在 llm_api_key,此处只填额外的;留空 = 单 key 模式不变。
    # 例: LLM_API_KEYS_EXTRA=tp-xxx,tp-yyy
    llm_api_keys_extra: str = Field(
        "",
        validation_alias=AliasChoices("LLM_API_KEYS_EXTRA", "LLM_API_KEY_2"),
    )
    llm_stream_first_delta_ms: int = 0           # 0 = 禁用；B 阶段生产调 8000

    bazi_repo_root: str = ""                     # 空字符串 = 运行时推断

    # Share-card analytics + WeChat JS-SDK config.
    admin_token: str = ""
    wx_app_id: str = ""
    wx_app_secret: str = ""

    # TMDB — optional, used by /api/media/cover for movie posters.
    # No key configured → endpoint falls back to iTunes Movies entity only.
    tmdb_api_key: str = ""

    # Plan 5+ 计费。'manual' 是默认 — 用户在前端点"立即升级"会显示作者
    # 邮箱，作者通过 /api/admin/subscriptions/grant 人工开通。
    # 接入真实渠道时把这里改成 'wechat' / 'alipay'，并把对应的商户号、
    # API key、签名密钥填到下面的字段；同一进程里只能有一个活动 provider，
    # 想 A/B 多个渠道得各起一份服务（足够的隔离）。
    payment_provider: Literal["manual", "wechat", "alipay"] = "manual"

    # 微信支付商户号 + API v3 私钥 + 回调签名 platform-cert / API key v3.
    # 留空时 wechat provider 在初始化阶段直接抛 NotImplementedError。
    wechat_pay_mch_id: str = ""
    wechat_pay_api_v3_key: str = ""
    wechat_pay_private_key_path: str = ""        # PEM 路径
    wechat_pay_serial_no: str = ""
    wechat_pay_notify_url: str = ""              # 回调对外地址（含 https://）

    # 支付宝商户应用 ID + RSA 密钥 / 公钥（PEM 路径或字符串均可）。
    alipay_app_id: str = ""
    alipay_app_private_key: str = ""
    alipay_public_key: str = ""
    alipay_notify_url: str = ""

    # cron loop（lifespan task）每多少秒扫一次到期订阅；0 = 禁用，单元测试用。
    subscription_expire_loop_seconds: int = 3600

    # ── CORS（默认同源，跨域时显式列出）──────────────────────────────
    # 逗号分隔的 allowed origin 列表。空 = 不挂 CORSMiddleware（同源部署
    # 用，nginx 反代到前后端共用一个 origin 时不需要）。跨域部署时填
    # 完整 origin（含 scheme + host + port），eg.
    # CORS_ORIGINS="https://youshi.app,https://beta.youshi.app"
    cors_origins: str = ""

    # ── 全局 API rate-limit ──────────────────────────────────────────
    # 简单 in-memory 滑动窗口。key = user_id（已登录）/ remote IP（未登录）。
    # 仅作用于 /api/ 路径下的 mutating endpoint（POST/PUT/PATCH/DELETE）+
    # 流式 endpoint，GET 公共数据（cities/config/health）跳过。
    # 默认值是"温和但能挡住脚本循环压测"的水平，单 worker 内存够用；
    # 多 worker 没共享会让上限实际变成 N×limit，但 spam 还是被早期阻断。
    rate_limit_per_minute: int = 60
    # 0 = 完全不挂 middleware（test / 极端场景）
    rate_limit_enabled: bool = True

    # ── Redis（可选）──────────────────────────────────────────────────
    # 设了走 Redis 共享 rate-limit + 跨 worker 锁;不设走 in-memory,
    # 跟之前一致。生产多 worker 必须设;本地 dev / 单 worker prod 都
    # 可以留空。例: REDIS_URL=redis://localhost:6379/0
    redis_url: str = ""

    # ── DB 连接池 ─────────────────────────────────────────────────────
    # 默认 5 + 10 (单 worker dev 够);生产多 worker 推荐 20 + 30 (50 总
    # 连接 / worker)。每条 SSE 流持有一条连接到 stream 完成 — 想支持
    # N 个并发聊天 + M 个普通 API,池要 ≥ N+M。
    # PG 端 max_connections 默认 100,部署时算 (worker 数 × pool 总数)
    # 不要超过该值的 70%,留出 monitoring/migration 等连接。
    db_pool_size: int = 5
    db_max_overflow: int = 10

    @property
    def mimo_api_key(self) -> str:
        """Backward-compatible alias for older call sites and docs."""
        return self.llm_api_key

    @property
    def mimo_base_url(self) -> str:
        """Backward-compatible alias for older call sites and docs."""
        return self.llm_base_url

    @property
    def guest_login_available(self) -> bool:
        return self.guest_login_enabled or self.env in {"dev", "test"}

    @property
    def resolved_session_cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.env != "dev"


settings = Settings()
