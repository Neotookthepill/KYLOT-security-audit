"""Iteration 6 — Inline status dropdown (PUT /api/sales/{id} status) + TAP source."""
import datetime

import pytest

from conftest import BASE_URL

CUR_MONTH = datetime.date.today().strftime("%Y-%m")
TODAY = datetime.date.today().isoformat()

SALE_STATUSES = ["en_cours", "commercial_cheque", "argent_recupere", "chantier_fini", "litige", "annule"]


@pytest.fixture(scope="module")
def created(admin_client):
    ids = {"sales": [], "clients": []}
    yield ids
    for sid in ids["sales"]:
        admin_client.delete(f"{BASE_URL}/api/sales/{sid}", timeout=30)
    for cid in ids["clients"]:
        admin_client.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)


@pytest.fixture(scope="module")
def tap_sale(admin_client, created):
    payload = {
        "client": {"name": "TEST_TAP_Client", "phone": "0600000000", "address": "1 rue Test",
                   "postal_code": "75001", "city": "Paris"},
        "service": "TEST_TAP Isolation",
        "amount": 2000,
        "payment_method": "cheque",
        "payment_installments": 1,
        "commission_rate": 0.10,
        "commercial": "Kilian",
        "source": "TAP",
        "sale_date": TODAY,
        "status": "en_cours",
        "commission_month": CUR_MONTH,
    }
    r = admin_client.post(f"{BASE_URL}/api/sales", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"create sale failed {r.status_code}: {r.text[:400]}"
    s = r.json()
    assert "_id" not in s
    assert s["source"] == "TAP"
    created["sales"].append(s["id"])
    if s.get("client_id"):
        created["clients"].append(s["client_id"])
    return s


# --- TAP source ---
class TestTapSource:
    def test_create_sale_with_tap_persists(self, admin_client, tap_sale):
        r = admin_client.get(f"{BASE_URL}/api/sales", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        found = [x for x in rows if x["id"] == tap_sale["id"]]
        assert found, "TAP sale not returned by GET /api/sales"
        assert found[0]["source"] == "TAP"
        assert found[0]["status"] == "en_cours"

    def test_sales_sorted_created_at_desc(self, admin_client, tap_sale):
        rows = admin_client.get(f"{BASE_URL}/api/sales", timeout=30).json()
        stamps = [r.get("created_at") for r in rows if r.get("created_at")]
        assert stamps == sorted(stamps, reverse=True), "sales not sorted by created_at DESC"
        # newly created sale must be near the top (parallel workers may add others)
        top_ids = [r["id"] for r in rows[:4]]
        assert tap_sale["id"] in top_ids, "newest sale not at top of the list"

    def test_monthly_report_includes_tap(self, admin_client, tap_sale):
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly", params={"month": CUR_MONTH}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "rows" in data and "totals" in data
        assert "TAP" in data["totals"]["sources"], f"TAP missing in totals.sources: {data['totals']['sources']}"
        assert data["totals"]["sources"]["TAP"] >= 1
        for row in data["rows"]:
            assert "TAP" in row["sources"], f"TAP missing in row sources: {row}"
        kilian = [x for x in data["rows"] if x.get("commercial") == "Kilian"]
        if kilian:
            assert kilian[0]["sources"]["TAP"] >= 1

    def test_monthly_pdf_generates(self, admin_client, tap_sale):
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly.pdf", params={"month": CUR_MONTH}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000


# --- Inline status change via PUT /api/sales/{id} ---
class TestStatusUpdate:
    @pytest.mark.parametrize("status", SALE_STATUSES)
    def test_put_each_status(self, admin_client, tap_sale, status):
        r = admin_client.put(f"{BASE_URL}/api/sales/{tap_sale['id']}", json={"status": status}, timeout=60)
        assert r.status_code == 200, f"{status} -> {r.status_code} {r.text[:300]}"
        # No GET /api/sales/{id} endpoint exists (405) -> verify persistence via list
        get = admin_client.get(f"{BASE_URL}/api/sales", timeout=30)
        assert get.status_code == 200
        matches = [x for x in get.json() if x["id"] == tap_sale["id"]]
        assert matches, "sale disappeared from list"
        body = matches[0]
        assert body["status"] == status
        # other fields untouched
        assert body["source"] == "TAP"
        assert body["amount"] == 2000

    def test_put_status_unknown_sale_404(self, admin_client):
        r = admin_client.put(f"{BASE_URL}/api/sales/does-not-exist-xyz", json={"status": "en_cours"}, timeout=30)
        assert r.status_code == 404, f"expected 404, got {r.status_code}"

    def test_put_status_requires_auth(self, api_client, tap_sale):
        r = api_client.put(f"{BASE_URL}/api/sales/{tap_sale['id']}", json={"status": "en_cours"}, timeout=30)
        assert r.status_code in (401, 403)


# --- AI action with TAP ---
class TestAiTap:
    def test_ai_create_sale_tap(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/ai/action",
                              json={"message": "Vente Kilian 2000€ 10% chez TestTAP TAP"}, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("intent") == "create_sale", f"unexpected intent: {d}"
        assert (d.get("data") or {}).get("source") == "TAP", f"source not TAP: {d}"
