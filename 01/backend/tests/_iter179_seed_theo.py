"""iter179 helper: temporarily move a 'Théo Fresh' commission to the current month so the
monthly-view accent-insensitive search can be exercised in the UI. Usage:
  python _iter179_seed_theo.py set
  python _iter179_seed_theo.py revert
"""
import json
import sys
from pathlib import Path

import requests

B = "http://127.0.0.1:8000/api"
STATE = Path("/tmp/iter179_theo_state.json")


def tok():
    return requests.post(f"{B}/auth/login", json={"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}, timeout=60).json()["token"]


h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json"}
rows = requests.get(f"{B}/commissions", headers=h, timeout=120).json()

if sys.argv[1] == "set":
    target = next(r for r in rows if "Théo" in (r.get("commercial") or "") and r.get("commission_amount"))
    STATE.write_text(json.dumps({"sale_id": target["sale_id"], "old": target.get("commission_month")}))
    r = requests.put(f"{B}/sales/{target['sale_id']}", json={"commission_month": "2026-09"}, headers=h, timeout=60)
    print("set ->", r.status_code, target["sale_id"], target.get("commission_month"), "=> 2026-09", target["commission_amount"])
else:
    st = json.loads(STATE.read_text())
    r = requests.put(f"{B}/sales/{st['sale_id']}", json={"commission_month": st["old"]}, headers=h, timeout=60)
    print("revert ->", r.status_code, st)
