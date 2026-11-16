# Runbook sauvegarde et réconciliation de migration

## Sauvegarde disponible

Archive locale protégée, non versionnée :

```text
backups/20261116T063852-pre-post.tar.gz
SHA-256 : 33a228f4d4c623d48632f8b2d29bfbf2b9648db429d9a6688dde5e25c9e822af
```

Contenu :

```text
pre-migration  : 541 clients, 175 ventes, 78 chantiers
post-migration : 552 clients, 193 ventes, 93 chantiers
+ équipe, stock, événements, paramètres, utilisateurs
```

Cette archive est un **export API**, pas un snapshot MongoDB Atlas.
Elle ne contient pas les mots de passe.

## Ce qui manque pour un vrai rollback

```text
snapshot Atlas
identifiant du snapshot
base de restauration séparée
test de restauration
durée de restauration
responsable de validation
```

Sans snapshot Atlas, le rollback complet n'est pas garanti.

## Contrôle read-only

```bash
KYLOT_BASE_URL="https://kylot-preview.onrender.com" \
KYLOT_ADMIN_EMAIL="..." \
KYLOT_ADMIN_PASSWORD="..." \
KYLOT_SOURCE_EXPORT="/chemin/source" \
python3 scripts/reconcile_migration.py
```

Le script :

```text
ne fait que des GET
ne supprime rien
ne modifie rien
n'affiche aucune donnée personnelle
échoue si doublon email/téléphone, orphelin, ou objet TEST-AUDIT
signale les doublons BDC et les libellés équipe absents
```

Dernier résultat :

```text
clients 552, ventes 193, chantiers 93, photos 123
0 doublon email/téléphone
0 orphelin
0 objet TEST-AUDIT
2 BDC dupliqués préexistants
2 libellés équipe source absents
```

## Procédure future

1. Gel des écritures.
2. Snapshot Atlas.
3. Export API de contrôle.
4. Import QA.
5. Réconciliation QA.
6. Import production uniquement des absents.
7. Réconciliation production.
8. Déploiement.
9. Dégel.
10. Conservation de l'archive et du snapshot.
