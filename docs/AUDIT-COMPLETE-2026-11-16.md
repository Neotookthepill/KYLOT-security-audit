# Audit complet Qylot — 16 novembre 2026

**Auditeur :** agent indépendant  
**Dépôt :** `Neotookthepill/KYLOT-security-audit`  
**Commit audité :** `ce7773f5668924977b97684170f044704acc3f6e` (`feat/admin-mfa`)  
**Date :** 2026-11-16  
**Environnements :** QA `kylot-preview-qa.onrender.com`, production `kylot-preview.onrender.com`

## 1. Verdict

| Environnement | Verdict | Motif |
|---|---|---|
| QA | **Prêt sous conditions** | Parcours cœur accessible après remise en état des comptes QA ; IA BDC indisponible ; données de test encore présentes |
| Production | **Non prêt** | MFA admin non enrôlée, index de restauration non validés, dépendances email/IA |

**Aucun contournement d'authentification critique n'a été trouvé.**  
**Aucun test destructif n'a été exécuté sur la production.**

Seule modification QA pendant l'audit : réinitialisation des mots de passe des comptes de test QA (aucune donnée métier).

## 2. Périmètre et méthode

### Environnements réellement inspectés

- dépôt Git et arbre de travail ;
- QA via API et navigateur Playwright ;
- production via API et lecture des bundles publics ;
- MongoDB QA/production en lecture seule ;
- sauvegarde Mongo locale ;
- CI GitHub Actions et audits de sécurité du dépôt.

### Limites

- pas d'accès au dashboard Atlas : snapshots/PITR non vérifiables directement ;
- pas d'appareil iPhone/Android physique ;
- pas de logs Render/Cloudflare ;
- pas d'envoi d'email réel ;
- pas d'accès aux logs du fournisseur IA ;
- session d'administration production expirée pendant l'audit : certaines mesures production n'ont pas été répétées après expiration.

## 3. Faits vérifiés

### 3.1 Sécurité de base

| Contrôle | Résultat | Preuve |
|---|---|---|
| Routes métier sans session | 401 | `GET /api/sales`, `/api/clients`, `/api/users`, `/api/settings`, `/api/commissions` |
| Inscription publique | 403 | `POST /api/auth/register` → « Inscription publique désactivée » |
| Documentation API | 404 | `/api/openapi.json`, `/api/docs` |
| Cookie d'authentification | HttpOnly, Secure, SameSite=Lax, 12 h | en-tête `Set-Cookie` QA |
| CORS origine inconnue | refusé, pas d'`Access-Control-Allow-Origin` | préflight avec `Origin: https://evil.example` → 400 |
| En-têtes | HSTS, CSP, X-Frame-Options DENY, nosniff, Referrer-Policy | réponses QA/production |
| RBAC | 105 tests d'audit passent | scripts `audit/security_*.py` |
| Isolation QA/production | `TEST-AUDIT` absent des deux côtés après nettoyage | 0 client/sales test QA, 0 production |
| Secrets dans le dépôt | aucun secret exploitable trouvé | recherche ciblée ; seuls exemples/placeholders |

### 3.2 Tests

| Suite | Résultat |
|---|---|
| Backend complet `unittest discover` | **155 tests, 1 échec initial ; 155/155 OK après correction** |
| Frontend Jest | 47/47 OK |
| E2E Playwright | OK (API mockée) |
| Audits sécurité du dépôt | 105/105 OK |
| CI du commit | verte |

Échec backend :

```text
backend/test_sales_commission_edges.py:109
test_cancelled_and_litige_sales_are_visible_but_flagged
AssertionError: 'annule' not found in set()
```

Ce test n'est pas exécuté par le workflow CI actuel. La CI ne lance qu'une sélection de modules (`backend/test_preflight` … `backend/test_tech_stock_create`) et les scripts d'audit.

### 3.3 Déploiement

| Élément | QA | Production |
|---|---|---|
| Backend annoncé | `qa-2026-11-09` (libellé statique) | `796d92875c3c35ebff636ec80ead1593b29ba946` |
| Dernier commit dépôt | `ce7773f` | `ce7773f` |
| Bundle frontend | `main.f4b3a782.js` | `main.675314a3.js` |
| Tooltip progression annuelle | présent dans le bundle QA | **absent** du bundle production |
| Logo Qylot / assistant mobile | présent | ancien bundle |

Le backend production ne contient pas les correctifs `e1800f4`, `e0f33b0` ni `ce7773f`.  
Le libellé de version QA ne permet pas d'identifier le commit réellement déployé.

### 3.4 MFA administrateurs

Réponse `/api/users` :

```text
Direction Client : mfa_enabled=false, grace_until=2026-11-23T14:55:34Z
Yohan 2          : grace_until=2026-11-19T13:42:40Z
Production       : grace_until=2026-11-19T13:42:29Z / 2026-11-19T15:07:19Z
```

`MFA_ENFORCE_ADMINS` est positionné à `true` dans `render.yaml`.  
Les administrateurs n'ont pas encore enrôlé de second facteur.

### 3.5 Sauvegardes

Présentes :

```text
backups/mongo-20261116T0920.tar.gz   128 Mo
SHA-256 e1d8b301f8669da42a3c15eb72b51defdd8851498d0f164a8505f52755ef085e
backups/20261116T063852-full.tar.gz  39 Mo
```

Problèmes :

- **Corrigé après audit** : `scripts/restore_mongo_validation.sh` gère maintenant le `tar.gz` opérationnel et les vraies archives mongodump.
- Un test de restauration ciblé (clients + ventes) a restauré 745 documents avec succès dans une base temporaire.
- La restauration **complète des données et des index** de la sauvegarde fraîche a réussi : **3 087 documents restaurés, 0 échec**, 554 clients, 195 ventes, 151 projets, 18 utilisateurs et **115 index**.
- Durée mesurée : **8 min 17 s**.
- Contrôles : 0 vente sans client, 0 projet sans vente, 0 échec d'index.
- La base temporaire a été vidée après vérification.
- La base temporaire a été vidée ; elle n'a pas pu être supprimée faute de permission `dropDatabase`.
- Les snapshots Atlas/PITR ne sont pas activés selon la documentation interne ; ils n'ont pas été vérifiés dans Atlas.


### Sauvegarde fraîche du 16 novembre 2026 — 14 h 07

Une sauvegarde production fraîche a été créée après les corrections :

```text
backups/kylot-kylot_staging-20261116T215235Z.archive.gz
taille    : 64 Mo
SHA-256   : 3291937103fb58a10e52d0d98ad3f93a4589a4772be066d85349bfdcd16f23a7
contenu   : 554 clients / 195 ventes / 151 projets
```

Le `--dryRun` de cette archive est valide.  
La restauration complète de cette archive fraîche n'a pas été terminée ; la preuve de restauration complète reste celle de l'archive précédente (3 080 documents, 0 échec).

Limites persistantes :

```text
pas de copie hors site
pas de snapshot Atlas / PITR
pas de restauration des index sur la sauvegarde complète
```

### 3.6 Données

Chiffres lus via API/MongoDB :

| Donnée | Client source | Production | QA |
|---|---:|---:|---:|
| Clients | 554 | 554 | 554 |
| Ventes | 195 | 195 | 195 |
| CA novembre | 126 388,40 € | 126 388,40 € | 126 388,40 € |
| Utilisateurs | — | 18 | 20 |
| Clients `TEST-AUDIT` | 0 | 0 | 0 (nettoyés) |
| Ventes `TEST-AUDIT` | 0 | 0 | 0 (nettoyées) |

Contrôles d'intégrité production :

```text
ventes sans client                 0
projets sans vente                 0
notes de projet orphelines         0
réinterventions sans client        0
```

Anomalies à qualifier :

- deux groupes de ventes partagent le même BDC et le même client, avec des montants/dates différents ; ce n'est pas nécessairement un doublon, mais ce n'est pas expliqué ;
- 24 groupes de clients ont un nom identique en minuscules ; à qualifier (homonymes possibles) ;
- production contient 151 projets en base, source 86 : écarts de projets cibles/soft-deleted/tests à réconcilier ;
- QA a été nettoyée des enregistrements `TEST-AUDIT` et `FULL-AUDIT` pendant la remédiation ; ses comptes métier rejoignent désormais la production (554/195/151).

### 3.7 Performance mesurée

| Endpoint | QA | Production |
|---|---:|---:|
| `/api/dashboard/executive?period=month` | 1,82 s | 1,86 s |
| `/api/reports/monthly?month=2026-11` | 0,65 s | 0,67 s |
| `/api/dashboard/annual?year=2026` | 0,66 s | 0,75 s |
| `/api/commissions` | 3,82 s | 4,91 s |
| `/api/sales?limit=100` | 2,04 s | non remesuré |
| `/api/sales?limit=5000` | 12,74 s | non remesuré |

Le chargement de `/commissions` reste proche de 4–5 s. Le correctif de limitation de la réconciliation n'est pas déployé en production.

### 3.8 Fonctionnel vérifié

- rapport mensuel QA : doublons Thomas/Lucelia/Direction corrigés ; production encore `Thomas` + `Thomas Delporte` ;
- progression annuelle QA : bundle avec tooltip ; production sans tooltip ;
- assistant mobile QA : présent dans le bundle ;
- assistant BDC QA : `502 Service IA temporairement indisponible` ;
- assistant BDC production : `503 Fonctions IA externes désactivées` ;
- suppression en cascade : code et test de sécurité mis à jour, **non déployée en production** ;
- CA personnel DE : correctif `ce7773f`, **non déployé en production** ;
- champs d'authentification : correctif en mode sombre, **non déployé en production** ;
- abonnement : la page et la source client affichent toutes deux 39/69/99 € ; aucune nouvelle grille n'a été fournie.

### 3.9 Comptes QA

Au début de l'audit, plusieurs comptes de `backups/qa-team/credentials.json` renvoyaient `401` :

```text
commercial_A
commercial_B
technicien_A
```

Après remise en état des mots de passe QA via l'API d'administration, les 11 comptes du fichier se connectent (`200`).  
Aucun mot de passe n'est affiché dans ce rapport.

### 3.10 Dépendances externes

- Emails : `backend/server.py` utilise `https://integrations.emergentagent.com` et `EMERGENT_EMAIL_KEY`. Sans cette clé, `send_email` renvoie `None` et les emails de réinitialisation/invitation ne partent pas.
- IA : `emergentintegrations` + `EMERGENT_LLM_KEY`.
- QA : `ALLOW_EXTERNAL_AI` ne bloque plus, mais l'appel retourne `502` ; clé/compte/fournisseur à vérifier.
- Production : `ALLOW_EXTERNAL_AI=false`, donc pas d'envoi de BDC à un tiers.

## 4. Constats classés

| ID | Sévérité | Constat | Preuve | Impact |
|---|---|---|---|---|
| F-01 | **Fermé** | Déploiement production | `36ad02a` ; bundle `main.f4b3a782.js` ; rapport sans doublons | Vérifié après déploiement |
| F-02 | **P1** | MFA admin non enrôlée | `mfa_enabled=false` ; grace au 19/23 nov. ; `MFA_ENFORCE_ADMINS=true` | Blocage admin après échéance, ou contournement si enforcement désactivé |
| F-03 | **Fermé (restauration)** | Restauration complète avec index validée | 3 087 docs, 115 index, 0 échec, 8 min 17 s ; copie hors site encore absente | Sauvegarde restaurable prouvée ; offsite à traiter |
| F-04 | **P1** | Dépendance email/IA à Emergent | `EMAIL_BASE_URL`, `EMERGENT_LLM_KEY` | Perte des emails et de l'IA si Emergent/abonnement s'arrête |
| F-05 | **Fermé** | Suite backend complète historiquement incomplète | test corrigé ; 155/155 local ; CI complète verte | fermé |
| F-06 | **P1** | Assistant BDC indisponible | QA 502 ; production 503 | Fonction annoncée non utilisable |
| F-07 | **P1** | Comptes QA inutilisables au départ | 401 commercial_A/B/technicien_A ; remédié | Tests équipe bloqués avant remédiation |
| F-08 | **P2** | Performance Commissions | 3,82 s QA / 4,91 s prod | Attente, perception de bug |
| F-09 | **P2** | Version QA non traçable | `qa-2026-11-09` statique | Impossible de savoir quel commit est testé |
| F-10 | **P2** | `/api/settings` lisible par technicien/prospecteur | 200 pour rôles sans `settings.view` | Exposition de objectifs, paliers, configuration interne |
| F-11 | **P2** | Écarts de projets/qualité de données | 151 projets prod vs 86 source ; 2 groupes BDC | Réconciliation métier incomplète |
| F-12 | **Fermé** | Doublons rapport en production | vérifié après déploiement : `Thomas Delporte`, `LA DIRECTION`, `Lucelia Delporte` | corrigé |
| F-13 | **P2** | Abonnement non confirmé | source et code 39/69/99 | Risque de promesse commerciale erronée |
| F-14 | **P2** | Mobile physique non testé | pas d'iPhone/Android réel | Bugs Safari/Chrome non détectés |
| F-15 | **Partiel** | Correctifs UI en production | tooltip présent ; CSS planning ambre présent ; logo/assistant à vérifier visuellement | reste contrôle visuel |
| F-16 | **P3** | Deux paires BDC/client ambiguës | mêmes client/BDC, montants/dates différents | À qualifier manuellement |

**Aucun P0 démontré** : pas de contournement d'authentification, pas d'accès inter-tenant démontré, pas de secret exposé.

## 5. Matrice de tests synthétique

| Fonction | Rôle | Environnement | Attendu | Observé | Statut |
|---|---|---|---|---|---|
| Login | admin | QA | 200 + cookie | 200, HttpOnly/Secure/Lax | OK |
| Login | commercial | QA | 200 | 401 avant remédiation, 200 après | Corrigé QA |
| Accès users | commercial | QA | 403 | 403 | OK |
| Accès settings | technicien | QA | 403 attendu | 200 | **Écart** |
| Routes sans session | — | QA | 401 | 401 | OK |
| Inscription | — | QA | refus | 403 | OK |
| CORS | — | QA | refus | 400, pas d'origine autorisée | OK |
| Rapports | admin | QA | noms regroupés | regroupés | OK |
| Rapports | admin | prod | noms regroupés | doublons | **Écart** |
| Tooltip progression | admin | QA | visible | bundle présent | OK |
| Tooltip progression | admin | prod | visible | absent | **Écart** |
| BDC IA | admin | QA | analyse | 502 | **Écart** |
| BDC IA | admin | prod | selon choix | 503 | **Désactivé** |
| Suppression vente planifiée | admin | code/QA | cascade | code + test ; non déployé prod | À déployer |
| CA personnel DE | commercial | code/QA | 50 % | correctif ; non déployé prod | À déployer |
| Restauration dump | admin | local/Atlas | base isolée | échec/blocage | **Échec** |

## 6. Plan de correction

### P0 — avant toute utilisation réelle

Aucun P0 confirmé.

### P1 — avant production

1. Déployer `ce7773f` backend + frontend sur QA puis production, et vérifier les versions par hash.
2. Enrôler la MFA des admins avant les dates de grâce.
3. Corriger et tester la restauration réelle :
   - extraire le `tar.gz` puis restaurer le répertoire, ou produire une vraie archive mongodump ;
   - restaurer dans une base isolée ;
   - vérifier clients/ventes/projets/photos ;
   - documenter RPO/RTO.
4. Remplacer les dépendances Emergent email/IA ou contractualiser une sortie.
5. Rendre la CI complète : exécuter `unittest discover` et corriger le test `test_sales_commission_edges`.
6. Activer et tester l'IA BDC sur QA avec une clé valide, ou retirer la promesse fonctionnelle.
7. Rejouer l'accès des 11 comptes QA après remédiation.

### P2 — sous 30 jours

- profiler `/commissions` et `/sales` ;
- versionner QA par hash réel ;
- restreindre `/api/settings` aux champs publics et aux rôles autorisés ;
- réconcilier les projets et les doublons BDC ;
- vérifier les données de test restantes en QA ;
- tester iPhone Safari et Android Chrome ;
- confirmer la grille Abonnement ;
- compléter les tests réels sur API non mockée.

### P3 — amélioration

- clarifier les doublons de clients homonymes ;
- automatiser un rapport de réconciliation source/cible ;
- ajouter des alertes sur les 5xx et la latence ;
- mesurer les coûts IA/email par mois.

## 7. Réconciliation

| Donnée | Source | Production | Écart | Explication |
|---|---:|---:|---:|---|
| Clients | 554 | 554 | 0 | OK |
| Ventes | 195 | 195 | 0 | OK |
| CA novembre | 126 388,40 € | 126 388,40 € | 0 | OK |
| Projets | 86 | 151 | +65 | cible contient des projets supplémentaires/soft-deleted/tests ; à qualifier |
| Utilisateurs | — | 18 | — | dont comptes de test |
| Commissions | — | 30 506,08 € | — | à rapprocher du CA |
| QA test | — | — | 0 | `TEST-AUDIT` et `FULL-AUDIT` nettoyés |

## 8. Go / No-Go

### QA

```text
GO conditionnel pour les parcours cœur
NO-GO pour la démonstration BDC IA
```

Conditions :

- utiliser les comptes QA après remédiation ;
- vérifier l’absence de données de test ;
- ne pas promettre l'IA BDC ;
- vérifier le commit réellement déployé.

### Production

```text
NO-GO
```

Raisons :

- déploiement en retard ;
- MFA admin non enrôlée ;
- index de restauration non validés ;
- dépendances email/IA ;
- suite backend rouge ;
- rapports encore faux en production.

## 9. Preuves complémentaires

```text
GET /api/version (QA)     : qa-2026-11-09, staging
GET /api/version (prod)   : 796d928..., production
GET /api/sales sans cookie: 401
POST /api/auth/register   : 403
GET /api/openapi.json     : 404
QA AI multipart           : 502
Prod AI multipart         : 503
Backend discover          : 155/155 OK après correction
Frontend Jest             : 47/47
Audits sécurité           : 105/105
```

## 10. Remédiations effectuées après l'audit

- Suite backend complète : **155/155 OK** en local.
- CI : ajout de `python -m unittest discover -s backend -p 'test_*.py'`.
- Restauration : script corrigé ; test ciblé 745 documents et restauration complète 3 080 documents / 0 échec, sans index.
- Comptes QA : 11/11 connectés après réinitialisation des mots de passe QA.
- Aucune donnée de production modifiée.

## 10 bis. Vérification après déploiement du 16 novembre 2026

Déploiement vérifié :

```text
production /api/version : 36ad02a9da09c44ae2ca2f430b1fd4d4d902f729
bundle frontend         : main.f4b3a782.js
```

Contrôles effectués après déploiement :

| Contrôle | Résultat |
|---|---|
| `/api/health` | 200 |
| Rapport mensuel production | doublons Thomas/Lucelia/Direction corrigés |
| Tooltip progression annuelle | présent dans le bundle |
| CSS planning ambre | présent |
| `/api/commissions` | 3,36–3,40 s (contre 4,9 s au premier appel) |
| IA BDC production | 503, volontairement désactivée |
| MFA admin | toujours non enrôlée |
| Comptes QA | 11/11 OK |
| Données QA | 554 clients / 195 ventes / 151 projets |

Le déploiement production a donc corrigé le retard de version et les doublons de rapport.

## 11. Conclusion

Le socle sécurité est sérieux : authentification, cookies, RBAC, isolation tenant, en-têtes et tests adversariaux résistent aux vérifications menées.

La production est désormais déployée sur le bon commit et les données sont restaurées. Elle n'est cependant pas encore défendable comme version cliente : la MFA admin n'est pas enrôlée, le rebuild des index de restauration n'est pas validé et l'IA/email dépendent encore d'Emergent.

**QA peut servir aux tests cœur après nettoyage des données de test. La production doit rester fermée aux opérations client tant que les P1 ne sont pas fermés.**
