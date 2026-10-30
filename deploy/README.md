# Préproduction reproductible de KYLOT

Ce dossier prépare un pilote **mono-instance** derrière un reverse proxy TLS de
l'hébergeur. Il ne publie pas MongoDB et n'embarque aucun secret.

## Préconditions

- un serveur avec Docker Compose ;
- un domaine HTTPS dont le proxy public transfère vers `127.0.0.1:8080` ;
- une instance MongoDB privée avec sauvegardes activées ;
- un jeu de données fictif ou anonymisé pour la préproduction.

## Démarrage contrôlé

1. Copier `deploy/backend.env.example` vers `deploy/secrets/backend.env`.
2. Remplacer chaque valeur `replace-*` et laisser les services externes
   désactivés tant qu'ils ne sont pas validés.
3. Exécuter le pré-vol avec ces variables, sans les afficher :

   ```sh
   set -a
   . deploy/secrets/backend.env
   set +a
   python3 backend/preflight.py --strict
   ```

   Le mode strict exige les intégrations facultatives. Pour un premier pilote
   sans IA, email ni Stripe, lancer sans `--strict` et vérifier chaque warning.

4. Construire et démarrer :

   ```sh
   docker compose -f deploy/compose.preproduction.yml build --pull
   docker compose -f deploy/compose.preproduction.yml up -d
   ```

5. Vérifier l'extérieur avec `APP_URL=https://… scripts/smoke_deployment.sh`.

Le port applicatif est lié uniquement à `127.0.0.1`. Le backend n'est jamais
exposé directement. N'activer `TRUST_PROXY_HEADERS=true` que dans cette
topologie, car Nginx remplace l'en-tête transmis par le navigateur.

## Limite volontaire

L'image backend installe `requirements-core.txt`. Les fonctions IA externes
restent désactivées : la dépendance privée Emergent n'est pas suffisamment
reproductible pour être intégrée au premier pilote. Elle doit être remplacée ou
archivée dans un registre contrôlé avant activation.

## Arrêt et retour arrière

Conserver l'identifiant du commit et les images précédentes. En cas d'anomalie :

```sh
docker compose -f deploy/compose.preproduction.yml down
# Revenir au commit ou aux images précédemment validés, puis redémarrer.
```

Ne jamais restaurer une sauvegarde par-dessus la production sans validation
sur une base distincte et accord explicite du propriétaire des données.
