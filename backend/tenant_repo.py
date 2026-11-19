"""Accès MongoDB multi-tenant centralisé.

Toute requête métier doit passer par TenantRepository. Le company_id vient
exclusivement de l'utilisateur authentifié et ne peut jamais être choisi par
le client HTTP. Ce module est volontairement sans dépendance FastAPI pour
pouvoir être testé et réutilisé par les services.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


class TenantIsolationError(PermissionError):
    """Tentative d'accès à une autre entreprise."""


class TenantRepository:
    def __init__(self, db: Any, user: Mapping[str, Any]):
        company_id = str((user or {}).get("company_id") or "").strip()
        if not company_id:
            raise TenantIsolationError("Utilisateur sans company_id")
        self.db = db
        self.user = dict(user)
        self.company_id = company_id

    def _scoped(self, query: Optional[Mapping[str, Any]]) -> dict:
        q = dict(query or {})
        supplied = q.get("company_id")
        if supplied is not None and str(supplied) != self.company_id:
            raise TenantIsolationError("Accès inter-entreprise refusé")
        q["company_id"] = self.company_id
        return q

    def _col(self, name: str):
        if not name or name.startswith("system."):
            raise TenantIsolationError("Collection invalide")
        return self.db[name]

    async def count(self, collection: str, query: Optional[Mapping[str, Any]] = None) -> int:
        return await self._col(collection).count_documents(self._scoped(query))

    async def find_one(self, collection: str, query: Optional[Mapping[str, Any]] = None,
                       projection: Optional[Mapping[str, Any]] = None) -> Optional[dict]:
        return await self._col(collection).find_one(self._scoped(query), projection)

    def find(self, collection: str, query: Optional[Mapping[str, Any]] = None,
             projection: Optional[Mapping[str, Any]] = None):
        return self._col(collection).find(self._scoped(query), projection)

    async def insert_one(self, collection: str, document: Mapping[str, Any]):
        doc = dict(document or {})
        supplied = doc.get("company_id")
        if supplied is not None and str(supplied) != self.company_id:
            raise TenantIsolationError("Insertion dans une autre entreprise refusée")
        doc["company_id"] = self.company_id
        return await self._col(collection).insert_one(doc)

    async def update_one(self, collection: str, query: Mapping[str, Any],
                         update: Mapping[str, Any], *, upsert: bool = False):
        patch = dict(update or {})
        for operator in ("$set", "$setOnInsert", "$unset"):
            values = patch.get(operator)
            if isinstance(values, Mapping) and "company_id" in values:
                if str(values["company_id"]) != self.company_id:
                    raise TenantIsolationError("Modification du company_id refusée")
        return await self._col(collection).update_one(self._scoped(query), patch, upsert=upsert)

    async def delete_one(self, collection: str, query: Mapping[str, Any]):
        return await self._col(collection).delete_one(self._scoped(query))

    async def aggregate(self, collection: str, pipeline: Sequence[Mapping[str, Any]]):
        """Ajoute un $match company_id en tête, sans faire confiance au pipeline."""
        stages = [{"$match": {"company_id": self.company_id}}, *list(pipeline or [])]
        return self._col(collection).aggregate(stages)
