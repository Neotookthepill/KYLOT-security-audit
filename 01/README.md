# KYLOT

Application de gestion commerciale et opérationnelle : clients, ventes, chantiers, planning, équipe, stock, commissions, exports et assistant IA.

## État de cette copie

Cette copie locale contient les correctifs de sécurité issus des trois campagnes de contre-audit. Elle conserve l'interface d'origine. Son statut est **prête pour une validation en préproduction**, pas encore une certification de production.

Lire avant toute livraison :

- `SECURITY-FIX-REPORT-2026-10-18.md` : correctifs, preuves, résultats et tests restant à effectuer ;
- `SECURITY-VALIDATION-2026-10-19.md` : dernière matrice multi-entreprises, entrées hostiles, volume et limites de validation ;
- `DEPLOYMENT.md` : configuration, staging, sauvegarde et retour arrière ;
- `AUTHORIZATION-MATRIX-2026-10-16.md` : rôles, permissions et portées attendues ;
- `ROUTE-INVENTORY-2026-10-16.md` : inventaire des routes à utiliser pour la recette multi-rôles.

## Démarrage local

Prérequis : Python compatible avec les dépendances du backend, Node.js, Yarn 1.22 et MongoDB.

1. Copier `backend/.env.example` vers `backend/.env` et remplacer les valeurs locales nécessaires.
2. Installer les dépendances Python de `backend/requirements.txt` dans un environnement virtuel.
3. Lancer l'API FastAPI depuis la racine du projet.
4. Copier `frontend/.env.example` vers `frontend/.env`.
5. Dans `frontend`, exécuter `yarn install --frozen-lockfile`, puis `yarn start`.

Les comptes, clés Stripe, clés IA et secrets cron ne doivent jamais être ajoutés au dépôt.

## Validation locale

Depuis la racine :

```bash
./scripts/run_local_validation.sh
```

Ou, pour exécuter les contrôles séparément :

```bash
PYTHONPATH=. ./.venv/bin/pytest -q \
  backend/test_security_invariants.py \
  backend/test_preflight.py \
  backend/test_app_smoke.py \
  backend/test_integration_security.py

PYTHONPATH=. ./.venv/bin/python audit/security_adversarial_checks.py
PYTHONPATH=. ./.venv/bin/python audit/security_adversarial_round2.py
PYTHONPATH=. ./.venv/bin/python audit/security_adversarial_round3.py
PYTHONPATH=. ./.venv/bin/python audit/security_e2e_matrix.py
PYTHONPATH=. ./.venv/bin/python audit/security_hostile_inputs.py
PYTHONPATH=. ./.venv/bin/python audit/security_scale_checks.py
PYTHONPATH=. ./.venv/bin/python audit/security_route_business_fuzz.py
./.venv/bin/bandit -q -r backend/server.py

cd frontend
CI=true yarn test --watchAll=false --runInBand
yarn build
yarn audit --groups dependencies
```

Résultat de référence du 19 octobre 2026 : 109 contrôles de sécurité et de robustesse, 40 tests serveur et 23 tests interface réussis, soit 172 tests automatisés ; build production réussi ; aucun avis connu dans les environnements Python installé et JavaScript de production audité.

Couverture mesurée sur cette campagne : 21 % des instructions de `backend/server.py` par les 40 tests serveur standards, et 3,11 % des lignes du frontend par les 23 tests interface. Les suites adversariales augmentent la surface serveur exercée, mais ces chiffres confirment que le nombre de tests ne constitue pas une preuve de couverture exhaustive.

## Production

Ne pas lancer les migrations automatiquement au démarrage. Effectuer d'abord une sauvegarde restaurable, puis suivre `DEPLOYMENT.md` et exécuter la migration contrôlée avec :

```bash
python -m backend.migrate --apply
```

La mise en production reste bloquée tant que les parcours multi-rôles, MongoDB réel, Stripe sandbox, emails, IA, mode hors ligne et restauration de sauvegarde n'ont pas été validés sur staging.
