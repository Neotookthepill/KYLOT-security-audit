# QA — accès équipe client

## Environnement

```text
URL : https://kylot-preview-qa.onrender.com
Base : QA séparée de la production
Données : données réelles clonées
```

## Comptes créés

```text
1 admin
1 responsable
2 commerciaux
2 techniciens
2 prospecteurs
1 responsable prospecteur
1 sous-traitant
1 comptable
```

Total : **11 comptes**, un par rôle.

Les identifiants sont dans un fichier local protégé, non versionné :

```text
backups/qa-team/credentials.json
```

Ne pas envoyer ce fichier dans un groupe public.

## Points de vigilance

```text
les données sont réelles
la QA est une copie, pas la production
les modifications de test restent dans la QA
les emails réels et Stripe doivent rester désactivés
la QA doit être restaurée après les tests
```

## Ce qui reste à faire

```text
snapshot Atlas avant la session
déployer le code actuel sur la QA
vérifier que les emails sortants sont désactivés
vérifier Stripe sandbox/désactivé
prévenir les testeurs que les données sont réelles
planifier la restauration QA après test
```

## Accès aux comptes

Les mots de passe sont générés aléatoirement. Ils ne sont pas dans Git.
Le fichier est en `chmod 600`, dossier `chmod 700`.
