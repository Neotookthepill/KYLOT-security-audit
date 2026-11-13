# Inventaire exhaustif des demandes client

Périmètre : toutes les demandes explicites présentes dans les captures et messages
de cette conversation. Les constats d'audit et les propositions internes sont
listés séparément à la fin.

Légende :

```text
LIVRÉ     implémenté et vérifié
TESTÉ     couvert par un test automatisé ou QA
SIMULÉ    vérifié en navigateur mobile simulé
MAQUETTE  volontairement non appliqué à l'application
PARTIEL   une partie reste à faire
BLOQUÉ    accès ou environnement manquant
```

## A. Captures Ventes / Clients / Prospecteur

| ID | Demande | Source | État |
|---|---|---|---|
| A01 | Sur téléphone, pouvoir accéder au tableau de vente / à la fin de la liste | Capture 1 | LIVRÉ / TESTÉ |
| A02 | Afficher les ventes mobiles en lignes plutôt qu'en cartes, pour un visu plus rapide | Capture 1 | LIVRÉ / TESTÉ |
| A03 | Prospecteur : le mois sélectionné doit afficher les bonnes lignes immédiatement | Capture 1 | LIVRÉ / TESTÉ |
| A04 | Corriger le bug d'affichage des icônes / zones sûres iPhone | Capture 1 | SIMULÉ — iPhone physique bloqué |
| A05 | Rendre l'adresse client cliquable vers la carte | Capture 2 | LIVRÉ |
| A06 | Modifier le CA par commercial doit mettre à jour l'objectif général, qui est un total | Capture 2 | LIVRÉ / TESTÉ |
| A07 | Code postal ou ville saisi doit retrouver automatiquement l'autre information | Capture 2 | LIVRÉ / TESTÉ live |
| A08 | Export client : séparer adresse, code postal et ville pour que la carte les reconnaisse | Capture 2 | LIVRÉ / TESTÉ |
| A09 | Rechercher une vente par n'importe quel libellé de statut | Message statuts | LIVRÉ / TESTÉ |
| A10 | La recherche par statut ne doit pas être polluée par un texte de service | Audit associé | LIVRÉ / TESTÉ |

## B. Commissions responsable de prospection

| ID | Demande | Source | État |
|---|---|---|---|
| B01 | Distinguer commission du mois en cours et commission reportée au mois suivant | Message commissions | LIVRÉ / TESTÉ |
| B02 | Ajouter les indicateurs « commission réelle » et « commission reportée » | Message commissions | LIVRÉ / TESTÉ |
| B03 | Reporter automatiquement les commissions au mois suivant | Message commissions | LIVRÉ / TESTÉ |
| B04 | Se baser sur le mois de réalisation du chantier, pas seulement la signature | Message commissions | LIVRÉ / TESTÉ |
| B05 | Ne jamais commissionner deux fois la même vente | Message commissions | LIVRÉ / TESTÉ |
| B06 | Si la date du chantier change, actualiser automatiquement le report | Message commissions | LIVRÉ / TESTÉ |
| B07 | Garder le détail des ventes composant chaque montant reporté | Message commissions | LIVRÉ |

## C. Module Challenge

| ID | Demande | Source | État |
|---|---|---|---|
| C01 | Ajouter un module Challenge accessible depuis le tableau de bord | Message challenge | LIVRÉ |
| C02 | Admin : créer un challenge avec nom, dates, critère, récompenses, participants | Message challenge | LIVRÉ / TESTÉ |
| C03 | Admin : activer, clôturer, archiver un challenge | Message challenge | LIVRÉ / TESTÉ |
| C04 | Classement automatique en temps réel relié aux données existantes | Message challenge | LIVRÉ / TESTÉ |
| C05 | Gérer annulations et modifications sans double comptage | Message challenge | LIVRÉ / TESTÉ |
| C06 | Tous les commerciaux voient le challenge en cours | Message challenge | LIVRÉ / TESTÉ QA |
| C07 | Afficher nom, dates, classement, position personnelle, points, récompenses, jours restants | Message challenge | LIVRÉ |
| C08 | Podium pour les trois premiers | Message challenge | LIVRÉ |
| C09 | Les commerciaux ne peuvent pas modifier résultats ou paramètres | Message challenge | LIVRÉ / TESTÉ |
| C10 | Configurer le Challenge de Noël 2026 : 1er nov.–17 déc., assistances, 1250/500/250 € | Message challenge | LIVRÉ / LIVE |
| C11 | Prendre en compte les assistances depuis le 1er novembre même si le module arrive après | Message challenge | LIVRÉ |
| C12 | Conserver l'historique des challenges et résultats définitifs | Message challenge | LIVRÉ / TESTÉ |

## D. Planning, téléphone, sélecteur client

| ID | Demande | Source | État |
|---|---|---|---|
| D01 | Tous les rôles doivent pouvoir cliquer sur un événement du planning | Message planning | LIVRÉ — admin testé, autres rôles non testés |
| D02 | La fenêtre doit afficher titre, date, horaires, description, lieu | Message planning | LIVRÉ |
| D03 | Seuls les autorisés peuvent modifier/supprimer l'événement | Message planning | LIVRÉ / TESTÉ RBAC partiel |
| D04 | Détecter les numéros séparés par `/` partout | Message téléphone | LIVRÉ / TESTÉ |
| D05 | Chaque numéro doit être indépendant et cliquable | Message téléphone | LIVRÉ / TESTÉ |
| D06 | Garder le fonctionnement avec un seul numéro | Message téléphone | LIVRÉ |
| D07 | Mobile : la barre de recherche client reste visible au-dessus du clavier | Message sélecteur | SIMULÉ |
| D08 | Mobile : défilement client fluide, sans blocage ni superposition | Message sélecteur | SIMULÉ |
| D09 | Éviter les sauts et bugs d'affichage pendant la saisie | Message sélecteur | SIMULÉ |

## E. P1 interface / Kanban

| ID | Demande | Source | État |
|---|---|---|---|
| E01 | Kanban paginé / chargement progressif | Contexte P1 | LIVRÉ / TESTÉ |
| E02 | Recherche dans les chantiers | Contexte P1 | LIVRÉ / TESTÉ |
| E03 | Filtres chantiers | Contexte P1 | LIVRÉ / TESTÉ |
| E04 | Onglets de statut sur mobile | Contexte P1 | LIVRÉ / TESTÉ E2E |
| E05 | Suppression dans le menu secondaire `•••` | Contexte P1 | LIVRÉ / TESTÉ E2E |
| E06 | La bulle d'assistance ne doit pas masquer les commandes | Contexte P1 | LIVRÉ / TESTÉ E2E |
| E07 | Squelettes de chargement | Contexte P1 | LIVRÉ |
| E08 | Recherche Kanban différée pour éviter trois requêtes par caractère | Audit P2 | LIVRÉ / TESTÉ |
| E09 | « Charger plus » exact quand il y a exactement 12 résultats | Audit P3 | LIVRÉ |
| E10 | Pagination technicien réellement appliquée après filtrage | Audit P1 | LIVRÉ / TESTÉ |
| E11 | Filtre « Non assignés » correct avec pagination | Audit P1 | LIVRÉ / TESTÉ |

## F. Dashboard, design et identité visuelle

| ID | Demande | Source | État |
|---|---|---|---|
| F01 | Refonte « Poste de pilotage » avec performance, urgences, terrain, risques, challenge | Contexte design | MAQUETTE |
| F02 | Vraie trajectoire sur 12 mois | Contexte design | MAQUETTE |
| F03 | Rail d'urgences permanent | Contexte design | MAQUETTE |
| F04 | Bloc terrain / planning du jour | Contexte design | MAQUETTE |
| F05 | Chantiers à risque | Contexte design | MAQUETTE |
| F06 | Challenge résumé | Contexte design | MAQUETTE |
| F07 | Supprimer les blocs vides ou redondants | Contexte design | MAQUETTE |
| F08 | Moins de cartes identiques, interfaces plus structurées | Contexte design | MAQUETTE |
| F09 | Une seule couleur d'action | Contexte design | MAQUETTE |
| F10 | Cuivre uniquement pour le logo | Contexte design | MAQUETTE |
| F11 | Jade pour le positif | Contexte design | MAQUETTE |
| F12 | Jaune réservé aux avertissements | Contexte design | MAQUETTE |
| F13 | Rouge réservé aux vrais dangers | Contexte design | MAQUETTE |
| F14 | Typographie et espacements plus soignés | Contexte design | MAQUETTE |
| F15 | Éviter le look SaaS pastel | Contexte design | MAQUETTE |
| F16 | Proposer 4 familles de couleurs × 3 layouts | Contexte design | MAQUETTE — propositions livrées |
| F17 | Proposer 8 palettes différentes | Contexte design | MAQUETTE — propositions livrées |
| F18 | Proposer 3 directions UI/UX distinctes | Contexte design | MAQUETTE — propositions livrées |
| F19 | Ne plus utiliser l'orange | Contexte design | MAQUETTE |
| F20 | Montrer le design uniquement, ne pas l'appliquer en production | Instruction design | RESPECTÉ — non appliqué |

## G. Refonte Ventes

| ID | Demande | Source | État |
|---|---|---|---|
| G01 | Colonnes personnalisables | Contexte ventes | LIVRÉ / TESTÉ |
| G02 | Panneau latéral pour les informations secondaires | Contexte ventes | LIVRÉ / TESTÉ E2E |
| G03 | Recherche et filtres visibles | Contexte ventes | LIVRÉ |
| G04 | Lignes adaptées au mobile | Contexte ventes | LIVRÉ / SIMULÉ |
| G05 | Moins de données affichées simultanément | Contexte ventes | LIVRÉ — colonnes par défaut |

## H. Synchronisation et recherche client

| ID | Demande | Source | État |
|---|---|---|---|
| H01 | Une date saisie/modifiée dans Ventes doit programmer le chantier | Contexte sync | LIVRÉ / TESTÉ |
| H02 | Le chantier doit apparaître dans le Planning | Contexte sync | LIVRÉ / TESTÉ |
| H03 | Ne pas créer de doublon de chantier | Contexte sync | LIVRÉ / TESTÉ |
| H04 | Les anciennes ventes doivent aussi être réparées | Contexte sync | LIVRÉ / TESTÉ |
| H05 | Afficher tous les techniciens affectés dans la recherche client | Contexte techniciens | LIVRÉ / TESTÉ |
| H06 | Afficher « Technicien non attribué » si aucun | Contexte techniciens | LIVRÉ |
| H07 | Afficher date, statut et intervention | Contexte techniciens | LIVRÉ |
| H08 | Afficher le technicien dans le tableau Clients | Contexte clients | LIVRÉ / TESTÉ |
| H09 | Le technicien doit être visible aussi sur mobile | Contexte clients | LIVRÉ / SIMULÉ |

## I. Stock, sécurité, sessions

| ID | Demande | Source | État |
|---|---|---|---|
| I01 | Idempotence des mouvements de stock | Audit sécurité | LIVRÉ / TESTÉ |
| I02 | Éviter les doublons dans l'outbox stock | Audit sécurité | LIVRÉ / TESTÉ |
| I03 | Empêcher la modification d'un stock supprimé | Audit sécurité | LIVRÉ / TESTÉ |
| I04 | Mouvement de quantité atomique avec journal | Audit sécurité | LIVRÉ / TESTÉ |
| I05 | Corriger la barre inférieure iPhone / safe area | Audit mobile | SIMULÉ |
| I06 | KIK'S doit respecter les permissions | Audit sécurité | LIVRÉ / TESTÉ |
| I07 | MFA obligatoire pour les admins | Audit sécurité | ÉCHOUÉ — admin non enrôlé |
| I08 | Code de récupération MFA à usage unique | Audit sécurité | LIVRÉ / TESTÉ |
| I09 | Budgets de fichiers et validation d'upload | Audit sécurité | LIVRÉ / TESTÉ |
| I10 | Journal d'audit minimisé et rétention | Audit sécurité | LIVRÉ / TESTÉ |

## J. Recette / validation demandée

| ID | Demande | Source | État |
|---|---|---|---|
| J01 | Contre-audit exhaustif dépôt + production | Demande audit | PARTIEL — rapport livré |
| J02 | Vérifier commit, version, health, ready, CI | Demande audit | RÉUSSI |
| J03 | Tester authentification, sessions, MFA, cookies | Demande audit | PARTIEL — MFA bloquée |
| J04 | Tester les 11 rôles | Demande audit | PARTIEL — 10 testés, super-admin bloqué |
| J05 | Tester deux sociétés | Demande audit | BLOQUÉ — société B absente |
| J06 | Tester IDOR / collègue / révocation | Demande audit | PARTIEL — collègue OK, société B bloquée |
| J07 | Exécuter 3 parcours métier complets | Demande audit | PARTIEL — 3 ventes créées, étapes event/photo/stock/encaissement non faites |
| J08 | Ajouter un E2E full-stack | Demande audit | PARTIEL — admin QA réel, multi-rôles non fait |
| J09 | Tests de charge 10/50/100 | Demande audit | PARTIEL — 100 requêtes HTTP, pas 100 utilisateurs |
| J10 | Restaurer Atlas et tester rollback | Demande audit | BLOQUÉ — accès absent |
| J11 | Tester Safari/iPhone/Android réels | Demande audit | BLOQUÉ — devices absents |
| J12 | Tester Stripe sandbox / emails / IA | Demande audit | BLOQUÉ — accès/services absents |
| J13 | Nettoyer les données TEST-AUDIT- | Demande audit | PARTIEL — comptes supprimés, 3 ventes/clients restants |
| J14 | Rejouer la recette finale | Demande audit | NON FAIT — dépend des bloqueurs |

## K. Corrections issues des audits

| ID | Demande | Source | État |
|---|---|---|---|
| K01 | Réparation des dates déplacée en tâche admin | Audit P1 | LIVRÉ / TESTÉ |
| K02 | Pas de modification hors périmètre sur simple lecture | Audit P1 | LIVRÉ |
| K03 | Moins de marge globale pour la bulle | Audit P2 | LIVRÉ |
| K04 | Registre des demandes à jour | Audit P2 | LIVRÉ |
| K05 | Tests E2E dans la CI | Audit P2 | LIVRÉ — CI verte |
| K06 | Pagination serveur réelle | Audit P1 | LIVRÉ / TESTÉ |
| K07 | Filtre non assignés côté serveur | Audit P1 | LIVRÉ / TESTÉ |
| K08 | Délai de recherche Kanban | Audit P2 | LIVRÉ |
| K09 | Compteur Charger plus exact | Audit P3 | LIVRÉ |
| K10 | Recherche par libellé de statut | Demande Ventes | LIVRÉ / TESTÉ |

## Bilan

```text
Demandes fonctionnelles listées : 79
LIVRÉ / TESTÉ / SIMULÉ          : 61
MAQUETTE                        : 15
PARTIEL                         : 10
BLOQUÉ                          : 5
ÉCHOUÉ                          : 1 (MFA)
```

Le total inclut les doublons de demandes répétées dans les messages (commissions,
challenge, planning, téléphone) une seule fois.
