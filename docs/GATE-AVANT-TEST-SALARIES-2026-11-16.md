# Gate avant test des salariés — 16 novembre 2026

Objectif : ne pas ouvrir les tests salariés tant que les six conditions obligatoires ne sont pas remplies.

## Statut global

```text
MFA administrateurs              : NON
Rotation MongoDB                 : NON
Sauvegarde + index restaurables  : PARTIEL
Parcours métier complet          : OUI (QA)
Rollback Render testé            : NON
Rôles commercial/responsable/technicien/admin : OUI (QA)
```

**Décision : test salariés NON autorisé.**

## 1. MFA administrateurs — à faire

Comptes admin concernés : tous les comptes `admin` et `super_admin`.

Procédure dans Qylot :

```text
Connexion admin
→ Paramètres
→ Sécurité / Double authentification
→ Configurer la double authentification
→ scanner le QR code avec Google Authenticator, Microsoft Authenticator ou 1Password
→ saisir le code à 6 chiffres
→ conserver les codes de secours hors ligne
→ refaire pour chaque administrateur
```

Vérification :

```text
GET /api/users
→ mfa_enabled = true pour chaque admin
```

Ne pas désactiver `MFA_ENFORCE_ADMINS`.  
Ne pas partager les codes de secours.

## 2. Rotation des identifiants MongoDB — à faire

Prérequis : sauvegarde fraîche déjà créée.

```text
Atlas
→ Database Access
→ utilisateur applicatif
→ Edit / Change Password
→ générer un mot de passe fort
→ mettre à jour MONGO_URL dans Render
→ redéployer l'API
→ vérifier /api/health
→ révoquer l'ancien accès
```

À faire sur QA **et** production, avec des identifiants distincts.

Vérifier ensuite :

```text
QA     : /api/health 200
Prod   : /api/health 200
```

Ne jamais coller l'URI ou le mot de passe dans un ticket, un chat ou Git.

## 3. Sauvegarde restaurable avec index — partiel

Preuves existantes :

```text
archive complète : 3 080 documents restaurés, 0 échec
nouvelle archive : 64 Mo, checksum valide, dry-run valide
```

Reste à faire :

```text
1. restaurer l'archive fraîche dans une base vierge
2. restaurer les index
3. vérifier les index avec index_information()
4. lancer un smoke test API sur cette base
5. mesurer le temps total
6. conserver une copie hors site
```

Tant que les index ne sont pas validés, la restauration n'est pas considérée comme opérationnelle.

## 4. Parcours métier complet — fait en QA

Parcours exécuté :

```text
client créé
→ vente créée
→ chantier auto-créé
→ date planifiée
→ technicien affecté
→ photo ajoutée
→ produit stock créé
→ commission calculée
```

Résultat :

```text
client                 : 200
vente                  : 200
projet planning        : 1
planification          : 200
photo                  : 1 ajoutée
stock                  : 200
commission             : 1 ligne, 120 €
```

Les enregistrements de test ont été supprimés après le parcours.

## 5. Rollback Render — à faire

Procédure :

```text
Render
→ service API kylot-preview-api
→ Deploys
→ sélectionner le dernier déploiement vert précédent
→ Redeploy
→ vérifier /api/version
→ refaire la même opération sur le frontend
→ vérifier le parcours de connexion et une page métier
```

Attention :

```text
le rollback Render ne rollback pas MongoDB
```

Il faut donc :

```text
code + frontend : rollback Render
données         : restauration Mongo séparée
```

Un rollback doit être testé au moins une fois avant le test salariés.

## 6. Rôles et permissions — fait en QA

Matrice vérifiée :

| Rôle | `/api/users` | `/api/reports/monthly` | `/api/commissions` | `/api/planning/projects` |
|---|---:|---:|---:|---:|
| admin | 200 | 200 | 200 | 200 |
| responsable | 403 | 200 | 200 | 200 |
| commercial | 403 | 403 | 200 | 200 |
| technicien | 403 | 403 | 403 | 200 |

Les quatre rôles se connectent avec les comptes QA fournis.

## Verdict

```text
Parcours métier et rôles : validés
Données et comptes QA    : propres
MFA                      : bloquant
Rotation MongoDB         : bloquant
Index de restauration    : bloquant
Rollback Render          : bloquant
```

**Le test des salariés ne doit pas être ouvert avant la fermeture de ces quatre points.**
