"""Fail-closed guard for historical scripts that mutate test data.

Loopback targets are allowed for local development. Any remote HTTP or MongoDB
target requires an exact allowlist plus an explicit acknowledgement. This keeps
old QA helpers from being pointed at staging or production by accident.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


ACK_VALUE = "I_UNDERSTAND_THIS_MUTATES_DATA"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _require_acknowledgement() -> None:
    if os.environ.get("KYLOT_ALLOW_REMOTE_TEST_MUTATIONS") != ACK_VALUE:
        raise RuntimeError(
            "Remote test mutations are blocked. Set "
            f"KYLOT_ALLOW_REMOTE_TEST_MUTATIONS={ACK_VALUE} only for an "
            "approved disposable environment."
        )


def require_http_mutation_permission(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("Invalid remote test URL")
    if parsed.hostname in LOOPBACK_HOSTS:
        return

    _require_acknowledgement()
    allowed = (os.environ.get("KYLOT_REMOTE_TEST_ALLOWED_ORIGIN") or "").rstrip("/")
    actual = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if not allowed or actual != allowed:
        raise RuntimeError(
            "Remote test target does not exactly match "
            "KYLOT_REMOTE_TEST_ALLOWED_ORIGIN"
        )


def require_mongo_mutation_permission(mongo_url: str) -> None:
    parsed = urlparse(mongo_url)
    if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.hostname:
        raise RuntimeError("Invalid MongoDB test URL")
    if parsed.hostname in LOOPBACK_HOSTS:
        return

    _require_acknowledgement()
    allowed_host = (os.environ.get("KYLOT_REMOTE_TEST_ALLOWED_MONGO_HOST") or "").strip()
    if not allowed_host or parsed.hostname != allowed_host:
        raise RuntimeError(
            "Remote MongoDB target does not exactly match "
            "KYLOT_REMOTE_TEST_ALLOWED_MONGO_HOST"
        )
