# Mise en ligne de la préproduction KYLOT sur Render

Cette procédure crée une version de démonstration isolée. Ne jamais importer de
données client réelles pendant cette validation.

## 1. Créer MongoDB Atlas

1. Créer un projet `KYLOT Preview` et un cluster partagé en région Frankfurt.
2. Créer un utilisateur de base dédié avec un mot de passe unique.
3. Copier l'URI `mongodb+srv://...` proposée pour l'application.
4. Après la création du service Render, ajouter dans Atlas uniquement les
   plages IP sortantes affichées par Render dans **Connect > Outbound**.

## 2. Créer le Blueprint Render

1. Ouvrir Render et connecter le compte GitHub qui possède
   `Neotookthepill/KYLOT-security-audit`.
2. Choisir **New > Blueprint** puis sélectionner ce dépôt et la branche `main`.
3. Render détecte `render.yaml` et prépare :
   - `kylot-preview`, le site public HTTPS ;
   - `kylot-preview-api`, le backend privé.
4. Renseigner les trois champs demandés :
   - `MONGO_URL` : l'URI Atlas ;
   - `ADMIN_EMAIL` : l'adresse du compte de test ;
   - `ADMIN_PASSWORD` : un mot de passe long et unique.
5. Valider le Blueprint. Ne renseigner aucune clé Stripe, email ou IA pour ce
   premier déploiement.

Le backend privé utilise un petit plan payant. Le frontend peut utiliser le plan
gratuit pour la recette, avec le délai de réveil propre à ce plan.

## 3. Autoriser Render dans Atlas

1. Ouvrir le service `kylot-preview-api` dans Render.
2. Copier toutes les plages affichées dans **Connect > Outbound**.
3. Dans Atlas, ouvrir **Network Access** et ajouter exactement ces plages.
4. Attendre la prise en compte puis relancer le déploiement Render si nécessaire.

Ne pas utiliser `0.0.0.0/0` pour contourner l'étape réseau.

## 4. Vérifier

Quand les deux services sont verts, ouvrir l'URL du service `kylot-preview` et
exécuter depuis un poste local :

```sh
APP_URL=https://kylot-preview.onrender.com scripts/smoke_deployment.sh
```

La recette fonctionnelle utilise uniquement des informations fictives :

- connexion et déconnexion ;
- création d'un client, d'une vente et d'un chantier de test ;
- contrôle d'un fichier autorisé puis d'un fichier refusé ;
- vérification sur mobile ;
- désactivation du compte de test et contrôle du refus de connexion.

Supprimer ensuite les données fictives ou détruire entièrement l'environnement
de préproduction si la démonstration est terminée.
