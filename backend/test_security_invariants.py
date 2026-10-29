import ast
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).with_name("server.py")
SERVER_SOURCE = SERVER_PATH.read_text(encoding="utf-8")
ROOT = SERVER_PATH.parent.parent
API_SOURCE = (ROOT / "frontend/src/lib/api.js").read_text(encoding="utf-8")
OFFLINE_SOURCE = (ROOT / "frontend/src/lib/offline.js").read_text(encoding="utf-8")
AUTH_SOURCE = (ROOT / "frontend/src/contexts/AuthContext.jsx").read_text(encoding="utf-8")
CRON_SOURCE = (ROOT / ".emergent/cron/dispatch_webhook.sh").read_text(encoding="utf-8")


class SecurityInvariantTests(unittest.TestCase):
    def test_server_remains_valid_python(self):
        ast.parse(SERVER_SOURCE)

    def test_no_refresh_cookie_without_refresh_flow(self):
        self.assertNotIn('set_cookie("refresh_token"', SERVER_SOURCE)
        self.assertNotIn("def create_refresh_token", SERVER_SOURCE)

    def test_kiks_pending_action_is_consumed_atomically(self):
        self.assertIn("db.kiks_pending.find_one_and_delete", SERVER_SOURCE)
        self.assertNotIn('db.kiks_pending.delete_one({"id": pending_id})', SERVER_SOURCE)

    def test_startup_does_not_delete_orphan_projects(self):
        self.assertNotIn('db.projects.delete_many({"id": {"$in": orphans}})', SERVER_SOURCE)
        self.assertIn("aucune suppression automatique", SERVER_SOURCE)

    def test_reminder_recipient_queries_are_tenant_scoped(self):
        self.assertIn("_build_reminder_digest(target_date, company_id)", SERVER_SOURCE)
        self.assertIn('{"company_id": company_id, "role": {"$in": ["commercial", "admin"]}}', SERVER_SOURCE)
        self.assertIn('{"company_id": company_id, "type": "commercial"}', SERVER_SOURCE)

    def test_stripe_event_has_processing_lifecycle(self):
        for status in ('"status": "processing"', '"status": "failed"', '"status": "processed"'):
            self.assertIn(status, SERVER_SOURCE)

    def test_startup_never_promotes_an_existing_user_to_super_admin(self):
        self.assertNotIn('update_one({"email": email}, {"$set": {"role": "super_admin"}})', SERVER_SOURCE)

    def test_production_startup_migrations_fail_closed(self):
        self.assertIn('RUN_STARTUP_MIGRATIONS est interdit en production', SERVER_SOURCE)
        migration_source = Path(__file__).with_name("migrate.py").read_text(encoding="utf-8")
        self.assertIn('if not args.apply:', migration_source)
        self.assertIn('status": "running"', migration_source)

    def test_login_throttling_is_persistent_and_privacy_preserving(self):
        self.assertNotIn("_LOGIN_ATTEMPTS: dict", SERVER_SOURCE)
        self.assertIn("db.login_attempts.find_one_and_update", SERVER_SOURCE)
        self.assertIn("db.login_attempts.create_index", SERVER_SOURCE)
        self.assertIn("hashlib.sha256", SERVER_SOURCE)

    def test_event_and_stock_user_references_are_tenant_validated(self):
        self.assertIn('detail="Un ou plusieurs participants sont invalides"', SERVER_SOURCE)
        self.assertIn('detail="Détenteur invalide pour cette société"', SERVER_SOURCE)
        self.assertIn('detail="Source ou destination invalide pour cette société"', SERVER_SOURCE)
        self.assertGreaterEqual(
            SERVER_SOURCE.count('{"company_id": company_id_of(user), "id": {"$in":'),
            2,
        )

    def test_browser_auth_uses_httponly_cookie_not_local_storage(self):
        self.assertIn("withCredentials: true", API_SOURCE)
        self.assertNotIn("localStorage.setItem", AUTH_SOURCE)
        self.assertNotIn("qylot_offline_creds", AUTH_SOURCE)
        self.assertNotIn("rememberOffline", AUTH_SOURCE)
        self.assertNotIn("offlineLogin", AUTH_SOURCE)

    def test_offline_queue_avoids_ambiguous_post_and_delete_replays(self):
        self.assertIn('["put", "patch"]', API_SOURCE)
        self.assertIn("OFFLINE_UNSAFE_MUTATION", API_SOURCE)
        self.assertIn("setOfflineIdentity", OFFLINE_SOURCE)
        self.assertIn("clearOfflineData", OFFLINE_SOURCE)

    def test_project_and_sale_mutations_enforce_row_scope(self):
        self.assertIn("async def _ensure_project_scope", SERVER_SOURCE)
        self.assertGreaterEqual(SERVER_SOURCE.count("await _ensure_project_scope"), 8)
        delete_sale = SERVER_SOURCE.split("async def delete_sale", 1)[1].split("# ---------------- Projects", 1)[0]
        self.assertIn('perm_scope(user, "sales", "view") == "own"', delete_sale)
        self.assertIn("_own_sales_filter(user)", delete_sale)

    def test_photo_payloads_are_bounded_and_scheme_validated(self):
        self.assertIn("def _validated_photo_source", SERVER_SOURCE)
        self.assertIn("MAX_INLINE_IMAGE_BYTES", SERVER_SOURCE)
        self.assertIn("MAX_PHOTOS_PER_ENTITY", SERVER_SOURCE)
        self.assertIn("base64.b64decode(match.group(2), validate=True)", SERVER_SOURCE)
        self.assertIn('"png" if decoded.startswith', SERVER_SOURCE)
        self.assertIn("actual != declared", SERVER_SOURCE)

    def test_client_notes_and_external_geocoding_are_explicitly_scoped(self):
        self.assertGreaterEqual(SERVER_SOURCE.count("await _scoped_client_query(user, cid)"), 2)
        self.assertIn("ALLOW_EXTERNAL_GEOCODING", SERVER_SOURCE)
        self.assertIn('"external_geocoding_enabled": geocoding_enabled', SERVER_SOURCE)

    def test_cron_never_forwards_bearer_across_hosts(self):
        self.assertNotIn("--location-trusted", CRON_SOURCE)
        self.assertIn("--location --max-redirs", CRON_SOURCE)


if __name__ == "__main__":
    unittest.main()
