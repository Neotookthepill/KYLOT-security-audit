# KYLOT — matrice d'autorisation et de portée

Date : 16 octobre 2026  
Source de vérité inspectée : `DEFAULT_PERMISSIONS`, `get_current_user`, `require_*`, `check_perm`, `cq`, `_own_sales_filter` et `_ensure_project_scope` dans `backend/server.py`.

Cette matrice décrit le comportement attendu visible dans le code. Elle ne prétend pas que chaque cellule a été testée dynamiquement : les colonnes « preuve » distinguent précisément les contrôles exécutés des contrôles encore nécessaires sur staging.

## Légende

- `R/C/U/D` : lire, créer, modifier, supprimer.
- `own` : uniquement ses données ou ses affectations.
- `all` : toutes les données de sa société, jamais celles d'une autre société.
- `—` : refus par défaut.
- Les permissions enregistrées sur un utilisateur peuvent préciser le défaut, sauf les règles critiques forcées par le serveur.

## Matrice des permissions par défaut

| Rôle | Ventes | Clients | Chantiers | Planning | Commissions | Heures sup. | Rapports | Utilisateurs | Paramètres | Finance | Photos | Stock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| admin | RCUD all | RCUD all | RCUD all | RU all | RU all | RCUD/valider all | R | gérer | modifier | R | RU | RU all |
| responsable | RCUD all | RCU all | RCU all | RU all | RU all | RU/valider all | R | — | — | — | RU | RU all |
| commercial | R own | RCU own | R own | R own | R own | — | — | — | — | — | R | — |
| technicien | — | — | RU own | RU own | — | RC/U own si éligible | — | — | — | — | RU | R own/autres/société ; U refusé par défaut |
| sous_traitant | — | — | RU own | RU own | — | — | — | — | — | — | RU | — |
| comptable | R all | R all | R all | R all | RU all | R all | R | — | — | R | R | R all |
| prospecteur | — | — | — | — | — | — | — | — | — | — | — | — |
| responsable_prospecteur | mêmes défauts que prospecteur | — | — | — | — | — | — | — | — | — | — | — |
| super_admin | uniquement auth, `/superadmin/*` et `/company/me` | — | — | — | — | — | — | gestion plateformes | — | — | — | — |

### Règles forcées côté serveur

- Un `commercial` est forcé en lecture seule sur ventes et commissions même si d'anciennes permissions en base disent le contraire.
- Un `responsable` est forcé en accès complet société sur ventes et commissions.
- Un `technicien` ne conserve ses droits d'heures supplémentaires que si un `team_member` éligible lui est associé.
- Un abonnement `suspended` bloque les routes métier et laisse seulement l'authentification, la régularisation et quelques informations de compte.
- Un `super_admin` ne peut pas utiliser les routes métier ordinaires ; le middleware le limite aux routes plateforme.

## Portée attendue : soi, collègue, autre société

| Ressource | Ses propres données | Données d'un collègue de la même société | Données d'une autre société | Preuve locale |
|---|---|---|---|---|
| ventes | selon scope `own/all` | seulement `all` ou droits manager | toujours refusées/404 | tests IDOR et filtres `company_id`; historiques homonymes encore signalés |
| clients | reliés à ses ventes pour scope `own` | managers/all | toujours refusés/404 | tests IDOR principaux ; note en écriture incohérente CA3-09 |
| chantiers | affectation propre pour technicien/sous-traitant | managers/all | toujours refusés/404 | tests de scope ; matching fuzzy/homonymes déjà signalé |
| planning | propre affectation ou `all` | selon portée | toujours refusé | contrôle statique + tests partiels |
| commissions | propre commercial ou `all` | managers/comptable | toujours refusées | tests partiels ; historique legacy à revoir |
| heures sup. | propres déclarations si éligible | validation manager | toujours refusées | tests antérieurs ; homonymes déjà signalés |
| photos | photos de chantier autorisé | selon accès chantier | toujours refusées | taille/type testés ; magic bytes restant déjà signalé |
| stock | selon flags `view_own/view_others/view_company` | selon flags | toujours refusé | ajustement arbitraire déjà signalé dans la passe 2 |
| équipe/primes/paramètres | pas de notion `own` générale | managers selon route | toujours filtrés par société attendu | divulgations secondaires et audit incomplet signalés |
| IA | contexte permis à l'utilisateur | ne doit jamais élargir les droits | jamais de contexte inter-société | actions serveur partiellement testées ; fuite locale CA3-03 |
| imports/exports | société courante | selon permission | jamais autre société | imports bornage absent CA3-05 ; CSV actif déjà signalé |

## Matrice CRUD/export par famille secondaire

Ces ressources ne disposent pas toutes d'une entrée dédiée dans `DEFAULT_PERMISSIONS`; les routes combinent rôle, statut manager et permissions génériques. C'est précisément une dette de lisibilité à corriger.

| Famille | Lecture | Création | Modification | Suppression | Export | Décision observée / risque |
|---|---|---|---|---|---|---|
| équipe | tout compte connecté, avec filtre partiel commercial | admin | admin | admin | — | lecture technicien trop large déjà signalée ; mutations sans audit |
| primes | tout compte connecté | manager | manager | manager | — | détails visibles trop largement déjà signalés |
| jours OFF | tout compte connecté | selon logique route | selon logique route | selon logique route | — | confidentialité déjà signalée passe 2 |
| événements | session | session selon route | session selon route | session selon route | — | dates/heures invalides déjà signalées |
| notifications | utilisateur/société | actions système | état propre | état propre | — | campagne E2E encore requise |
| prospects/prospection | routes dédiées, contrôle hétérogène | selon route | contrôle parfois absent visiblement | selon route | — | à fermer par permission explicite |
| statuts de vente | session | via remplacement | permission | via réaffectation | — | usage agrégé trop visible déjà signalé |
| mémoire/corrections IA | lecture hétérogène | manager pour mémoire | manager | manager | — | `GET /ai/memory` mérite permission explicite |
| audit log | admin/manager selon route | système | — | — | selon route | couverture d'écriture incomplète CA3-08 |
| abonnement/paiement | compte/admin selon route | admin | webhooks signés | fournisseur | — | validation Stripe externe requise |
| société | compte/admin/super-admin | super-admin | admin/super-admin | super-admin | — | staging multi-tenant requis |
| configuration tableau de bord | propre utilisateur | propre utilisateur | propre utilisateur | propre utilisateur | — | correctement orienté propriétaire dans l'inventaire statique |

## État du compte et session

| État | Accès serveur attendu | Données locales attendues | Couverture |
|---|---|---|---|
| actif | selon rôle/permissions | partitionnées par utilisateur/société | parcours normaux testés |
| désactivé | `401/403`, aucune route métier | purge au prochain contrôle | protection serveur/offline antérieure ; E2E staging requis |
| supprimé | `401`, utilisateur introuvable | purge immédiate dès `401` | purge automatique absente CA3-04 |
| mot de passe changé | anciennes sessions révoquées | purge après refus | révocation déjà signalée dans audit précédent |
| logout explicite | cookie révoqué | IndexedDB + brouillons supprimés | IndexedDB oui ; `sessionStorage` non, CA3-03 |
| cookie expiré | `401` | toutes données sensibles purgées | redirection oui ; purge non, CA3-04 |
| abonnement suspendu | uniquement auth/paiement/compte | lecture locale à neutraliser | gate serveur visible ; E2E offline requis |

## Couverture dynamique et manque restant

Les tests locaux ont confirmé des contrôles inter-sociétés sur les ressources principales, des scopes propres, la désactivation, le logout, plusieurs opérations de vente/chantier et les scénarios adversariaux des trois campagnes.

La preuve exhaustive exige encore, sur staging, un jeu de comptes représentant chaque rôle dans deux sociétés et l'exécution de chaque route de `ROUTE-INVENTORY-2026-10-16.md` avec :

1. identifiant propre ;
2. identifiant d'un collègue ;
3. identifiant de l'autre société ;
4. compte actif, désactivé, supprimé, mot de passe changé et cookie expiré ;
5. chaque méthode disponible : lecture, création, modification, suppression et export.

Tant que cette campagne n'est pas automatisée, la matrice est une spécification vérifiable et non une certification complète.

