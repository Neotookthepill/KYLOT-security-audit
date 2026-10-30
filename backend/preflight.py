"""Fail-fast production configuration checks without importing the application."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}
_PLACEHOLDERS = ("replace", "changeme", "change-me", "placeholder", "example", "ci-only")


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _value(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def _is_mongodb_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"mongodb", "mongodb+srv"} and bool(parsed.hostname)


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDERS)


def _strong_secret(value: str, minimum: int) -> bool:
    return len(value) >= minimum and not _is_placeholder(value)


def _parse_bool(value: str) -> bool | None:
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return None


def validate_config(env: Mapping[str, str]) -> ValidationResult:
    """Validate deploy-time values. Messages only name variables, never their values."""

    errors: list[str] = []
    warnings: list[str] = []
    environment = (_value(env, "ENVIRONMENT") or _value(env, "APP_ENV") or "development").lower()
    production = environment in {"production", "prod"}

    for name in ("MONGO_URL", "DB_NAME", "JWT_SECRET", "FRONTEND_URL", "ADMIN_EMAIL", "ADMIN_PASSWORD"):
        if not _value(env, name):
            errors.append(f"{name} is required")

    jwt_secret = _value(env, "JWT_SECRET")
    if jwt_secret and not _strong_secret(jwt_secret, 32):
        errors.append("JWT_SECRET must be a non-placeholder secret of at least 32 characters")

    mongo_url = _value(env, "MONGO_URL")
    if mongo_url and not _is_mongodb_url(mongo_url):
        errors.append("MONGO_URL must use the mongodb or mongodb+srv scheme")

    db_name = _value(env, "DB_NAME")
    if db_name and not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", db_name):
        errors.append("DB_NAME contains unsupported characters")

    app_version = _value(env, "APP_VERSION")
    if production and (not app_version or _is_placeholder(app_version) or app_version == "local"):
        errors.append("APP_VERSION must identify the exact production build")

    frontend_url = _value(env, "FRONTEND_URL").rstrip("/")
    if production and frontend_url and not _is_https_url(frontend_url):
        errors.append("FRONTEND_URL must be an HTTPS origin in production")

    cors_origins = [item.strip().rstrip("/") for item in _value(env, "CORS_ORIGINS").split(",") if item.strip()]
    if production and not cors_origins:
        errors.append("CORS_ORIGINS must explicitly list the production frontend origin")
    if "*" in cors_origins:
        errors.append("CORS_ORIGINS must not contain a wildcard")
    if production and any(not _is_https_url(origin) for origin in cors_origins):
        errors.append("Every CORS_ORIGINS entry must be an HTTPS origin in production")
    if production and frontend_url and frontend_url not in cors_origins:
        errors.append("CORS_ORIGINS must include FRONTEND_URL")

    stripe_return_origins = [
        item.strip().rstrip("/")
        for item in _value(env, "STRIPE_RETURN_ORIGINS").split(",")
        if item.strip()
    ]
    if production and any(not _is_https_url(origin) for origin in stripe_return_origins):
        errors.append("Every STRIPE_RETURN_ORIGINS entry must be an HTTPS origin in production")

    registration = _parse_bool(_value(env, "ALLOW_PUBLIC_REGISTRATION"))
    if registration is None:
        errors.append("ALLOW_PUBLIC_REGISTRATION must be a boolean")
    elif production and registration:
        errors.append("ALLOW_PUBLIC_REGISTRATION must remain false for the single-user deployment")

    for name in ("ALLOW_DEMO_DATA", "ALLOW_TOKEN_RESPONSE", "RUN_STARTUP_MIGRATIONS", "EXPOSE_API_DOCS", "ALLOW_EXTERNAL_GEOCODING"):
        enabled = _parse_bool(_value(env, name))
        if enabled is None:
            errors.append(f"{name} must be a boolean")
        elif production and enabled and name != "ALLOW_EXTERNAL_GEOCODING":
            errors.append(f"{name} must be false in production")
        elif production and enabled and name == "ALLOW_EXTERNAL_GEOCODING":
            warnings.append("ALLOW_EXTERNAL_GEOCODING is enabled; client addresses will be sent to a third party")

    external_ai = _parse_bool(_value(env, "ALLOW_EXTERNAL_AI"))
    if external_ai is None:
        errors.append("ALLOW_EXTERNAL_AI must be a boolean")
    elif production and external_ai:
        warnings.append("ALLOW_EXTERNAL_AI is enabled; prompts and uploaded documents may be sent to an external AI provider")

    cookie_secure = _parse_bool(_value(env, "COOKIE_SECURE"))
    if cookie_secure is None:
        errors.append("COOKIE_SECURE must be a boolean")
    elif production and not cookie_secure:
        errors.append("COOKIE_SECURE must be true in production")

    cookie_samesite = (_value(env, "COOKIE_SAMESITE") or "lax").lower()
    if cookie_samesite not in {"lax", "strict", "none"}:
        errors.append("COOKIE_SAMESITE must be lax, strict or none")
    if cookie_samesite == "none" and cookie_secure is not True:
        errors.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
    if production and cookie_samesite == "none":
        errors.append("COOKIE_SAMESITE=none is forbidden until dedicated CSRF protection exists")

    trust_proxy = _parse_bool(_value(env, "TRUST_PROXY_HEADERS"))
    if trust_proxy is None:
        errors.append("TRUST_PROXY_HEADERS must be a boolean")

    admin_password = _value(env, "ADMIN_PASSWORD")
    if admin_password and not _strong_secret(admin_password, 16):
        errors.append("ADMIN_PASSWORD must be a non-placeholder secret of at least 16 characters")

    super_email = _value(env, "SUPER_ADMIN_EMAIL")
    super_password = _value(env, "SUPER_ADMIN_PASSWORD")
    if bool(super_email) != bool(super_password):
        errors.append("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD must be configured together")
    if super_password and not _strong_secret(super_password, 16):
        errors.append("SUPER_ADMIN_PASSWORD must be a non-placeholder secret of at least 16 characters")
    if admin_password and super_password and admin_password == super_password:
        errors.append("ADMIN_PASSWORD and SUPER_ADMIN_PASSWORD must be different")

    stripe_key = _value(env, "STRIPE_SECRET_KEY")
    stripe_webhook = _value(env, "STRIPE_WEBHOOK_SECRET")
    if bool(stripe_key) != bool(stripe_webhook):
        errors.append("STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be configured together")
    if production and stripe_key and frontend_url not in stripe_return_origins:
        errors.append("STRIPE_RETURN_ORIGINS must include FRONTEND_URL when Stripe is enabled")

    positive_limits = (
        "MAX_UPLOAD_BYTES",
        "MAX_UPLOAD_FILES",
        "MAX_PDF_PAGES",
        "MAX_REQUEST_BYTES",
        "MAX_INLINE_IMAGE_BYTES",
        "MAX_PHOTOS_PER_ENTITY",
        "MAX_IMPORT_ROWS",
        "MAX_IMPORT_COLUMNS",
        "MAX_IMPORT_CELL_CHARS",
        "IMPORT_BATCH_TTL_MINUTES",
        "AI_RATE_LIMIT_PER_MINUTE",
        "AI_DAILY_REQUEST_QUOTA",
    )
    for name in positive_limits:
        raw = _value(env, name)
        if raw:
            try:
                valid = int(raw) > 0
            except ValueError:
                valid = False
            if not valid:
                errors.append(f"{name} must be a positive integer")

    cron_secret = _value(env, "WEBHOOK_CRON_SECRET")
    if cron_secret and not _strong_secret(cron_secret, 24):
        errors.append("WEBHOOK_CRON_SECRET must be a non-placeholder secret of at least 24 characters")

    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for name in ("ADMIN_EMAIL", "SUPER_ADMIN_EMAIL"):
        email = _value(env, name)
        if email and not email_pattern.match(email):
            errors.append(f"{name} must be a valid email address")

    if production and external_ai and not _value(env, "EMERGENT_LLM_KEY"):
        warnings.append("EMERGENT_LLM_KEY is missing; AI features will fail")
    if production and not _value(env, "EMERGENT_EMAIL_KEY"):
        warnings.append("EMERGENT_EMAIL_KEY is missing; email delivery will be disabled")
    if production and not stripe_key:
        warnings.append("Stripe keys are missing; billing features will be disabled")
    if production and not cron_secret:
        warnings.append("WEBHOOK_CRON_SECRET is missing; protected cron callbacks will be unavailable")

    return ValidationResult(tuple(errors), tuple(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate KYLOT deployment configuration")
    parser.add_argument("--strict", action="store_true", help="Treat optional integration warnings as errors")
    args = parser.parse_args(argv)

    result = validate_config(os.environ)
    for message in result.errors:
        print(f"ERROR: {message}", file=sys.stderr)
    for message in result.warnings:
        print(f"WARNING: {message}", file=sys.stderr)

    if result.errors or (args.strict and result.warnings):
        print("Preflight failed; deployment must not continue.", file=sys.stderr)
        return 1

    print("Preflight passed; required deployment settings are coherent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
