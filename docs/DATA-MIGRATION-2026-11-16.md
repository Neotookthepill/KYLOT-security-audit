# Migration de données — version client vers pilote QA

## Périmètre

```text
Source : https://sales-dispatch-6.emergent.host/  (version client, iter178)
Cible  : https://kylot-preview-qa.onrender.com/   (pilote QA)
```

La source n'a pas été modifiée. La production n'a pas été touchée.

## Résultat

| Donnée | Source | QA avant | QA après | Source-only importés |
|---|---:|---:|---:|---:|
| Clients | 552 | 545 | 556 | 11 |
| Ventes | 193 | 179 | 197 | 18 |
| Chantiers | 84 | 78 | 93 | 15 |
| Photos | 111 | 94 | 123 | 29 |
| Événements | 4 | 4 | 4 | 0 |
| Stock | 30 | 30 | 30 | 0 |
| Équipe | 13 | 13 | 13 | 2 slots fusionnés |
| Utilisateurs | 17 emails | tous présents | tous présents | 0 |

Les 4 clients et 4 ventes supplémentaires côté QA sont des données déjà présentes
dans QA, conservées.

## Contrôles après import

```text
clients sans email/phone dupliqué : 0
vente sans client                 : 0
chantier sans client              : 0
chantier sans vente               : 0
doublon de relation vente/chantier: 0
photos source-only importées      : 29 / 29
```

BDC dupliqués : **2** — doublons déjà présents dans les données, pas créés par
la migration. Aucun BDC source-only ne correspondait à un BDC cible avant import.

## Ce qui n'a pas été migré

```text
mots de passe / hash de comptes : impossible par API, et non nécessaire
paramètres de société            : non écrasés
journal d'audit source           : non copié
commissions                      : recalculées par le moteur cible
challenges                       : aucun module challenge côté source
données cible-only               : conservées
```

## Sauvegarde / rollback

Avant import, les exports QA de `clients`, `sales` et `projects` ont été
sauvegardés dans un répertoire temporaire protégé. La migration a créé de
nouveaux identifiants ; un rollback nécessite une restauration de la base QA,
pas une simple suppression via l'API (les ventes liées à des chantiers ne
peuvent pas être supprimées par l'API).

## État

```text
Migration QA : RÉUSSIE
Production   : NON TOUCHÉE
```

Le pilote production n'a pas été migré. Il faut confirmer l'environnement cible
et faire une sauvegarde avant de rejouer l'import.
