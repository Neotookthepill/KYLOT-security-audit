# KYLOT — Politique de persistance des données (iter165)

**Contrainte majeure d'architecture** — Aucune mise à jour de l'application ne doit supprimer, écraser ou rendre inaccessibles les données déjà enregistrées par les utilisateurs.

---

## 1) Architecture de stockage

- **Base MongoDB externe** (URL `MONGO_URL` via variable d'environnement) : la BDD vit **en dehors** du conteneur d'application. Un redéploiement, une reconstruction d'image ou un pod restart n'affecte **jamais** les données.
- Toutes les collections métier vivent dans la même DB (`DB_NAME`) : `users`, `companies`, `clients`, `sales`, `projects`, `project_notes`, `settings`, `team_members`, `notifications`, `audit_log`, `documents`, `overtime`, `absences`, `events`, `reinterventions`, `bonus_awards`, `project_bonuses`, `ai_memories`, `payment_transactions`, `stripe_events`.
- Les photos sont stockées inline (base64) dans `projects.photos` — pas de bucket S3 à re-synchroniser.

## 2) Règles absolues côté code

- ❌ **INTERDIT** dans tout le codebase : `drop_collection`, `drop_database`, `delete_many({})` sans filtre.
- ✅ **Toutes** les requêtes `delete_*` doivent avoir un filtre `company_id` ou équivalent (audit iter161 : conforme).
- ✅ Les migrations au démarrage sont **strictement additives** :
  - `migrate_sales_statuses` : renomme des valeurs (`update_many`) sans supprimer
  - `migrate_projects_assigned_to` : convertit `str` → `list` sans supprimer
  - `migrate_multi_tenant` : backfill `company_id` sur les documents sans en supprimer
- ✅ Le webhook Stripe (iter161) : **jamais** de `db.*.delete_*` en réponse à un événement de paiement/abonnement.

## 3) Suspension d'abonnement (rappel iter161)

- `subscription_status="suspended"` → API métier bloquée (HTTP 402) mais **aucune** donnée touchée.
- Auth, billing, `/api/subscription/me`, `/api/company/me` restent accessibles pour la régularisation.
- Reconnexion après régularisation → même email + mot de passe + `company_id` inchangé → toutes les données retrouvées à l'identique.

## 4) Garde-fou de démarrage (iter165)

`on_startup` :
1. Relève les volumes des collections critiques dans `_preserve_before` **avant** toute migration/seed.
2. Après migrations, log `[persistence] <coll>: N_avant → N_après (OK)` pour chaque collection.
3. Si `N_après < N_avant` sur une collection non vide → **`logger.critical`** avec un message d'alerte. Un monitoring externe (prometheus/loki) doit alerter l'ops.
4. Le démarrage n'est pas bloqué (pour permettre les envs de test vides), mais toute régression de volume est tracée.

## 5) Cycle de mise à jour

1. Modifier le code (routes, modèles, front) — **jamais** la donnée existante d'un utilisateur.
2. Ajouter au besoin une migration additive dans `on_startup` (ex: `settings.setdefault(...)`).
3. Déployer via `Save to Github` → pipeline Emergent → nouveau pod. La BDD n'est **pas** touchée.
4. Au démarrage du nouveau pod : le log `[persistence]` doit montrer des volumes ≥ ceux du pod précédent.

## 6) Sauvegarde de sécurité

- La sauvegarde native MongoDB (`mongodump`) est de la responsabilité de la couche hébergement (Emergent-managed MongoDB inclut un snapshot journalier).
- Recommandation : avant tout déploiement contenant une migration structurelle (ajout/renommage d'un champ Pydantic obligatoire), effectuer un `mongodump` manuel via l'ops et le stocker hors du cluster.

## 7) Résiliation volontaire

- La résiliation Stripe (`customer.subscription.deleted`) passe `subscription_status` à `cancelled` — les données restent.
- Toute suppression **définitive** doit passer par un endpoint admin explicite (à créer ultérieurement) avec double confirmation utilisateur et respect RGPD (délai de rétention).

---

**Cette politique doit être respectée par tout futur agent/dev intervenant sur Kylot.**
