# Release production Qylot — checklist du 25/11/2026

## Décision

- **Candidat QA :** `79f0f2e`
- **Production actuelle :** `05700c6`
- **Type de release :** code applicatif, sans copie des données QA
- **Interdit :** lancer `scripts/promote_qa_to_prod.sh` pour cette release
  - il copie les collections métier QA vers la production
  - il écraserait les clients, ventes et chantiers de production
- **Fenêtre recommandée :** hors activité, avec au moins 2 h de disponibilité
- **Responsable :** à désigner
- **Rollback :** voir `docs/release/ROLLBACK-PRODUCTION.md`

## 1. Avant le gel

- [ ] CI verte sur `79f0f2e`.
- [ ] Build frontend local réussi.
- [ ] Tests E2E P1 réussis.
- [ ] QA validée sur les parcours critiques.
- [ ] Aucun changement de code en cours.
- [ ] Fenêtre de release annoncée.
- [ ] Version production notée : `05700c6`.
- [ ] Responsable rollback désigné.

## 2. Sauvegarde obligatoire

Variables à préparer dans un terminal sécurisé, sans les écrire dans Git :

```bash
export PROD_MONGO_URI='...'
export PROD_DB_NAME='...'
```

Exécuter :

```bash
CONFIRM=BACKUP ./scripts/release/backup_production.sh
```

Le script :

- refuse une cible contenant `qa` ou `staging` ;
- crée une archive complète `mongodump` ;
- crée un SHA-256 ;
- enregistre la version API et le commit de release ;
- n’affiche jamais l’URI.

Contrôles :

- [ ] Archive créée dans `backups/release-*`.
- [ ] Taille cohérente avec la production.
- [ ] SHA-256 généré.
- [ ] Version API notée.
- [ ] Sauvegarde copiée hors du poste local.
- [ ] Restauration testée sur une base temporaire, jamais sur la production.

> Si `mongodump` bloque sur les photos, utiliser une sauvegarde Atlas à la demande.  
> Ne pas démarrer la release sans sauvegarde exploitable.

## 3. Vérifications avant déploiement

- [ ] `/health` et `/ready` répondent en production.
- [ ] Le trafic est nominal avant la release.
- [ ] Les secrets ne changent pas pendant cette release.
- [ ] `RUN_STARTUP_MIGRATIONS` reste à `false`.
- [ ] Le changement est compatible avec les données existantes :
  - ajout de `excluded_sale_ids` sur les challenges ;
  - synchronisation des coordonnées client vers les ventes ;
  - aucune suppression de collection.
- [ ] Les comptes de contrôle existent pour admin, commercial, technicien.
- [ ] Un chantier de test avec photo est disponible.
- [ ] Le frontend de production est suffisamment dimensionné.  
      Le `render.yaml` indique encore `plan: free` : à corriger avant ou juste après la release si la latence est un problème.

## 4. Ordre de déploiement

### 4.1 Backend

- [ ] Render → service `kylot-preview-api`.
- [ ] Manual Deploy du commit `79f0f2e`.
- [ ] Attendre `/api/version` = `79f0f2e`.
- [ ] Vérifier les logs : aucune erreur 5xx au démarrage.

### 4.2 Frontend

- [ ] Render → service `kylot-preview`.
- [ ] Manual Deploy du commit `79f0f2e`.
- [ ] Vérifier que le nouveau build est servi.
- [ ] Vérifier `/asset-manifest.json`.

### 4.3 Après déploiement

- [ ] `/health` OK.
- [ ] `/ready` OK.
- [ ] `/api/version` = `79f0f2e`.
- [ ] Connexion admin OK.
- [ ] Connexion commercial OK.
- [ ] Connexion technicien OK.
- [ ] Un client s’ouvre.
- [ ] Un chantier s’ouvre.
- [ ] Une photo de test s’ajoute puis se supprime.
- [ ] Tableau de bord : compteurs cohérents.
- [ ] Tableau de vente : filtres Mois/Semaine/Jour/Année.
- [ ] Challenge : bouton Assistances visible pour l’admin.
- [ ] Décompte 14 jours visible sur une vente concernée.
- [ ] Modification des coordonnées client depuis la fiche client.
- [ ] Vérification des coordonnées dans la vente liée.
- [ ] Aucun bandeau d’erreur, aucune page blanche.
- [ ] Aucune erreur 5xx dans les logs Render.

## 5. Smoke test automatique

```bash
APP_URL='https://kylot-preview.onrender.com' \
EXPECTED_VERSION='79f0f2e' \
./scripts/release/smoke_production.sh
```

Le script est en lecture seule :

- health ;
- readiness ;
- version ;
- présence des en-têtes de sécurité ;
- absence d’OpenAPI public ;
- présence du build frontend.

## 6. Surveillance 24 h

- [ ] Erreurs 5xx.
- [ ] Latence API.
- [ ] Connexions échouées.
- [ ] Uploads photos.
- [ ] Erreurs frontend.
- [ ] MongoDB : connexions, stockage, sauvegardes.
- [ ] Aucun ticket « ancienne version ».
- [ ] Aucune incohérence de commission ou de challenge signalée.

## 7. Critères de rollback

Déclencher le rollback si :

- authentification cassée ;
- isolation des données compromise ;
- erreurs 5xx répétées ;
- impossibilité d’ouvrir les ventes ou chantiers ;
- corruption ou perte de données ;
- upload photo qui échoue massivement ;
- valeur financière incohérente.

Ne pas rollback pour :

- un simple détail visuel ;
- un cache PWA isolé ;
- une lenteur passagère sans erreur.

## 8. Après release

- [ ] Remplir le rapport post-déploiement.
- [ ] Noter l’heure, le commit, les incidents.
- [ ] Mettre à jour la version de référence.
- [ ] Conserver la sauvegarde au moins 30 jours.
- [ ] Planifier la migration R2/S3.
