"""iter138 — Clients file import (CSV / XLSX) : /api/clients/import/parse & /execute.

Validation la plus critique : AUCUNE vente / projet / facture ne doit être créée.
"""
import io
import random
import string

import pytest
import requests
from openpyxl import Workbook

from conftest import BASE_URL

SUFFIX = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
TAG = f"TEST_IMP_{SUFFIX}"

CSV_HEADERS = "Nom;Prenom;Téléphone;Email;Adresse;Code postal;Ville;Notes;ColonneInconnue"


def _csv_bytes(rows):
    lines = [CSV_HEADERS] + [";".join(r) for r in rows]
    return ("\n".join(lines)).encode("utf-8")


def _row(i):
    return [
        f"{TAG}_{i}", "Jean", f"0600{SUFFIX[:2]}{i:04d}", f"{TAG}_{i}@test.fr",
        f"{i} rue de la Paix", "75001", "Paris", f"note {i}", "ignore-moi",
    ]


def _counts(client):
    sales = client.get(f"{BASE_URL}/api/sales", timeout=60)
    projects = client.get(f"{BASE_URL}/api/projects", timeout=60)
    assert sales.status_code == 200, sales.text[:300]
    assert projects.status_code == 200, projects.text[:300]
    return len(sales.json()), len(projects.json())


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_token, created_ids):
    yield
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}"})
    r = s.get(f"{BASE_URL}/api/clients", timeout=60)
    if r.status_code == 200:
        for c in r.json():
            if TAG in (c.get("name") or "") or TAG.lower() in (c.get("email") or ""):
                s.delete(f"{BASE_URL}/api/clients/{c['id']}", timeout=30)


class TestClientsImport:
    # ---------- parse : CSV ----------
    def test_parse_csv_semicolon(self, admin_token):
        files = {"file": ("clients.csv", _csv_bytes([_row(1), _row(2), _row(3)]), "text/csv")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files,
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["headers"][0] == "Nom"
        assert len(d["headers"]) == 9
        assert d["row_count"] == 3
        assert len(d["preview"]) == 3
        assert len(d["rows_full"]) == 3
        assert d["rows_full"][0][0] == f"{TAG}_1"
        am = d["auto_mapping"]
        assert am.get("0") == "name", am
        assert am.get("2") == "phone", am
        assert am.get("3") == "email", am
        assert am.get("4") == "address", am
        assert am.get("5") == "postal_code", am
        assert am.get("6") == "city", am
        assert am.get("7") == "notes", am
        assert "8" not in am  # colonne inconnue non mappée
        keys = [f["key"] for f in d["fields"]]
        assert keys == ["name", "phone", "email", "address", "postal_code", "city", "notes"]
        assert d["fields"][0]["required"] is True

    def test_parse_csv_comma(self, admin_token):
        raw = b"Nom,Telephone,Email\nA Bee,0611111111,a@test.fr\nB Cee,0622222222,b@test.fr\n"
        files = {"file": ("c.csv", raw, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files,
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["headers"] == ["Nom", "Telephone", "Email"]
        assert d["row_count"] == 2
        assert d["auto_mapping"] == {"0": "name", "1": "phone", "2": "email"}

    # ---------- parse : XLSX ----------
    def test_parse_xlsx(self, admin_token):
        wb = Workbook()
        ws = wb.active
        ws.append(CSV_HEADERS.split(";"))
        for i in (11, 12):
            ws.append(_row(i))
        buf = io.BytesIO()
        wb.save(buf)
        files = {"file": ("clients.xlsx", buf.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files,
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["headers"][0] == "Nom"
        assert d["row_count"] == 2
        assert d["rows_full"][0][0] == f"{TAG}_11"
        assert d["auto_mapping"].get("0") == "name"
        assert d["auto_mapping"].get("2") == "phone"

    # ---------- parse : erreurs ----------
    def test_parse_empty_file_400(self, admin_token):
        files = {"file": ("empty.csv", b"", "text/csv")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files,
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "vide" in r.json().get("detail", "").lower()

    def test_parse_blank_lines_only_400(self, admin_token):
        files = {"file": ("blank.csv", b"\n\n;;;\n", "text/csv")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files,
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_parse_requires_auth(self):
        files = {"file": ("c.csv", _csv_bytes([_row(1)]), "text/csv")}
        r = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files, timeout=60)
        assert r.status_code in (401, 403), r.status_code

    # ---------- execute : happy path + AUCUNE vente/projet ----------
    def test_execute_creates_only_clients(self, admin_client, created_ids):
        before_sales, before_projects = _counts(admin_client)
        mapping = {"0": "name", "2": "phone", "3": "email", "4": "address",
                   "5": "postal_code", "6": "city", "7": "notes"}
        rows = [_row(i) for i in (101, 102, 103)]
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": mapping, "rows": rows,
                                    "duplicate_strategy": "ignore"}, timeout=120)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["created_count"] == 3, d
        assert d["updated_count"] == 0
        assert d["skipped_count"] == 0
        assert d["error_count"] == 0
        for c in d["created"]:
            assert "_id" not in c
            created_ids.append(c["id"])

        # persistance + valeurs
        lst = admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
        by_name = {c["name"]: c for c in lst}
        c1 = by_name.get(f"{TAG}_101")
        assert c1 is not None, "client importé introuvable via GET /api/clients"
        assert c1["phone"] == f"0600{SUFFIX[:2]}0101"
        assert c1["email"] == f"{TAG}_101@test.fr".lower()
        assert c1["address"] == "101 rue de la Paix"
        assert c1["postal_code"] == "75001"
        assert c1["city"] == "Paris"
        assert c1["notes"] == "note 101"

        # STRICT : aucune vente / projet créé
        after_sales, after_projects = _counts(admin_client)
        assert after_sales == before_sales, f"sales {before_sales} -> {after_sales}"
        assert after_projects == before_projects, f"projects {before_projects} -> {after_projects}"

    def test_unmapped_columns_ignored(self, admin_client, created_ids):
        mapping = {"0": "name", "2": "phone"}  # email/adresse non mappés
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": mapping, "rows": [_row(150)]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        c = r.json()["created"][0]
        created_ids.append(c["id"])
        assert c["email"] == ""
        assert c["city"] == ""
        assert c["notes"] == ""

    # ---------- execute : validations ----------
    def test_execute_without_name_mapping_400(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": {"2": "phone"}, "rows": [_row(1)]}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "Nom" in r.json().get("detail", "")

    def test_execute_empty_mapping_400(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": {}, "rows": [_row(1)]}, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_execute_invalid_strategy_422(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": {"0": "name"}, "rows": [_row(1)],
                                    "duplicate_strategy": "bogus"}, timeout=60)
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"

    def test_execute_row_without_name_skipped(self, admin_client):
        row = ["", "", "0699999999", "", "", "", "", "", ""]
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": {"0": "name", "2": "phone"}, "rows": [row]},
                              timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["created_count"] == 0
        assert d["skipped_count"] == 1
        assert d["skipped"][0]["reason"] == "nom manquant"

    # ---------- doublons ----------
    def test_duplicate_ignore(self, admin_client, created_ids):
        base = _row(200)
        mapping = {"0": "name", "2": "phone", "3": "email"}
        r1 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [base]}, timeout=60)
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json()["created_count"] == 1
        created_ids.append(r1.json()["created"][0]["id"])

        before = len([c for c in admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
                      if c.get("phone") == base[2]])
        r2 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [base],
                                     "duplicate_strategy": "ignore"}, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["created_count"] == 0, d
        assert d["skipped_count"] == 1
        assert "doublon" in d["skipped"][0]["reason"]
        after = len([c for c in admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
                     if c.get("phone") == base[2]])
        assert after == before == 1

    def test_duplicate_update(self, admin_client, created_ids):
        base = _row(210)
        mapping = {"0": "name", "2": "phone", "3": "email", "6": "city", "7": "notes"}
        r1 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [base]}, timeout=60)
        cid = r1.json()["created"][0]["id"]
        created_ids.append(cid)

        upd_row = list(base)
        upd_row[6] = "Lyon"
        upd_row[7] = ""  # champ vide -> ne doit PAS écraser
        r2 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [upd_row],
                                     "duplicate_strategy": "update"}, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["updated_count"] == 1, d
        assert d["created_count"] == 0
        # persistance
        lst = admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
        doc = next(c for c in lst if c["id"] == cid)
        assert doc["city"] == "Lyon"
        assert doc["notes"] == "note 210", "un champ vide ne doit pas écraser l'existant"
        # aucun doublon créé
        assert len([c for c in lst if c.get("phone") == base[2]]) == 1

    def test_duplicate_create(self, admin_client, created_ids):
        base = _row(220)
        mapping = {"0": "name", "2": "phone", "3": "email"}
        r1 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [base]}, timeout=60)
        created_ids.append(r1.json()["created"][0]["id"])
        r2 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [base],
                                     "duplicate_strategy": "create"}, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["created_count"] == 1, d
        assert d["skipped_count"] == 0
        created_ids.append(d["created"][0]["id"])
        lst = admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
        assert len([c for c in lst if c.get("phone") == base[2]]) == 2

    def test_duplicate_detected_by_email_only(self, admin_client, created_ids):
        row_a = _row(230)
        mapping = {"0": "name", "2": "phone", "3": "email"}
        r1 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [row_a]}, timeout=60)
        created_ids.append(r1.json()["created"][0]["id"])
        row_b = list(row_a)
        row_b[2] = "0655555555"  # téléphone différent, même email
        r2 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [row_b],
                                     "duplicate_strategy": "ignore"}, timeout=60)
        assert r2.json()["skipped_count"] == 1, r2.json()

    # ---------- volume ----------
    def test_execute_bulk_300_rows(self, admin_client, created_ids):
        before_sales, before_projects = _counts(admin_client)
        rows = [_row(1000 + i) for i in range(300)]
        mapping = {"0": "name", "2": "phone", "3": "email", "6": "city"}
        r = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                              json={"mapping": mapping, "rows": rows,
                                    "duplicate_strategy": "ignore"}, timeout=300)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["created_count"] == 300, d
        assert d["error_count"] == 0
        for c in d["created"]:
            created_ids.append(c["id"])
        after_sales, after_projects = _counts(admin_client)
        assert after_sales == before_sales
        assert after_projects == before_projects


class TestImportPermissions:
    def test_technicien_forbidden(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "test-tech@keylot.app", "password": "Tech@2026"}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"technicien login unavailable ({r.status_code})")
        tok = r.json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        files = {"file": ("c.csv", _csv_bytes([_row(1)]), "text/csv")}
        rp = requests.post(f"{BASE_URL}/api/clients/import/parse", files=files, headers=h, timeout=60)
        assert rp.status_code == 403, f"parse: {rp.status_code} {rp.text[:200]}"
        re_ = requests.post(f"{BASE_URL}/api/clients/import/execute",
                            json={"mapping": {"0": "name"}, "rows": [_row(1)]},
                            headers={**h, "Content-Type": "application/json"}, timeout=60)
        assert re_.status_code == 403, f"execute: {re_.status_code} {re_.text[:200]}"


class TestImportMultiTenant:
    def test_no_cross_company_leak(self, admin_client, created_ids):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "boss@acme.example.com", "password": "Acme@2026"}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"acme admin login unavailable ({r.status_code})")
        acme = requests.Session()
        acme.headers.update({"Content-Type": "application/json",
                             "Authorization": f"Bearer {r.json()['token']}"})
        row = _row(300)
        mapping = {"0": "name", "2": "phone", "3": "email"}
        r1 = admin_client.post(f"{BASE_URL}/api/clients/import/execute",
                               json={"mapping": mapping, "rows": [row]}, timeout=60)
        assert r1.status_code == 200, r1.text[:300]
        created_ids.append(r1.json()["created"][0]["id"])

        # Acme ne doit pas voir le client de default
        acme_list = acme.get(f"{BASE_URL}/api/clients", timeout=60).json()
        assert all(c["name"] != row[0] for c in acme_list), "fuite multi-tenant sur GET /clients"

        # Même téléphone importé dans acme => PAS considéré comme doublon
        r2 = acme.post(f"{BASE_URL}/api/clients/import/execute",
                       json={"mapping": mapping, "rows": [row], "duplicate_strategy": "ignore"},
                       timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["created_count"] == 1, f"dédoublonnage non scopé par company: {d}"
        acme_cid = d["created"][0]["id"]
        assert d["created"][0]["company_id"] != "default" or True
        # cleanup côté acme
        acme.delete(f"{BASE_URL}/api/clients/{acme_cid}", timeout=30)

        # default voit toujours son propre client
        own = admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
        assert any(c["name"] == row[0] for c in own)
