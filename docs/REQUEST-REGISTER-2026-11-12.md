# Registre des demandes — état au 12 novembre 2026

## Légende

```text
FAIT        codé, testé et disponible
LIVE        vérifié sur la production
PARTIEL     une partie seulement est couverte
NON FAIT    demandé, pas implémenté
À VALIDER   code présent, validation réelle manquante
```

## Sécurité / audit

| Demande | État | Preuve / limite |
|---|---|---|
| KIK’S respecte les permissions | FAIT | `76ea21e`, tests `test_kiks_rbac` |
| MFA admin obligatoire | PARTIEL | config active, admin non enrôlé, grâce au 19/11 |
| Code de récupération MFA à usage unique | FAIT | `$pull` atomique, test MFA |
| Budgets XLSX / PDF / images | FAIT | `test_file_bounds` |
| Journal d’audit minimisé et rétention | FAIT | `ccad208`, TTL 365 j |
| Stock : création technicien | FAIT | `test_tech_stock_create`, ajout réel |
| Stock : idempotence | FAIT | clé obligatoire, test rejeu |
| Stock : outbox / doublons | FAIT | index unique + dédoublonnage |
| Stock : ligne supprimée non modifiable | FAIT | `deleted_at`, test |
| Stock : renommage atomique | FAIT | outbox |
| Audit transactionnel complet des mouvements stock | PARTIEL | stock + mouvement atomiques ; audit séparé |

## Fonctionnalités demandées

| Demande | État | Preuve / limite |
|---|---|---|
| Commissions responsable réelles / reportées | FAIT | `Prospecteur.jsx`, `test_prospection` |
| Report automatique selon date chantier | FAIT | tests changement de date |
| Détail des commissions reportées | FAIT | tableau dédié |
| Challenge personnalisable | FAIT / LIVE | `ChallengeWidget`, `test_challenges` |
| Challenge de Noël 2026 | LIVE | actif, 5 participants, récompenses |
| Historique des challenges | FAIT | dialog + endpoint |
| Événement cliquable pour tous | FAIT | `EventDetailsDialog` |
| Édition événement réservée aux autorisés | FAIT | `canEdit` |
| Téléphones séparés par `/` | FAIT / À VALIDER | composant + test unitaire ; audit de tous les écrans à finir |
| Sélecteur client mobile clavier/scroll | FAIT / À VALIDER | `0a55f26`, test visuel mobile ; pas d’iPhone physique |

## P1 demandés

| Demande | État |
|---|---|
| Kanban paginé / progressif | NON FAIT |
| Recherche chantiers | NON FAIT |
| Filtres chantiers | PARTIEL (technicien seulement) |
| Onglets mobile chantiers | NON FAIT |
| Suppression dans menu secondaire | NON FAIT |
| Bulle assistance sans masquer les commandes | PARTIEL (padding ventes, autres écrans non audités) |
| Squelettes de chargement | PARTIEL (dashboard uniquement) |

## Dashboard / design

| Demande | État |
|---|---|
| Dashboard poste de pilotage | NON FAIT dans l’app |
| Trajectoire 12 mois réelle | NON FAIT (maquette seulement ; API sans série) |
| Rail urgences permanent | NON FAIT |
| Réduire les cartes / blocs vides | PARTIEL (carte commissions compactée) |
| Challenge résumé | NON FAIT |
| Cuivre logo uniquement | NON FAIT |
| Jade données / jaune alertes / rouge dangers | NON FAIT |
| Suppression des pastels SaaS | NON FAIT |
| Ventes : colonnes personnalisables | NON FAIT |
| Ventes : panneau latéral | NON FAIT |
| Ventes : moins de colonnes simultanées | NON FAIT |
| Ventes mobile en lignes | FAIT dans le code, déploiement front à confirmer |
| Prospecteur : mois de commission immédiat | FAIT dans le code, déploiement front à confirmer |

## Opérations / production

| Demande | État |
|---|---|
| Nettoyage objets QA | NON FAIT |
| Backup Atlas + restauration testée | NON FAIT |
| Stripe sandbox | NON FAIT |
| Emails réels | NON FAIT |
| Test iPhone réel | NON FAIT |
| Playwright E2E dans CI | NON FAIT |
| MFA admin enrôlée | NON FAIT |

## Versions

```text
Production backend  : 31060aa
Production frontend : main.932f8beb.js
Dernier commit      : 0a55f26
```

Le frontend de production ne contient pas encore toutes les dernières
corrections (liste mobile ventes / mois prospect / sélecteur client).
