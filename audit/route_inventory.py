"""Emit a reviewable Markdown inventory of every FastAPI route in server.py.

The columns are conservative static indicators, not a replacement for dynamic
authorization tests.  A dash means that the marker is not visible in the route
function itself and may still be enforced by a called helper.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "backend/server.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def yes(value: bool) -> str:
    return "oui" if value else "—"


def resource_for(path: str) -> str:
    """Return the primary domain named by the route, for human review."""
    parts = [part for part in path.split("/") if part and part != "api"]
    return parts[0] if parts else "application"


def operation_for(method: str) -> str:
    return {
        "GET": "lecture/export",
        "POST": "création/action",
        "PUT": "remplacement/action",
        "PATCH": "modification",
        "DELETE": "suppression",
    }.get(method, "action")


def inventory():
    rows = []
    for node in TREE.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.get_source_segment(SOURCE, node) or ""
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                and decorator.args
            ):
                continue
            try:
                path = ast.literal_eval(decorator.args[0])
            except Exception:
                continue
            auth = "publique"
            for marker, label in (
                ("require_super_admin", "super-admin"),
                ("require_admin", "admin"),
                ("require_sales_access", "rôles ventes"),
                ("get_current_user", "session"),
            ):
                if marker in body:
                    auth = label
                    break
            permission = []
            for marker, label in (
                ("check_perm(", "permission"), ("require_role(", "rôle"),
                ("_is_manager(", "manager"), ("_stock_rbac_check(", "stock RBAC"),
                ("_ensure_project_scope(", "scope projet"), ("_own_sales_filter(", "scope vente"),
            ):
                if marker in body:
                    permission.append(label)
            method = decorator.func.attr.upper()
            rows.append({
                "method": method, "path": path, "function": node.name,
                "line": node.lineno, "auth": auth, "permission": ", ".join(permission) or "—",
                "resource": resource_for(path), "operation": operation_for(method),
                "direct_id": yes("{" in path and "}" in path),
                "tenant": yes("cq(" in body or "company_id" in body or "with_company(" in body),
                "owner": yes(any(x in body for x in ("user[\"id\"]", "user['id']", "author_id", "created_by"))),
                "audit": yes("log_audit(" in body),
                "idempotence": yes(any(x in body.lower() for x in ("idempot", "duplicate", "upsert"))),
                "limit": yes(any(x in body for x in ("max_length", "MAX_", ".limit(", "to_list(", "Query("))),
            })
    return rows


if __name__ == "__main__":
    rows = inventory()
    print(f"# Inventaire statique des {len(rows)} routes KYLOT\n")
    print("Les colonnes sont des indices statiques conservateurs. Un tiret signifie que le contrôle n'est pas visible dans le corps de la route ; il peut exister dans un helper appelé.\n")
    print("| Méthode | Route | Ressource | Opération | Fonction/ligne | Auth attendue visible | Contrôle visible | ID direct | Société | Propriétaire | Audit | Idempotence | Limite |")
    print("|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['method']} | `{row['path']}` | {row['resource']} | {row['operation']} | "
            f"`{row['function']}:{row['line']}` | {row['auth']} | {row['permission']} | "
            f"{row['direct_id']} | {row['tenant']} | {row['owner']} | "
            f"{row['audit']} | {row['idempotence']} | {row['limit']} |"
        )
