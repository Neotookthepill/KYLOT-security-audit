# KYLOT — validation étendue du 19 octobre 2026

## Ce qui a été fait

Cette passe complète les trois audits adversariaux précédents sans toucher au design :

- simulation de deux entreprises et de plusieurs rôles sur les accès directs, les listes et les modifications ;
- tests de sessions expirées, comptes suspendus ou supprimés, JWT malformés et déconnexion rejouée ;
- envoi de textes démesurés, collections trop longues, champs inconnus et fausses images ;
- contrôles locaux d'import, d'export et d'isolation avec plusieurs milliers d'objets ;
- ajout permanent des nouvelles suites dans la CI.

## Problème supplémentaire trouvé et corrigé

Des champs métier importants n'avaient pas tous une limite explicite. Un utilisateur autorisé pouvait donc envoyer des textes ou listes inutilement énormes, avec un risque de gonflement de la base, de mémoire excessive et de ralentissement. Les principaux champs clients, ventes, chantiers, équipe, prospects, absences, événements et stock sont maintenant bornés avant stockage.

Le logo enregistré dans les paramètres ne passait pas non plus par le validateur renforcé des images. Il utilise maintenant le même contrôle de taille, de signature réelle et de source HTTPS autorisée que les photos métier.

## Résultats vérifiés

- 54 scénarios adversariaux historiques : réussis ;
- 10 groupes multi-rôles/multi-entreprises, couvrant 62 appels : réussis ;
- 8 groupes d'entrées hostiles et sessions : réussis ;
- 4 groupes de volume borné : réussis ;
- 33 groupes d'inventaire des routes, d'intégrité métier, de paiement, d'authentification et de fuzzing structuré : réussis ;
- 40 tests serveur standards : réussis ;
- 23 tests interface : réussis ;
- total : **172 tests automatisés réussis** (109 sécurité/robustesse, 40 serveur, 23 interface) ;
- build frontend de production : réussi ;
- analyse Bandit du serveur : aucun constat après qualification des faux positifs ;
- audits de dépendances déjà réalisés : aucune vulnérabilité connue dans les environnements installés et audités.

Couverture observée : 21 % des instructions du serveur par la suite serveur standard et 3,11 % des lignes du frontend. Les 487 tests HTTP historiques ont été collectés, mais ne peuvent être exécutés honnêtement sans staging, MongoDB réel, données de recette, comptes de test et intégrations sandbox.

Mesures locales indicatives sur base en mémoire : import de 1 000 clients en 1,24 s, export en flux de 5 000 ventes en 0,37 s et liste isolée de 5 000 clients parmi 10 000 en 0,10 s. Ces chiffres ne prédisent pas les performances de production.

## Campagne complémentaire : routes et intégrité métier

Une nouvelle suite inventorie automatiquement les 164 routes API. Les 158 routes utilisant la chaîne centrale d'authentification ont été appelées sans session et ont toutes refusé l'accès. Les six routes publiques restantes sont explicitement attendues : connexion, inscription fermée en production, logout idempotent, deux crons protégés par secret et webhook Stripe protégé par signature.

Le contre-audit additionnel a aussi supprimé le replay de session PostHog/Emergent chargé sans consentement, rendu l'IA externe opt-in en production, fermé la suppression de notes sans permission courante et corrigé Stripe afin qu'une session terminée mais impayée ne soit jamais considérée comme payée. Un essai Stripe `trialing` reste reconnu comme donnant accès sans falsifier l'état du paiement.

La recherche globale a également été corrigée : elle respecte maintenant les permissions effectivement attribuées et les portées `own`, y compris après révocation, et ne renvoie l'annuaire des utilisateurs qu'aux comptes autorisés à le gérer.

Cette campagne a révélé puis fait corriger des validations manquantes : dates calendaires impossibles, heures invalides, mois de commission hors calendrier, part financée supérieure au montant total et collections imbriquées démesurées. Les prestations, catégories, statuts, tags IA, photos, réglages, primes et configurations utilisateur disposent maintenant de plafonds explicites avant stockage.

## Ce que ces résultats ne prouvent pas encore

La copie est prête pour une préproduction contrôlée, pas pour une certification de production. Il reste à tester sur la vraie infrastructure : MongoDB et concurrence multi-processus, navigateurs et coupures réseau, Stripe sandbox, emails et cron, fournisseur IA réel, sauvegarde/restauration, TLS/proxy et charge représentative. Aucun résultat externe n'est déclaré sans l'avoir réellement observé.
