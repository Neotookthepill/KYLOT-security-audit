import unittest

from backend.preflight import validate_config


def valid_production_env():
    return {
        "ENVIRONMENT": "production",
        "APP_VERSION": "0123456789abcdef",
        "MONGO_URL": "mongodb://database.internal:27017",
        "DB_NAME": "kylot",
        "JWT_SECRET": "a-random-runtime-secret-longer-than-32-characters",
        "FRONTEND_URL": "https://app.example.invalid",
        "CORS_ORIGINS": "https://app.example.invalid",
        "ALLOW_PUBLIC_REGISTRATION": "false",
        "ALLOW_DEMO_DATA": "false",
        "ALLOW_TOKEN_RESPONSE": "false",
        "RUN_STARTUP_MIGRATIONS": "false",
        "EXPOSE_API_DOCS": "false",
        "ALLOW_EXTERNAL_GEOCODING": "false",
        "COOKIE_SECURE": "true",
        "COOKIE_SAMESITE": "lax",
        "TRUST_PROXY_HEADERS": "false",
        "ADMIN_EMAIL": "admin@example.invalid",
        "ADMIN_PASSWORD": "a-strong-admin-password",
        "SUPER_ADMIN_EMAIL": "owner@example.invalid",
        "SUPER_ADMIN_PASSWORD": "a-different-owner-password",
        "EMERGENT_LLM_KEY": "configured",
        "EMERGENT_EMAIL_KEY": "configured",
        "STRIPE_SECRET_KEY": "configured",
        "STRIPE_WEBHOOK_SECRET": "configured",
        "STRIPE_RETURN_ORIGINS": "https://app.example.invalid",
        "WEBHOOK_CRON_SECRET": "a-random-cron-secret-value",
    }


class PreflightTests(unittest.TestCase):
    def test_valid_production_configuration_passes(self):
        result = validate_config(valid_production_env())
        self.assertEqual(result.errors, ())
        self.assertEqual(result.warnings, ())

    def test_rejects_public_registration_and_insecure_cookie(self):
        env = valid_production_env()
        env["ALLOW_PUBLIC_REGISTRATION"] = "true"
        env["COOKIE_SECURE"] = "false"
        result = validate_config(env)
        self.assertTrue(any("ALLOW_PUBLIC_REGISTRATION" in error for error in result.errors))
        self.assertTrue(any("COOKIE_SECURE" in error for error in result.errors))

    def test_rejects_demo_data_and_token_response_in_production(self):
        env = valid_production_env()
        env["ALLOW_DEMO_DATA"] = "true"
        env["ALLOW_TOKEN_RESPONSE"] = "true"
        result = validate_config(env)
        self.assertTrue(any("ALLOW_DEMO_DATA" in error for error in result.errors))
        self.assertTrue(any("ALLOW_TOKEN_RESPONSE" in error for error in result.errors))

    def test_rejects_automatic_data_migrations_in_production(self):
        env = valid_production_env()
        env["RUN_STARTUP_MIGRATIONS"] = "true"
        result = validate_config(env)
        self.assertTrue(any("RUN_STARTUP_MIGRATIONS" in error for error in result.errors))

    def test_rejects_public_api_documentation_in_production(self):
        env = valid_production_env()
        env["EXPOSE_API_DOCS"] = "true"
        result = validate_config(env)
        self.assertTrue(any("EXPOSE_API_DOCS" in error for error in result.errors))

    def test_rejects_invalid_external_geocoding_flag(self):
        env = valid_production_env()
        env["ALLOW_EXTERNAL_GEOCODING"] = "sometimes"
        result = validate_config(env)
        self.assertTrue(any("ALLOW_EXTERNAL_GEOCODING" in error for error in result.errors))

    def test_rejects_cross_site_cookie_without_csrf_protection(self):
        env = valid_production_env()
        env["COOKIE_SAMESITE"] = "none"
        result = validate_config(env)
        self.assertTrue(any("CSRF" in error for error in result.errors))

    def test_rejects_wildcard_cors_and_plain_http(self):
        env = valid_production_env()
        env["FRONTEND_URL"] = "http://app.example.invalid"
        env["CORS_ORIGINS"] = "*"
        result = validate_config(env)
        self.assertTrue(any("FRONTEND_URL" in error for error in result.errors))
        self.assertTrue(any("wildcard" in error for error in result.errors))

    def test_rejects_unknown_build_invalid_mongo_and_database_name(self):
        env = valid_production_env()
        env["APP_VERSION"] = "local"
        env["MONGO_URL"] = "https://database.example.invalid"
        env["DB_NAME"] = "kylot unsafe"
        result = validate_config(env)
        self.assertTrue(any("APP_VERSION" in error for error in result.errors))
        self.assertTrue(any("MONGO_URL" in error for error in result.errors))
        self.assertTrue(any("DB_NAME" in error for error in result.errors))

    def test_rejects_invalid_proxy_flag_limits_and_stripe_return_origin(self):
        env = valid_production_env()
        env["TRUST_PROXY_HEADERS"] = "perhaps"
        env["MAX_UPLOAD_FILES"] = "0"
        env["STRIPE_RETURN_ORIGINS"] = "https://another.example.invalid"
        result = validate_config(env)
        self.assertTrue(any("TRUST_PROXY_HEADERS" in error for error in result.errors))
        self.assertTrue(any("MAX_UPLOAD_FILES" in error for error in result.errors))
        self.assertTrue(any("STRIPE_RETURN_ORIGINS" in error for error in result.errors))

    def test_rejects_placeholder_secrets(self):
        env = valid_production_env()
        env["JWT_SECRET"] = "replace-with-at-least-32-random-bytes"
        env["ADMIN_PASSWORD"] = "change-me-please-now"
        result = validate_config(env)
        self.assertTrue(any("JWT_SECRET" in error for error in result.errors))
        self.assertTrue(any("ADMIN_PASSWORD" in error for error in result.errors))

    def test_warns_when_optional_integrations_are_absent(self):
        env = valid_production_env()
        for name in (
            "EMERGENT_LLM_KEY",
            "EMERGENT_EMAIL_KEY",
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "WEBHOOK_CRON_SECRET",
        ):
            env.pop(name)
        result = validate_config(env)
        self.assertEqual(result.errors, ())
        # AI is fail-closed by default, so a missing AI key is not a deployment
        # warning until the external integration is explicitly enabled.
        self.assertEqual(len(result.warnings), 3)

    def test_warns_when_external_ai_is_enabled_or_missing_its_key(self):
        env = valid_production_env()
        env["ALLOW_EXTERNAL_AI"] = "true"
        env.pop("EMERGENT_LLM_KEY")
        result = validate_config(env)
        self.assertEqual(result.errors, ())
        self.assertTrue(any("ALLOW_EXTERNAL_AI" in warning for warning in result.warnings))
        self.assertTrue(any("EMERGENT_LLM_KEY" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
