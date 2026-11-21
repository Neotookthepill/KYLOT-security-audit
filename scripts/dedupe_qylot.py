#!/usr/bin/env python3
"""Détection et fusion contrôlée des doublons Qylot.

Modes :
  python scripts/dedupe_qylot.py report
  python scripts/dedupe_qylot.py apply --approvals backups/dedupe-.../approvals.csv

Le mode report ne modifie rien. Le mode apply exige :
  - CONFIRM=DEDUPE
  - un fichier approvals.csv où les lignes à appliquer ont approve=yes
  - une sauvegarde mongodump réussie avant toute écriture
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]


def load_env(name: str) -> None:
    p = ROOT / ".secrets" / name
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env("qa-mongo.env")
load_env("qa.env")


def norm(value: Any) -> str:
    text = " ".join(str(value or "").replace("\u00a0", " ").split())
    return " ".join(
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore").decode().lower().split()
    )


def phone_key(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) >= 9 else ""


def stable_id(prefix: str, key: str) -> str:
    return prefix + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8].upper()


def mongo():
    uri = os.environ.get("QA_MONGO_URI") or os.environ.get("MONGO_URL")
    dbname = os.environ.get("QA_DB_NAME") or os.environ.get("DB_NAME")
    if not uri or not dbname:
        raise SystemExit("QA_MONGO_URI / QA_DB_NAME manquants (ou MONGO_URL / DB_NAME).")
    return MongoClient(uri, serverSelectionTimeoutMS=15000)[dbname]


def counts_for(db, client_id: str) -> tuple[int, int, int]:
    sales = db.sales.count_documents({"client_id": client_id})
    projects = db.projects.count_documents({"client_id": client_id})
    notes = db.client_notes.count_documents({"client_id": client_id})
    return sales, projects, notes


def client_groups(db) -> list[dict]:
    rows = list(db.clients.find({}, {
        "_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1,
        "address": 1, "postal_code": 1, "city": 1, "company_id": 1, "created_at": 1,
    }))
    by = defaultdict(list)
    for row in rows:
        key = (row.get("company_id") or "default", norm(row.get("name")))
        if key[1]:
            by[key].append(row)

    out = []
    for (company, name_key), members in by.items():
        if len(members) < 2:
            continue
        # Un groupe homonyme n'est "fort" que si le téléphone ou le code postal concorde.
        phones = {phone_key(m.get("phone")) for m in members if phone_key(m.get("phone"))}
        postals = {str(m.get("postal_code") or "").strip() for m in members if str(m.get("postal_code") or "").strip()}
        confidence = "high" if len(phones) == 1 and phones else ("medium" if len(postals) == 1 and postals else "low")
        enriched = []
        for m in members:
            s, p, n = counts_for(db, m["id"])
            enriched.append({**m, "sales": s, "projects": p, "notes": n})
        # Une fiche sans téléphone est incomplète : on garde d'abord celle qui
        # possède un numéro, puis celle qui a le plus de liens métier.
        keep = max(
            enriched,
            key=lambda m: (
                1 if phone_key(m.get("phone")) else 0,
                1 if m.get("sales") or m.get("projects") or m.get("notes") else 0,
                1 if m.get("email") else 0,
                1 if m.get("address") else 0,
                m["sales"] + m["projects"] + m["notes"],
                str(m.get("created_at") or ""),
            ),
        )
        out.append({
            "group_id": stable_id("C", f"{company}|{name_key}"),
            "type": "client",
            "confidence": confidence,
            "company_id": company,
            "normalized_name": name_key,
            "keep_id": keep["id"],
            "member_ids": [m["id"] for m in enriched],
            "names": [m.get("name") or "" for m in enriched],
            "phones": [m.get("phone") or "" for m in enriched],
            "postal_codes": [m.get("postal_code") or "" for m in enriched],
            "sales_per_member": [m["sales"] for m in enriched],
            "projects_per_member": [m["projects"] for m in enriched],
            "notes_per_member": [m["notes"] for m in enriched],
            "approve": "",
        })
    return sorted(out, key=lambda g: (g["confidence"] != "high", g["normalized_name"]))


def project_groups(db) -> list[dict]:
    rows = list(db.projects.find({}, {
        "_id": 0, "id": 1, "sale_id": 1, "client_id": 1, "status": 1,
        "scheduled_date": 1, "created_at": 1, "assigned_to": 1, "company_id": 1,
    }))
    by = defaultdict(list)
    for row in rows:
        if row.get("sale_id"):
            by[(row.get("company_id") or "default", row["sale_id"])].append(row)
    out = []
    for (company, sale_id), members in by.items():
        if len(members) < 2:
            continue
        # Priorité au chantier déjà terminé, sinon au plus ancien.
        priority = {"termine": 0, "encaisse": 0, "en_cours": 1, "a_planifier": 2}
        keep = min(members, key=lambda m: (priority.get(m.get("status"), 3), str(m.get("created_at") or "")))
        out.append({
            "group_id": stable_id("P", f"{company}|{sale_id}"),
            "type": "project",
            "confidence": "medium",
            "company_id": company,
            "sale_id": sale_id,
            "keep_id": keep["id"],
            "member_ids": [m["id"] for m in members],
            "statuses": [m.get("status") or "" for m in members],
            "scheduled_dates": [m.get("scheduled_date") or "" for m in members],
            "approve": "",
        })
    return sorted(out, key=lambda g: g["group_id"])


def sales_bdc_groups(db) -> list[dict]:
    rows = list(db.sales.find({}, {"_id": 0, "id": 1, "bdc": 1, "client_id": 1, "amount": 1, "sale_date": 1, "status": 1, "company_id": 1}))
    by = defaultdict(list)
    for row in rows:
        key = (row.get("company_id") or "default", norm(row.get("bdc")))
        if key[1]:
            by[key].append(row)
    out = []
    for (company, bdc), members in by.items():
        if len(members) < 2:
            continue
        out.append({
            "group_id": stable_id("S", f"{company}|{bdc}"),
            "type": "sale_bdc",
            "confidence": "low",
            "company_id": company,
            "normalized_name": bdc,
            "keep_id": members[0]["id"],
            "member_ids": [m["id"] for m in members],
            "amounts": [m.get("amount") for m in members],
            "sale_dates": [m.get("sale_date") or "" for m in members],
            "statuses": [m.get("status") or "" for m in members],
            "approve": "",
        })
    return sorted(out, key=lambda g: g["group_id"])


def user_groups(db) -> list[dict]:
    rows = list(db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "company_id": 1}))
    out = []
    for row in rows:
        name = str(row.get("name") or "")
        if name != name.strip():
            out.append({
                "group_id": stable_id("U", row["id"]),
                "type": "user_name",
                "confidence": "high",
                "company_id": row.get("company_id") or "default",
                "keep_id": row["id"],
                "member_ids": [row["id"]],
                "names": [name],
                "new_name": name.strip(),
                "approve": "",
            })
    return sorted(out, key=lambda g: g["group_id"])


def write_report(db, groups: list[dict]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = ROOT / "backups" / f"dedupe-report-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    fields = ["group_id", "type", "confidence", "company_id", "normalized_name", "sale_id",
              "keep_id", "member_ids", "names", "phones", "postal_codes",
              "sales_per_member", "projects_per_member", "notes_per_member",
              "statuses", "scheduled_dates", "amounts", "sale_dates", "new_name", "approve"]
    csv_path = out / "approvals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for g in groups:
            w.writerow({k: ("|".join(map(str, v)) if isinstance(v, list) else v) for k, v in g.items()})
    summary = defaultdict(int)
    for g in groups:
        summary[g["type"]] += 1
    md = out / "report.md"
    lines = [
        "# Rapport de doublons Qylot",
        "",
        f"Base : `{db.name}`",
        f"Date : {stamp} UTC",
        "",
        "## Résumé",
        "",
        f"- Groupes clients : **{summary['client']}**",
        f"- Groupes projets : **{summary['project']}**",
        f"- BDC en double : **{summary['sale_bdc']}**",
        f"- Noms utilisateurs à nettoyer : **{summary['user_name']}**",
        "",
        "## Validation",
        "",
        "1. Ouvrir `approvals.csv`.",
        "2. Mettre `approve=yes` uniquement sur les groupes validés.",
        "3. Vérifier `keep_id` : c'est la fiche conservée.",
        "4. Lancer ensuite la fusion avec `CONFIRM=DEDUPE`.",
        "",
        "## Groupes",
        "",
    ]
    for g in groups:
        lines += [
            f"### {g['group_id']} · {g['type']} · confiance {g['confidence']}",
            "",
            f"- Garder : `{g['keep_id']}`",
            f"- Doublons : {', '.join(f'`{x}`' for x in g['member_ids'])}",
        ]
        if g.get("names"):
            lines.append(f"- Noms : {' / '.join(g['names'])}")
        if g.get("phones"):
            lines.append(f"- Téléphones : {' / '.join(map(str, g['phones']))}")
        if g.get("postal_codes"):
            lines.append(f"- Codes postaux : {' / '.join(map(str, g['postal_codes']))}")
        if g.get("sales_per_member"):
            lines.append(f"- Ventes par fiche : {g['sales_per_member']}")
        if g.get("projects_per_member"):
            lines.append(f"- Chantiers par fiche : {g['projects_per_member']}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    (out / "groups.json").write_text(__import__("json").dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def backup(db) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = ROOT / "backups" / f"dedupe-backup-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    if os.environ.get("DEDUPE_BACKUP_MODE") == "targeted":
        # Sauvegarde rapide des seules données concernées par une fusion clients.
        import gzip, json
        data = {"clients": list(db.clients.find({}, {"_id": 0})), "references": {}}
        for coll in db.list_collection_names():
            if coll in ("clients",) or coll.startswith("system."):
                continue
            docs = list(db[coll].find({"client_id": {"$exists": True}}, {"_id": 0, "id": 1, "client_id": 1}))
            if docs:
                data["references"][coll] = docs
        archive = out / "qa-before-dedupe-targeted.json.gz"
        with gzip.open(archive, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        return archive
    archive = out / "qa-before-dedupe.archive.gz"
    dump = os.environ.get("MONGODUMP", "/opt/homebrew/bin/mongodump")
    uri = os.environ.get("QA_MONGO_URI") or os.environ.get("MONGO_URL")
    if not uri:
        raise SystemExit("URI MongoDB absente")
    subprocess.run([dump, f"--uri={uri}", f"--db={db.name}", f"--archive={archive}", "--gzip"], check=True)
    if not archive.exists() or archive.stat().st_size < 1024:
        raise SystemExit("Sauvegarde invalide")
    return archive


def read_approvals(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if str(r.get("approve") or "").strip().lower() in ("yes", "oui", "1", "true")]


def apply_approvals(db, approvals: list[dict]) -> dict:
    if os.environ.get("CONFIRM") != "DEDUPE":
        raise SystemExit("Relance avec CONFIRM=DEDUPE après validation.")
    if not approvals:
        raise SystemExit("Aucun groupe approuvé.")
    archive = backup(db)
    before = {
        "clients": db.clients.count_documents({}),
        "sales": db.sales.count_documents({}),
        "projects": db.projects.count_documents({}),
    }
    stats = defaultdict(int)
    for row in approvals:
        kind = row.get("type")
        keep = (row.get("keep_id") or "").strip()
        members = [x.strip() for x in str(row.get("member_ids") or "").split("|") if x.strip()]
        if not keep or keep not in members or len(members) < 2:
            continue
        company = row.get("company_id") or "default"
        duplicates = [x for x in members if x != keep]
        if kind == "client":
            for coll in db.list_collection_names():
                if coll.startswith("system."):
                    continue
                db[coll].update_many(
                    {"company_id": company, "client_id": {"$in": duplicates}},
                    {"$set": {"client_id": keep}},
                )
            db.clients.delete_many({"company_id": company, "id": {"$in": duplicates}})
            stats["clients_merged"] += 1
        elif kind == "user_name":
            new_name = (row.get("new_name") or "").strip()
            if new_name:
                db.users.update_one({"company_id": company, "id": keep}, {"$set": {"name": new_name}})
                db.team_members.update_many({"company_id": company, "user_id": keep}, {"$set": {"name": new_name}})
                stats["users_trimmed"] += 1
        elif kind == "project":
            for coll in ("project_notes", "project_bonuses"):
                db[coll].update_many({"company_id": company, "project_id": {"$in": duplicates}}, {"$set": {"project_id": keep}})
            db.projects.update_many({"company_id": company, "id": {"$in": duplicates}}, {"$set": {"cancelled": True, "merged_into": keep}})
            stats["projects_merged"] += 1
    stats["backup"] = str(archive)
    stats["before"] = before
    stats["after"] = {
        "clients": db.clients.count_documents({}),
        "sales": db.sales.count_documents({}),
        "projects": db.projects.count_documents({}),
    }
    stats["remaining_client_groups"] = len(client_groups(db))
    stats["remaining_project_groups"] = len(project_groups(db))
    stats["remaining_bdc_groups"] = len(sales_bdc_groups(db))
    return dict(stats)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("report", "apply"))
    parser.add_argument("--approvals", type=Path)
    args = parser.parse_args()
    db = mongo()
    if args.mode == "report":
        groups = client_groups(db) + project_groups(db) + sales_bdc_groups(db) + user_groups(db)
        out = write_report(db, groups)
        print(out)
        print(f"Groupes: {len(groups)}")
        return
    if not args.approvals:
        raise SystemExit("--approvals requis")
    approvals = read_approvals(args.approvals)
    print(apply_approvals(db, approvals))


if __name__ == "__main__":
    main()
