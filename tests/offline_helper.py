# Helper for offline-mode testing: API ops outside the browser
import os, sys, json, requests
BASE = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0].rstrip('/') + '/api'
def tok():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"})
    return r.json()["token"]
H = {"Authorization": f"Bearer {tok()}"}
CID = "68b69fa6-b17a-4eee-935b-f002a5af8bb3"
cmd = sys.argv[1]
if cmd == "sales":
    s = [x for x in requests.get(f"{BASE}/sales", headers=H).json() if x.get("client_id") == CID]
    print(json.dumps([{k: x.get(k) for k in ("id", "bdc", "amount", "notes", "service", "created_at")} for x in s], indent=1))
elif cmd == "notes":
    print(json.dumps(requests.get(f"{BASE}/clients/{CID}/notes", headers=H).json(), indent=1)[:2000])
elif cmd == "setnotes":
    sid, val = sys.argv[2], sys.argv[3]
    s = next(x for x in requests.get(f"{BASE}/sales", headers=H).json() if x["id"] == sid)
    body = {k: s.get(k) for k in ("bdc", "service", "amount", "payment_method", "status", "commercial", "source", "sale_date")}
    body["notes"] = val
    if len(sys.argv) > 4: body["amount"] = float(sys.argv[4])
    r = requests.put(f"{BASE}/sales/{sid}", headers=H, json=body)
    print(r.status_code, r.text[:300])
elif cmd == "delsale":
    print(requests.delete(f"{BASE}/sales/{sys.argv[2]}", headers=H).status_code)
elif cmd == "delnote":
    print(requests.delete(f"{BASE}/client-notes/{sys.argv[2]}", headers=H).status_code)
elif cmd == "client":
    print(json.dumps(next(x for x in requests.get(f"{BASE}/clients", headers=H).json() if x["id"] == CID), indent=1)[:800])
