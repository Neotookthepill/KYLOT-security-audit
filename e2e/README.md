# Tests E2E de préproduction

`staging_flow.js` teste la préproduction KYLOT avec Playwright et Chromium.

## Prérequis

- Node.js et le module `playwright` disponibles.
- Un compte admin de test et un compte commercial de test.
- Un fichier local **non versionné** avec les identifiants :

```bash
cat > /tmp/kylot-e2e.env <<'ENV'
E2E_ADMIN_EMAIL=...
E2E_ADMIN_PASSWORD=...
E2E_COMMERCIAL_EMAIL=...
E2E_COMMERCIAL_PASSWORD=...
ENV
```

Aucun mot de passe n'est affiché par le script.

## Lancer

```bash
cd /chemin/vers/kylot
NODE_PATH=/Users/l1l2/node_modules node e2e/staging_flow.js
```

Variables optionnelles :

```bash
STAGING_URL=https://kylot-preview.onrender.com
E2E_ENV_FILE=/tmp/kylot-e2e.env
```

## Ce qui est vérifié

1. Connexion commercial et absence des écrans admin.
2. Redirection de `/utilisateurs` pour un commercial.
3. Connexion admin et création d'un client/vente/chantier.
4. Mois de commission dérivé de la date du chantier.
5. Affichage de la commission responsable reportée et de son détail.
6. Mise à jour du mois quand la date du chantier change.
7. Priorité de l'override manuel du mois.
8. Création du challenge, classement et affichage sur le dashboard.
9. Présence du client et de la vente dans les écrans.

## Données de test

Les données sont préfixées `E2E-`. L'API de suppression refuse de supprimer une
vente qui possède un chantier, même soft-deleted. Les données de test restent donc
dans la base de staging ; utiliser une base de staging jetable ou supprimer les
documents `E2E-` depuis Atlas avant une démonstration client.

Le script remet le rôle du commercial test à `commercial` et clôture/archive le
challenge de test à la fin.


## MFA

```bash
NODE_PATH=/Users/l1l2/node_modules node e2e/mfa_flow.js
```

Teste la configuration TOTP, le blocage du login par mot de passe seul, la
connexion avec code, la connexion avec code de secours, la désactivation et le
retour au login mot de passe seul. Le compte de test doit être administrateur.


## Offline

```bash
NODE_PATH=/Users/l1l2/node_modules node e2e/offline_flow.js
```

Crée une vente, passe le navigateur hors ligne, modifie les notes, vérifie que
le serveur n'est pas touché, rétablit le réseau, puis contrôle le rejeu et la
vidange de la file IndexedDB.


## Imports

```bash
NODE_PATH=/Users/l1l2/node_modules node e2e/import_flow.js
```

Couvre l'import copier-coller, la détection de doublons et l'import fichier CSV
avec mapping des colonnes.
