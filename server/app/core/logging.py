"""structlog setup with PII-whitelist scrubber.

Only keys in ``_LOG_WHITELIST`` make it to log output; everything else is
dropped at the processor stage. This is a defense-in-depth layer; callers
should still avoid passing PII into log calls.
"""
from __future__ import annotations

import logging

import structlog


# NOTE: see spec §4.3 — whitelist must match audit requirements.
_LOG_WHITELIST: frozenset[str] = frozenset({
    "event", "level", "timestamp", "request_id",
    "user_id", "chart_id", "conversation_id",
    "endpoint", "method", "status", "duration_ms",
    "model", "tokens_used", "error_code",
})


def _pii_scrub_processor(logger, method_name, event_dict):
    """Drop any key not in the whitelist."""
    return {k: v for k, v in event_dict.items() if k in _LOG_WHITELIST}


def setup_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _pii_scrub_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
