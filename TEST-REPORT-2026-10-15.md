# KYLOT — rapport de tests de la copie renforcée

Date : 15 octobre 2026

## Résultats

| Vérification | Résultat |
|---|---:|
| Compilation Python (`server.py`, `preflight.py`, `migrate.py`) | Réussie |
| Tests backend pré-vol, invariants, smoke et intégration | 39/39 réussis |
| Tests permissions frontend | 6/6 réussis |
| Build frontend production | Réussi |
| Audit dépendances Python publiques | 0 vulnérabilité connue |
| Audit dépendances Python de test | 0 vulnérabilité connue |
| Audit frontend runtime | 0 critique / 0 élevée / 0 modérée |
| Bandit backend | 0 moyenne / 0 élevée ; 38 faibles |
| Audit frontend complet avec outils de build | 11 élevées / 8 modérées, uniquement `braces` et `sprintf-js` dans CRA/Jest/Tailwind |

Les alertes Bandit faibles sont des faux positifs de valeurs comme `"0"`, des données de test et des exceptions volontairement tolérées dans des traitements secondaires. Elles ne constituent pas une validation absolue ; aucune alerte moyenne ou élevée n'a été trouvée.

## Parcours de sécurité exercés

- fermeture de l'inscription publique en production ;
- CORS limité à l'origine configurée ;
- en-têtes HSTS/CSP/nosniff de l'API ;
- isolation multi-société des clients, événements et stocks ;
- refus d'un participant/détenteur d'une autre société ;
- verrouillage après échecs de connexion ;
- révocation du token à la déconnexion ;
- refus d'un chantier hors scope appelé directement par son ID ;
- refus de suppression d'une vente hors scope ;
- refus d'une photo utilisant un schéma actif ;
- migration journalisée et non répétée ;
- invariants sur cookies HttpOnly, stockage local, file hors ligne, cron, Stripe et démarrage.

## Limites

Ces tests utilisent une base Mongo compatible en mémoire pour les scénarios d'intégration. Ils ne couvrent pas les comportements spécifiques d'un cluster MongoDB réel, les services privés Emergent, la délivrabilité email, les comptes Stripe réels ni le proxy de production.
