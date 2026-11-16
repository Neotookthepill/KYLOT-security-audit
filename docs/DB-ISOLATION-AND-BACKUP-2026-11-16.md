# Isolation QA / production et sauvegarde MongoDB

## Bases

```text
QA         : kylot_qa
Production : kylot_staging
```

Les deux URI pointent vers le même domaine Atlas (`82ctt9u`).
Les bases sont différentes, avec des utilisateurs MongoDB différents.

```text
isolation des données : OUI
isolation du cluster  : NON PROUVÉE
```

## Preuves de séparation

```text
QA   : 3 clients TEST-AUDIT
Prod : 0 client TEST-AUDIT
```

```text
QA   : 556 clients, 197 ventes
Prod : 552 clients, 193 ventes
```

Les objets de test créés dans `kylot_qa` ne sont pas dans `kylot_staging`.

## Volumes des dumps

```text
QA
clients       556
ventes        197
chantiers     153 (inclut les annulés/supprimés logiques)
users          20
team_members   12

Production
clients        552
ventes         193
chantiers      149 (inclut les annulés/supprimés logiques)
users           18
team_members    13
```

## Sauvegarde complète disponible

```text
backups/mongo-20261116T0920.tar.gz
128 Mo
SHA-256 : e1d8b301f8669da42a3c15eb72b51defdd8851498d0f164a8505f52755ef085e
```

Contenu :

```text
kylot_qa       dump complet
kylot_staging  dump complet
```

Ce sont des **mongodump logiques**, pas des snapshots Atlas/PITR.

## Ce qui n'est pas encore fait

```text
snapshot Atlas natif
restauration testée dans une base séparée
Continuous Cloud Backup
rotation des utilisateurs MongoDB exposés
```

## Recommandation

```text
1. restaurer le dump QA dans une base de test séparée
2. vérifier 556 / 197 / 153
3. faire tester l'équipe sur kylot_qa
4. restaurer kylot_qa depuis le dump si nécessaire
5. activer les snapshots Atlas plus tard
6. changer les mots de passe MongoDB QA et production
```
