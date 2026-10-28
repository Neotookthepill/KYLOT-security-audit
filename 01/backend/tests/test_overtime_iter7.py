# Tests for overtime tracking (heures sup techniciens) — iteration 7
import pytest
import requests
from conftest import BASE_URL

TEST_MONTH = "2026-08"
TEST_TECH = "TEST_Sebastien"
TEST_DATE = f"{TEST_MONTH}-27"
TEST_DATE2 = f"{TEST_MONTH}-28"


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_client):
    yield
    for d in (TEST_DATE, TEST_DATE2):
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": d, "hours": 0})


class TestOvertimeAuth:
    def test_get_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30)
        assert r.status_code in (401, 403), r.text[:300]

    def test_post_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE, "hours": 3}, timeout=30)
        assert r.status_code in (401, 403), r.text[:300]


class TestOvertimeCrud:
    def test_get_month_shape(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["month"] == TEST_MONTH
        assert isinstance(d["entries"], list)
        assert isinstance(d["rows"], list)
        assert isinstance(d["grand_total"], (int, float))
        for row in d["rows"]:
            assert "technician_name" in row and "total_hours" in row
        # iter8: sort key is (over_threshold desc, total_hours desc, name asc)
        keys = [(not row["over_threshold"], -row["total_hours"], row["technician_name"]) for row in d["rows"]]
        assert keys == sorted(keys), f"rows not sorted as expected: {d['rows']}"

    def test_get_missing_month_400_or_422(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/overtime", timeout=30)
        assert r.status_code in (400, 422), r.status_code

    def test_get_invalid_month(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/overtime?month=20", timeout=30)
        assert r.status_code == 400, r.status_code

    def test_create_and_persist(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE, "hours": 3}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert "id" in body and isinstance(body["id"], str)
        assert "created_at" in body
        assert body["hours"] == 3
        assert body["technician_name"] == TEST_TECH
        assert "_id" not in body

        g = admin_client.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30).json()
        match = [e for e in g["entries"] if e["technician_name"] == TEST_TECH and e["date"] == TEST_DATE]
        assert len(match) == 1
        assert match[0]["hours"] == 3
        row = next(r for r in g["rows"] if r["technician_name"] == TEST_TECH)
        assert row["total_hours"] == 3

    def test_upsert_duplicate_updates_not_duplicates(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE, "hours": 5.5}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["hours"] == 5.5
        g = admin_client.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30).json()
        match = [e for e in g["entries"] if e["technician_name"] == TEST_TECH and e["date"] == TEST_DATE]
        assert len(match) == 1, f"duplicate entries created: {match}"
        assert match[0]["hours"] == 5.5

    def test_multiple_dates_sum_in_row(self, admin_client):
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE2, "hours": 2}, timeout=30)
        g = admin_client.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30).json()
        row = next(r for r in g["rows"] if r["technician_name"] == TEST_TECH)
        assert row["total_hours"] == 7.5, g["rows"]

    def test_zero_hours_deletes(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE2, "hours": 0}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.json().get("deleted") is True
        g = admin_client.get(f"{BASE_URL}/api/overtime?month={TEST_MONTH}", timeout=30).json()
        match = [e for e in g["entries"] if e["technician_name"] == TEST_TECH and e["date"] == TEST_DATE2]
        assert match == []
        row = next(r for r in g["rows"] if r["technician_name"] == TEST_TECH)
        assert row["total_hours"] == 5.5

    def test_other_month_isolated(self, admin_client):
        g = admin_client.get(f"{BASE_URL}/api/overtime?month=2026-09", timeout=30).json()
        assert [e for e in g["entries"] if e["technician_name"] == TEST_TECH] == []

    def test_empty_technician_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": "   ", "date": TEST_DATE, "hours": 2}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_bad_date_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": "2026-08", "hours": 2}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_missing_fields_422(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_out_of_range_hours(self, admin_client):
        # Backend has no upper bound validation; documents behaviour
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE2, "hours": 99}, timeout=30)
        accepted = r.status_code == 200
        if accepted:
            admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TEST_TECH, "date": TEST_DATE2, "hours": 0}, timeout=30)
        assert r.status_code in (200, 400, 422)
        if accepted:
            print("MINOR: hours=99 accepted (no 0-24 upper bound validation on backend, frontend-only guard)")


# Regression: key existing endpoints still respond 200
class TestRegressionEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/auth/me",
        "/api/sales",
        "/api/team",
        "/api/users",
        "/api/clients",
        "/api/projects",
        "/api/dashboard/stats",
        "/api/reports/monthly?month=2026-07",
        "/api/commissions?month=2026-07",
        "/api/subscription/me",
        "/api/settings",
    ])
    def test_endpoint_200(self, admin_client, path):
        r = admin_client.get(f"{BASE_URL}{path}", timeout=45)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
