# Analyse des demandes reçues — 13 novembre 2026

## Légende

```text
LIVRÉ       fonctionne dans le code et en production
TESTÉ       couvert par un test automatisé
SIMULÉ      vérifié dans Chromium mobile simulé
MAQUETTE    volontairement hors application
PARTIEL     une partie reste à faire
NON FAIT    identifié mais non livré
HORS CODE   action humaine / infrastructure / décision
```

## P1 — Interface et Kanban

| Demande | État |
|---|---|
| Kanban paginé / chargé progressivement | LIVRÉ / TESTÉ — 12 cartes puis `Charger plus`, pagination serveur |
| Pagination technicien réellement appliquée après affectation | LIVRÉ / TESTÉ |
| Filtre « Non assignés » correct avec pagination | LIVRÉ / TESTÉ — filtre serveur `assigned=__none` |
| Recherche chantiers | LIVRÉ / TESTÉ |
| Filtres chantiers (technicien, priorité, statut) | LIVRÉ / TESTÉ |
| Onglets mobile À planifier / Programmé / À encaisser | LIVRÉ / TESTÉ E2E |
| Suppression dans menu secondaire ••• | LIVRÉ / TESTÉ E2E |
| Squelettes de chargement Kanban | LIVRÉ |
| Bulle d'assistance sans masquer les commandes | LIVRÉ — assistant déplacé dans la barre mobile |
| Délai de recherche Kanban | LIVRÉ — 300 ms |
| Bouton « Charger plus » exact | LIVRÉ — requête `limit=13` |

## Ventes

| Demande | État |
|---|---|
| Recherche par tous les libellés de statut | LIVRÉ / TESTÉ — labels + codes + accents |
| Ne pas mélanger un statut avec un texte de service | LIVRÉ / TESTÉ — ex. « En cours », « PROG » |
| Recherche par nom client, téléphone, BDC, service, commercial, source | LIVRÉ |
| Ventes mobile en lignes compactes | LIVRÉ / TESTÉ SIMULÉ |
| Pagination mobile conservée | LIVRÉ |
| Colonnes personnalisables | LIVRÉ / TESTÉ |
| Préférence de colonnes par utilisateur | LIVRÉ — localStorage |
| Panneau latéral des informations secondaires | LIVRÉ / TESTÉ E2E |
| Moins de colonnes visibles par défaut | LIVRÉ — téléphone, BDC, source masqués |
| Fiche adaptée au mobile | LIVRÉ |

## Clients / adresses / téléphone

| Demande | État |
|---|---|
| Adresse cliquable → Maps | LIVRÉ |
| Code postal → ville automatique | LIVRÉ / TESTÉ live |
| Ville → code postal automatique | LIVRÉ / TESTÉ live |
| Téléphones séparés par `/` | LIVRÉ / TESTÉ |
| Chaque numéro cliquable indépendamment | LIVRÉ / TESTÉ |
| Technicien dans la recherche globale | LIVRÉ / TESTÉ live |
| Technicien dans le tableau Clients | LIVRÉ / TESTÉ |
| « Technicien non attribué » si aucun | LIVRÉ |
| Export clients : adresse / CP / ville séparés | LIVRÉ / TESTÉ |
| Import avec adresse, CP, ville distincts | LIVRÉ / TESTÉ |
| Objectif général = somme des objectifs commerciaux | LIVRÉ / TESTÉ live |

## Prospection / commissions

| Demande | État |
|---|---|
| Commission responsable réelle du mois | LIVRÉ / TESTÉ |
| Commission responsable reportée | LIVRÉ / TESTÉ |
| Report basé sur le mois du chantier | LIVRÉ / TESTÉ |
| Report automatique au mois suivant | LIVRÉ / TESTÉ |
| Modification de date → mise à jour du report | LIVRÉ / TESTÉ |
| Éviter une double commission | LIVRÉ / TESTÉ |
| Détail des ventes reportées | LIVRÉ |
| Sélecteur de mois immédiatement actualisé | LIVRÉ / TESTÉ |

## Challenge

| Demande | État |
|---|---|
| Création/paramétrage admin | LIVRÉ / TESTÉ |
| Nom, dates, critère, récompenses, participants | LIVRÉ / TESTÉ |
| Classement temps réel | LIVRÉ / TESTÉ |
| Podium et position personnelle | LIVRÉ |
| Consultation par les commerciaux | LIVRÉ |
| Interdiction de modifier les résultats | LIVRÉ / TESTÉ RBAC |
| Challenge de Noël 2026 | LIVE — actif |
| Historique des challenges | LIVRÉ / TESTÉ |

## Planning / événements

| Demande | État |
|---|---|
| Événement cliquable pour tous les rôles | LIVRÉ / TESTÉ navigateur |
| Titre, date, horaires, description, lieu | LIVRÉ |
| Modification réservée aux autorisés | LIVRÉ |

## Sécurité / stock / audit

| Demande | État |
|---|---|
| KIK'S respecte les permissions | LIVRÉ / TESTÉ |
| MFA obligatoire pour les admins | CONFIGURÉ — admin non enrôlé |
| Code de récupération MFA à usage unique | LIVRÉ / TESTÉ |
| Budgets XLSX / PDF / images | LIVRÉ / TESTÉ |
| Journal d'audit minimisé + rétention | LIVRÉ |
| Stock idempotent | LIVRÉ / TESTÉ |
| Mouvement stock atomique / outbox | LIVRÉ / TESTÉ |
| Stock supprimé non modifiable | LIVRÉ / TESTÉ |
| Réparation des anciens chantiers | LIVRÉ — tâche admin explicite |
| Synchronisation vente → chantier → planning | LIVRÉ / TESTÉ live |
| Pas de doublon de chantier | LIVRÉ / TESTÉ |
| Ventes existantes réparées | LIVRÉ — production vérifiée |

## Mobile / PWA

| Demande | État |
|---|---|
| Safe area iPhone / barre inférieure | SIMULÉ — Chromium, safe area 34 px |
| Sélecteur client : clavier, recherche visible, scroll | SIMULÉ |
| iPhone physique / Safari réel / PWA installée | NON VALIDÉ |

## Design et maquettes

| Demande | État |
|---|---|
| 4 couleurs × 3 layouts | MAQUETTE |
| 8 directions couleur | MAQUETTE |
| 3 concepts UI/UX | MAQUETTE |
| « Poste de pilotage » | MAQUETTE — non appliqué à l'app |
| Système visuel navy / ivoire / jade / cuivre logo | NON APPLIQUÉ |
| Ventes : colonnes / panneau | APPLIQUÉ DANS L'APP |

## Ce qui reste ouvert

```text
MFA admin non enrôlée
test iPhone/Safari/PWA physique
nettoyage des objets QA
backup/restauration Atlas
Stripe sandbox, emails réels
application du design « Poste de pilotage » si le client la valide
```

## Validation technique

```text
backend : 117 tests avant la dernière passe
frontend : 47 tests
E2E P1 : dans la CI, vert
CI : verte
production : bae0ce4 au dernier contrôle
```

## Conclusion

Toutes les demandes fonctionnelles explicites présentes dans les messages et captures
sont couvertes, sauf la validation physique iPhone et les opérations externes.
Le design reste une maquette volontairement non appliquée.
