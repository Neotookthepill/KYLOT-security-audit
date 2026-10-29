import os
import unittest


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_smoke_test",
    "JWT_SECRET": "smoke-test-secret-value-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "ADMIN_EMAIL": "admin@example.invalid",
    "ADMIN_PASSWORD": "smoke-test-admin-password",
})

from fastapi.testclient import TestClient

from backend.server import api_router, app


class ApplicationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Do not use the context-manager form: startup intentionally requires
        # a real MongoDB. These tests validate routing and middleware only.
        cls.client = TestClient(app)

    def test_health_and_security_headers(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertIn("max-age=31536000", response.headers.get("strict-transport-security", ""))
        self.assertEqual(
            response.headers.get("content-security-policy"),
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )

    def test_api_routes_exist_but_documentation_is_closed(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 404)
        paths = {route.path for route in api_router.routes}
        self.assertGreaterEqual(len(paths), 120)
        self.assertIn("/api/auth/login", paths)
        self.assertIn("/api/stripe/webhook", paths)

    def test_public_registration_is_closed_in_production(self):
        response = self.client.post("/api/auth/register", json={
            "email": "new-user@example.com",
            "name": "New User",
            "password": "a-long-test-password",
        })
        self.assertEqual(response.status_code, 403)

    def test_cors_only_allows_the_configured_frontend(self):
        allowed = self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://app.example.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "https://app.example.invalid")

        denied = self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://attacker.example.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotEqual(denied.headers.get("access-control-allow-origin"), "https://attacker.example.invalid")


if __name__ == "__main__":
    unittest.main()
