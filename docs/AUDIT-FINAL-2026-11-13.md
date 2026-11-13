# Contre-audit Qylot — 13 novembre 2026

> Audit en lecture seule. Aucun correctif appliqué.
> Aucune donnée de production créée, modifiée ou supprimée.

## 1. Résumé non technique

Qylot fonctionne, la CI est verte et les parcours principaux testés en lecture seule sont cohérents.
Mais la recette finale ne peut pas être prononcée :

- la MFA admin n'est pas activée ;
- les rôles autres qu'administrateur n'ont pas de comptes de test disponibles ;
- l'isolation entre sociétés n'a pas été prouvée ;
- Safari, iPhone, Android et Firefox réels n'ont pas été testés ;
- Stripe, les emails, l'IA et Atlas n'ont pas été validés dans un environnement sûr ;
- aucune sauvegarde/restauration n'a été réalisée ;
- le parcours métier complet n'a pas été exécuté sur des données `TEST-AUDIT-` ;
- l'E2E interface utilise des API mockées, pas le backend réel.

Verdict : **PILOTE ACCOMPAGNÉ**, pas commercialisable en autonomie.

## 2. Déploiement

| Élément | Résultat |
|---|---|
| Commit production `bae0ce4` | OK |
| Frontend servi `main.5e9fa621.js` | OK |
| `/api/health` | 200 |
| `/api/ready` | 200 — `ready` |
| `/api/version` | 200 — `bae0ce4` |
| CI du commit déployé | verte |
| Dépôt HEAD | `d37c872` (documentation uniquement) |
| `/docs` / `/openapi.json` | 404 |
| `/api/auth/register` | 405 |
| Rollback | BLOQUÉ — pas testé |
| Variables obligatoires | BLOQUÉ — non inspectables sans accès Render |
| Redémarrage Render | BLOQUÉ — non provoqué |

## 3. Tests automatisés

| Suite | Résultat |
|---|---|
| Backend | 121 réussis, 0 échec |
| Frontend | 47 réussis, 0 échec |
| E2E P1 CI | 1 scénario réussi |
| Total automatisé | 169 réussis |

L'E2E P1 couvre : colonnes Ventes, panneau latéral, onglets Kanban, chargement progressif, assistant mobile.
Il utilise des **routes API mockées** : il ne prouve pas le backend réel.

## 4. Authentification

| Test | Résultat | Preuve |
|---|---|---|
| Connexion admin valide | RÉUSSI | HTTP 200 |
| Cookie de session | RÉUSSI | `HttpOnly; Secure; SameSite=Lax` |
| `/auth/me` avec session | RÉUSSI | HTTP 200 |
| `/auth/me` sans session | RÉUSSI | HTTP 401 |
| Déconnexion | RÉUSSI | logout 200, puis `/auth/me` 401 |
| API protégée sans session | RÉUSSI | clients/sales/projects/settings → 401 |
| Inscription publique | RÉUSSI | endpoint 405 |
| Mot de passe oublié / lien expiré / réutilisé | BLOQUÉ | pas de flux de test isolé |
| Mauvais mot de passe sur compte réel | BLOQUÉ | évite verrouillage du compte admin |
| Expiration de session | BLOQUÉ | attente de 12 h non réalisée |
| Révocation multi-sessions | BLOQUÉ | pas de second compte |
| MFA | ÉCHOUÉ (P1) | admin connecté avec `mfa_enabled=false` |
| Code MFA faux / récupération double | BLOQUÉ | MFA non enrôlée |
| Rate limiting login | PARTIEL | emails invalides rejetés en 422 avant le limiteur |

## 4 bis. QA et production

Le backend QA et le backend production utilisent des variables `MONGO_URL` et
`DB_NAME` différentes. Les identifiants utilisateur et société identiques
observés lors de la connexion QA proviennent d'une **copie/clone de données**,
pas d'une base partagée.

Preuve lecture seule :

```text
production : 541 clients, 175 ventes
QA         : 542 clients, 176 ventes
```

Le QA est donc utilisable pour les tests, mais il ne contenait pas encore de
tenant QA dédié ni de comptes `TEST-AUDIT-`.

## 5. Matrice des rôles

| Rôle | Lecture | Création | Modification | Suppression | Export | URL directe | Statut |
|---|---|---|---|---|---|---|---|
| super-admin | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| admin | PARTIEL | NON TESTÉ | NON TESTÉ | NON TESTÉ | NON TESTÉ | RÉUSSI | seul rôle connecté |
| responsable | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| commercial A/B | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| technicien A/B | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| sous-traitant | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| comptable | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| prospecteur | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |
| responsable prospecteur | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | BLOQUÉ | pas de compte test |

Isolation société A/B et collègue A/B : **BLOQUÉ**, pas de second tenant de test.

## 6. Parcours métier

Le parcours complet n'a pas été exécuté : il exige des comptes de rôles et des données `TEST-AUDIT-` dans un environnement isolé. Les tests n'ont pas été simulés avec de vraies données.

| Étape | Résultat |
|---|---|
| Prospect → client | BLOQUÉ |
| Vente → CA → commission | BLOQUÉ |
| Vente → chantier → planning | PARTIEL — relations lues, pas de création |
| Affectation technicien | BLOQUÉ |
| Événement / photos | BLOQUÉ |
| Stock / réservation | BLOQUÉ |
| Fin de chantier → À encaisser | BLOQUÉ |
| Encaissement | BLOQUÉ |
| Rapport / objectif / commission | PARTIEL — lecture uniquement |
| Challenge impacté | BLOQUÉ |
| Journal d'audit | BLOQUÉ |
| Suppression / restauration test | BLOQUÉ |

## 7. Intégrité des données — lecture seule

```text
clients        541
ventes         175
chantiers       78
planning       122
commissions     94
```

Contrôles :

```text
vente → client manquant        : 0
chantier → client manquant     : 0
chantier → vente manquant      : 0
chantier sans vente            : 0
doublons d'identifiants        : 0
doublons vente → chantier      : 0
planning → client/vente manquant: 0
chantiers a_planifier avec date ISO réelle: 0
```

Le planning contient 44 chantiers de plus que la liste Chantiers : ce sont des chantiers dont la vente est fermée, volontairement masqués côté Kanban. Ce n'est pas un doublon.

## 8. Sécurité applicative

| Contrôle | Résultat |
|---|---|
| HSTS | OK |
| CSP | OK |
| X-Frame-Options: DENY | OK |
| X-Content-Type-Options: nosniff | OK |
| Referrer-Policy | OK |
| Permissions-Policy | OK |
| `/api/docs` exposé | NON |
| APIs sans session | 401 |
| Cookie HttpOnly/Secure/SameSite | OK |
| JWT dans localStorage | NON |
| IDOR inter-société | BLOQUÉ |
| Élévation de privilèges | BLOQUÉ |
| CSRF | PARTIEL — SameSite observé, pas de test hostile |
| CORS | NON TESTÉ |
| Rate limiting | PARTIEL |
| Secrets dans le dépôt | NON TESTÉ |
| Dépendances vulnérables | CI audit uniquement |
| Webhooks / cron | BLOQUÉ |

## 9. UI / responsive

Routes testées en Chromium, admin, 1440 et 390 px :

```text
/dashboard /ventes /clients /chantiers
/planning /stock /commissions /challenges
```

Résultat :

```text
débordement horizontal : 0
erreur JavaScript      : 0
```

La bannière MFA est visible sur mobile.

Non testés : Firefox, Safari, Edge, iPhone, Android, tablette, 320/375/768/1024/1920, zoom 200 %, lecteur d'écran, clavier seul, mode sombre complet.

## 10. Modules non validés

| Module | Statut | Raison |
|---|---|---|
| Stripe sandbox | BLOQUÉ | accès/configuration absents |
| Emails réels | BLOQUÉ | pas d'envoi autorisé |
| IA réelle | BLOQUÉ | pas de scénario isolé |
| Sauvegarde Atlas | BLOQUÉ | pas d'accès Atlas |
| Restauration | BLOQUÉ | pas de base séparée |
| Charge 10/50/100 utilisateurs | BLOQUÉ | pas d'outil de charge |
| Rollback Render | BLOQUÉ | pas d'accès Render |
| MFA admin | ÉCHOUÉ P1 | non enrôlée |

## 11. Anomalies

| ID | Gravité | Anomalie | Preuve | Recommandation |
|---|---|---|---|---|
| AUD-001 | P1 | MFA admin non enrôlée, connexion admin encore possible | `/api/auth/me` : `mfa_enabled=false`, `mfa_setup_required=true` | Enrôler la MFA avant toute commercialisation |
| AUD-002 | P1 | Rôles et isolation multi-sociétés non prouvés | aucun compte test | Fournir tenant QA + comptes `TEST-AUDIT-` |
| AUD-003 | P1 | Aucune restauration Atlas testée | pas d'accès | Restaurer dans une base séparée et comparer |
| AUD-004 | P1 | Safari/iPhone/Android non validés | Chromium uniquement | Test physique obligatoire |
| AUD-005 | P1 | Stripe/emails/IA non validés | pas d'accès | Sandbox + boîte test |
| AUD-006 | P1 | Parcours métier complet non exécuté | pas de données test | Exécuter 3 variantes sur tenant QA |
| AUD-007 | P2 | E2E interface utilise des API mockées | routes mockées | Ajouter E2E full-stack QA |
| AUD-008 | P2 | Dépôt HEAD `d37c872` ≠ version Render `bae0ce4` | docs uniquement | Aligner le déploiement documentaire |
| AUD-009 | P3 | Login email invalide → 422, pas 401 | test curl | Uniformiser le contrat d'erreur si souhaité |
| AUD-010 | P2 | Rate limiting non prouvé | 422 avant limiteur | Tester avec compte de test valide |

## 12. Données créées / supprimées

```text
Aucune donnée créée.
Aucune donnée modifiée.
Aucune donnée supprimée.
Aucun paiement, email ou fichier envoyé.
```

## 13. Plan de correction ordonné

1. Enrôler la MFA admin et vérifier la révocation des sessions.
2. Créer un tenant QA + comptes `TEST-AUDIT-` pour les 11 rôles.
3. Exécuter la matrice rôles / isolation société et collègue.
4. Exécuter les 3 parcours métier complets et nettoyer les données.
5. Restaurer Atlas dans une base séparée.
6. Valider Stripe sandbox, emails test, IA.
7. Tests physiques iPhone/Safari/Android/Firefox.
8. E2E full-stack sur QA.
9. Tests de charge.
10. Corriger les P2 restants et rejouer la recette.

## 14. Verdict

```text
PILOTE ACCOMPAGNÉ
```

Qylot n'est pas **PRÊT POUR PRODUCTION** ni **COMMERCIALISABLE SOUS CONDITIONS** à ce stade :
les P1 AUD-001 à AUD-006 ne sont pas fermés.

Le code et les tests automatisés sont verts, mais la recette de sécurité, de rôles, de restauration et de devices réels n'est pas prouvée.
