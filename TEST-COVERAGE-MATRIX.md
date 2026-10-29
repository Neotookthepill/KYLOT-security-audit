# KYLOT — matrice initiale de couverture

Cette matrice distingue les contrôles automatiques actuels des validations qui
exigent une véritable préproduction. Elle doit être complétée à chaque anomalie
et avant toute refactorisation d'un domaine.

| Domaine | Règle protégée | Preuve actuelle | Environnement | Manque principal |
|---|---|---|---|---|
| Authentification | session révoquée, compte désactivé, inscription fermée | `backend/test_integration_security.py`, tests de fumée | Mongo simulée | proxy, cookies et révocation multi-processus |
| Multi-tenant | injection et filtrage de `company_id` | intégration et suites adversariales | Mongo simulée | deux entreprises sur MongoDB réelle |
| Autorisations | routes privées refusées sans session, portées `own` | inventaire des routes et tests IDOR | application locale | matrice complète de chaque rôle |
| Chantiers | accès direct, modification, suppression et confirmation bornés | tests d'intégration sécurité | Mongo simulée | parcours mobile et concurrence réelle |
| Ventes | suppression hors périmètre refusée | tests d'intégration sécurité | Mongo simulée | transitions de statut et cas historiques |
| Stock | utilisateurs tenantés et opérations bornées | intégration et fuzzing métier | Mongo simulée | transferts simultanés sur MongoDB réelle |
| Hors ligne | cache cloisonné, purge d'identité, replay limité | tests Jest `offline.test.js` | navigateur simulé | téléphone réel, coupures et conflits |
| Imports | limites de taille et entrées hostiles | modèles, fuzzing et tests historiques | local/simulé | PDF, CSV, Excel réels et volumes représentatifs |
| Stripe | signature, idempotence et états applicatifs | tests unitaires et invariants | simulé | sandbox, remboursement, litige et résiliation |
| Email et cron | secret et déduplication applicative | invariants et tests ciblés | simulé | fournisseur réel, délivrabilité et concurrence |
| IA | limites, opt-in et actions bornées | suites hostiles et modèles | fournisseur simulé | fournisseur réel, injection, coûts et délais |
| Migrations | verrou, reprise et journalisation | tests d'intégration | Mongo simulée | copie réaliste, interruption et retour arrière |
| Sauvegarde | procédure documentée | `DEPLOYMENT.md` | non exécuté | restauration complète chronométrée |
| Frontend | auth, API, permissions et hors ligne | 23 tests Jest documentés | jsdom | navigateur réel, mobile et accessibilité |

## Règle de modification

Avant d'extraire une partie de `backend/server.py`, chaque règle métier du
domaine concerné doit avoir au moins un test de caractérisation et un résultat
attendu compréhensible par le propriétaire du produit.
