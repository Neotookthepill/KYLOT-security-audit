# KYLOT — runbook de préproduction réelle

Objectif : prouver que le commit déployé fonctionne avec **MongoDB Atlas**, un vrai
navigateur, un vrai domaine, une sauvegarde restaurable et les intégrations réelles.

Ce runbook ne remplace pas un contrat d'hébergement ni un avis juridique.

## 0. Pré-requis

- Atlas : projet dédié staging, cluster M0/M2, utilisateur applicatif dédié.
- Un domaine de staging et un certificat TLS.
- Un hébergeur backend (Render, VPS Docker, etc.) et un hébergeur frontend.
- Un compte Stripe **sandbox**.
- Un fournisseur email (SPF/DKIM/DMARC).
- Une clé IA si l'IA est activée.
- Les secrets dans le gestionnaire de l'hébergeur, jamais dans Git.

## 1. Base Atlas

1. Créer une base `kylot_staging`.
2. Créer un utilisateur applicatif à privilèges limités.
3. Autoriser uniquement les IP de l'hébergeur.
4. Activer les sauvegardes Atlas.
5. Définir `MONGO_URL`, `DB_NAME=kylot_staging`.
6. Ne pas utiliser le compte admin Atlas dans l'application.

## 2. Variables minimales

```text
ENVIRONMENT=staging
APP_VERSION=<sha exact du commit>
MONGO_URL=mongodb+srv://...
DB_NAME=kylot_staging
JWT_SECRET=<secret aléatoire >= 32 caractères>
FRONTEND_URL=https://staging.example.com
CORS_ORIGINS=https://staging.example.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
TRUST_PROXY_HEADERS=true
ADMIN_EMAIL=<email admin staging>
ADMIN_PASSWORD=<mot de passe >= 16 caractères>
ALLOW_PUBLIC_REGISTRATION=false
ALLOW_DEMO_DATA=false
ALLOW_TOKEN_RESPONSE=false
RUN_STARTUP_MIGRATIONS=false
EXPOSE_API_DOCS=false
ALLOW_EXTERNAL_AI=false
ALLOW_EXTERNAL_GEOCODING=false
```

Ajouter Stripe sandbox, email et IA seulement après validation des DPA.

## 3. Déploiement

1. Déployer le commit exact, pas un rebuild non tracé.
2. Vérifier `APP_VERSION=<sha>`.
3. Lancer le pré-vol :

```bash
ENVIRONMENT=staging ... python backend/preflight.py --strict
```

4. Démarrer le backend, vérifier `/health` et `/ready`.
5. Démarrer le frontend derrière Nginx/TLS.
6. Vérifier que `/api` passe par le même domaine que le frontend.

## 4. Smoke test

```bash
STAGING_URL=https://staging.example.com \
STAGING_EMAIL=... \
STAGING_PASSWORD=... \
STAGING_EXPECTED_VERSION=<sha> \
python scripts/staging_smoke.py
```

Le script vérifie : version, health, readiness MongoDB, login, `/auth/me`,
clients, ventes, challenge, prospection et audit.

Si la MFA est active :

```bash
STAGING_MFA_CODE=123456 ...
```

## 5. Sauvegarde initiale

```bash
MONGO_URL='...' DB_NAME='kylot_staging' BACKUP_DIR=./backups \
  ./scripts/backup_mongo.sh
```

Conserver le `.sha256` hors du serveur.

## 6. Restauration testée

Créer une base cible distincte, puis :

```bash
MONGO_URL='...' \
DB_NAME='kylot_staging' \
RESTORE_TARGET_DB='kylot_staging_restore' \
BACKUP_ARCHIVE='./backups/....archive.gz' \
KYLOT_ALLOW_RESTORE_VALIDATION='I_UNDERSTAND_THIS_REPLACES_THE_TARGET_DB' \
./scripts/restore_mongo_validation.sh
```

Vérifier dans la base restaurée :

- nombre d'utilisateurs ;
- nombre de clients ;
- nombre de ventes ;
- nombre de chantiers ;
- index créés ;
- comptes admin.

Puis démarrer une instance de vérification pointant sur `kylot_staging_restore`
et rejouer le smoke test.

**RTO/RPO à mesurer et noter.** Une sauvegarde non restaurée n'est pas une preuve.

## 7. Tests navigateur

À exécuter sur Chrome et mobile :

1. Login admin.
2. Activer la MFA, se déconnecter, se reconnecter avec TOTP.
3. Créer un client.
4. Créer une vente.
5. Vérifier le chantier.
6. Créer le Challenge de Noël 2026.
7. Vérifier le classement et le podium.
8. Modifier une date de chantier et vérifier la commission prospection.
9. Couper le réseau, faire une modification, se reconnecter.
10. Provoquer un 401 et vérifier que la file hors ligne est conservée.
11. Vérifier les rôles commercial/technicien.
12. Vérifier Stripe sandbox.

## 8. Critères go/no-go

- Smoke test : OK.
- Restauration : OK, RTO/RPO mesurés.
- Aucun P1 ouvert.
- MFA testée.
- Challenge testé avec données depuis le 1er novembre.
- Commissions testées sur un changement de date.
- Stripe sandbox : abonnement, essai, impayé, remboursement.
- Emails reçus.
- Monitoring et alertes actifs.
- Rollback testé.

## 9. Rollback

1. Redéployer l'image/commit précédent.
2. Ne pas restaurer la production par-dessus une base active sans accord.
3. Conserver les données créées après le déploiement.
4. Vérifier `/api/version` après rollback.

## 10. Preuves à archiver

- SHA du commit déployé.
- Sortie du smoke test.
- Hash de la sauvegarde.
- Rapport de restauration.
- Captures Playwright.
- Relevés de latence.
- Décision go/no-go signée.
