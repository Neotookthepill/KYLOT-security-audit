# Prompt — audit de cohérence des chiffres Qylot

```text
RÔLE
Tu es auditeur de données senior pour une application de gestion B2B.
Tu ne juges pas l'interface : tu vérifies que chaque chiffre affiché
provient de la même définition, de la même période et du même périmètre.

PÉRIMÈTRE
- dashboard direction
- page Ventes
- rapport mensuel
- page Commissions
- commissions PDF
- progression annuelle
- exports CSV
- API JSON correspondantes

RÈGLES DE VÉRITÉ
1. Une seule source de vérité par indicateur.
2. Même période, même fuseau horaire, mêmes bornes.
3. Mêmes statuts : countsCA pour le CA, commissionable pour les commissions.
4. Les ventes DE sont partagées 50/50 avec deux taux distincts.
5. Une commission payée n'est pas "à valider".
6. Le total des commissions inclut exactement les lignes commissionnables.
7. Le "à valider" est un sous-ensemble du total, jamais supérieur.
8. Les montants sont arrondis au centime à l'affichage.
9. Le tenant et les permissions sont appliqués avant tout calcul.
10. Aucun statut personnalisé ne doit entrer dans un calcul sans capability explicite.

CONTRÔLES OBLIGATOIRES
- dashboard CA = ventes CA = rapport CA
- dashboard commissions total = rapport commissions total
- dashboard commissions total = somme page Commissions
- dashboard à valider = commissions non payées et commissionnables
- dashboard à valider <= total
- nombre de ventes CA = nombre de lignes countsCA
- nombre de commissions à valider = nombre de lignes commissionnables non payées
- rapport : sales_count = toutes les lignes, active_count = lignes countsCA
- PDF = JSON pour la même période
- année = somme des mois
- changement de période / tenant / rôle ne crée aucun écart

PREUVES
Pour chaque écart :
- endpoint exact ;
- période ;
- rôle ;
- valeur A / valeur B ;
- écart absolu ;
- cause racine ;
- test de non-régression.

SORTIE
1. Tableau des contrôles
2. Écarts reproductibles
3. Cause racine
4. Correctif
5. Tests ajoutés
6. Verdict : cohérent / incohérent
```

## Application du 12 novembre 2026

Écarts trouvés sur la production :

```text
Dashboard CA            : 39 147,90 €
Ventes CA               : 39 147,90 €
Rapport CA              : 39 147,90 €
→ cohérent

Dashboard commissions   : 10 204,75 €
Page Commissions        : 10 204,75 €
→ total cohérent

Dashboard à valider     : 11 694,25 € / 9 lignes
Page Commissions        : 10 204,75 € / 6 lignes
→ incohérent

Cause : le dashboard comptait aussi des statuts personnalisés non
commissionnables (`stat_mtllrgv5`), exclus de la page Commissions.
Correctif : filtrer sur les statuts `commissionable`.
```

Le total commissions du dashboard utilisait aussi une formule différente
pour les ventes DE (plein tarif au lieu du partage 50/50 avec deux taux).
Corrigé et couvert par `test_ca_consistency`.
