# Migration de données — version client vers pilote production

## Périmètre

```text
Source : https://sales-dispatch-6.emergent.host/   (version client, iter178)
Cible  : https://kylot-preview.onrender.com/       (pilote production)
```

La source n'a pas été modifiée. Aucune donnée existante de la cible n'a été
supprimée ni écrasée.

## Sauvegarde

Avant import, les collections suivantes ont été exportées dans un répertoire
temporaire protégé :

```text
clients, sales, projects, team, events, stock, settings
```

## Résultat

| Donnée | Source | Cible avant | Cible après | Importés |
|---|---:|---:|---:|---:|
| Clients | 552 | 541 | 552 | 11 |
| Ventes | 193 | 175 | 193 | 18 |
| Chantiers | 84 | 78 | 93 | 15 |
| Photos | 111 | 94 | 123 | 29 |
| Événements | 4 | 4 | 4 | 0 |
| Stock | 30 | 30 | 30 | 0 |

La cible conserve 9 chantiers qui n'existent pas dans la source. Ils n'ont pas
été supprimés.

## Contrôles après import

```text
doublon email client          : 0
doublon téléphone client      : 0
vente sans client             : 0
chantier sans client          : 0
chantier sans vente           : 0
doublon vente → chantier      : 0
photos source-only importées  : 29 / 29
```

Les 2 BDC dupliqués existaient déjà dans la cible. Aucun BDC source-only ne
correspondait à un BDC cible avant l'import.

Les identifiants source ne sont pas conservés : les clients, ventes et chantiers
importés reçoivent de nouveaux identifiants cible, et les relations sont
reconstruites par le script.

## Ce qui n'a pas été migré

```text
mots de passe / hash de comptes
paramètres de société source
journal d'audit source
commissions recalculées par le moteur cible
challenges : aucun module challenge côté source
photos : 29 photos des chantiers source-only importées
```

## Rollback

Le rollback ne peut pas être fait par simple suppression API : les ventes liées
à un chantier ne sont pas supprimables par l'API. Il faut restaurer la base
production depuis une sauvegarde si la migration doit être annulée.

## État

```text
Migration production : RÉUSSIE
Source               : NON MODIFIÉE
CI / code            : inchangés par la migration
```
