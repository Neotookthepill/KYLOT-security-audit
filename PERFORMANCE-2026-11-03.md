# KYLOT — mesures de performance locales

Date : 3 novembre 2026  
Environnement : `mongomock_motor` + `TestClient`, pas un MongoDB réel.  
Objectif : détecter les régressions de sérialisation et de requêtes, pas certifier la production.

## Jeu de données

- 5 000 clients
- 5 000 ventes
- 20 000 chantiers
- 5 000 entrées d'audit

## Commande

```bash
PYTHONPATH=. ./.venv/bin/python audit/performance_checks.py
```

Variables optionnelles : `PERF_CLIENTS`, `PERF_SALES`, `PERF_PROJECTS`, `PERF_AUDIT`.

## Résultats (médiane de 3 appels)

| Mesure | HTTP | Médiane |
|---|---:|---:|
| Clients, page 100 | 200 | 84 ms |
| Recherche clients | 200 | 195 ms |
| Compteurs catégories clients | 200 | 86 ms |
| Ventes, page 100 | 200 | 154 ms |
| Agrégats Ventes | 200 | 114 ms |
| Chantiers, page 100 | 200 | 1 045 ms |
| Audit, page 100 | 200 | 59 ms |

## Point corrigé

Avant la pagination avant enrichissement, `/api/projects?limit=100` chargeait
5 000 chantiers et prenait environ **4 700 ms**. La requête applique désormais
`skip/limit` avant l'enrichissement pour les scopes non technicien : environ
**1 045 ms** sur le même jeu simulé.

Le temps restant doit être remesuré sur MongoDB réel avec les index
`(company_id, created_at)` et une vraie latence réseau.

## Limites

- Les temps `mongomock` ne représentent pas MongoDB Atlas.
- Aucun test de charge concurrent (plusieurs workers, verrous, cache).
- Le payload réseau n'est pas mesuré.
- Les 20 000 chantiers ne sont pas tous chargés par l'API paginée ; les
  interfaces Planning/Kanban restent à raccorder.
