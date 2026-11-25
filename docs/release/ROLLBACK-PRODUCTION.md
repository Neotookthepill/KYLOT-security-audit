# Rollback production Qylot

## Principe

Un rollback se décide sur un incident réel, pas sur une simple impression.

Ordre recommandé :

```text
1. rollback code
2. vérification
3. restauration base uniquement si les données sont corrompues
```

## 1. Rollback code

Dans Render :

```text
kylot-preview-api
→ Deploys
→ sélectionner le déploiement précédent
→ Redeploy

kylot-preview
→ Deploys
→ sélectionner le déploiement précédent
→ Redeploy
```

Version précédente connue avant release :

```text
05700c6
```

Vérifier :

```bash
APP_URL='https://kylot-preview.onrender.com' \
EXPECTED_VERSION='05700c6' \
./scripts/release/smoke_production.sh
```

Puis vérifier manuellement :

- connexion admin ;
- ouverture d’une vente ;
- ouverture d’un chantier ;
- tableau de bord ;
- aucune erreur 5xx.

## 2. Rollback base

À faire uniquement si :

- des données ont été supprimées ou corrompues ;
- une migration de données a échoué ;
- les contrôles d’intégrité sont faux.

Ne pas restaurer la base pour un simple bug d’affichage.

### Vérification de la sauvegarde

```bash
shasum -a 256 -c backups/release-*/prod-before-*.archive.gz.sha256
```

### Restauration

> Commande destructive : elle remplace la base cible.  
> Ne jamais la lancer sans avoir vérifié `PROD_MONGO_URI`, `PROD_DB_NAME` et la sauvegarde.

```bash
export PROD_MONGO_URI='...'
export PROD_DB_NAME='...'

mongorestore \
  --uri="$PROD_MONGO_URI" \
  --archive="backups/release-XXXX/prod-before-XXXX.archive.gz" \
  --gzip \
  --nsFrom="$PROD_DB_NAME.*" \
  --nsTo="$PROD_DB_NAME.*" \
  --drop
```

Après restauration :

- `/health` ;
- `/ready` ;
- connexion ;
- vérifier clients, ventes, chantiers, photos ;
- vérifier les totaux ;
- consigner l’incident.

## 3. Ce qu’il ne faut pas faire

```text
❌ lancer promote_qa_to_prod.sh pendant un rollback
❌ restaurer une sauvegarde QA en production
❌ supprimer une collection pour « réparer »
❌ modifier les ventes ou commissions à la main
```

## 4. Journal de rollback

À remplir :

```text
Heure :
Commit déployé :
Symptôme :
Décision :
Version restaurée :
Sauvegarde utilisée :
Vérifications :
Responsable :
```
