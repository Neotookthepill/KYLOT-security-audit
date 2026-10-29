# KYLOT — contrôle d'hygiène du dépôt

Référence examinée : commit `6bf15d2` et ses cinq commits accessibles.

## Vérifications réalisées

- 321 fichiers suivis et 360 objets Git inventoriés ;
- recherche dans tous les blobs accessibles des formats courants de clés
  privées, jetons GitHub, clés AWS, clés Stripe et URL MongoDB avec identifiants ;
- contrôle des affectations ressemblant à des mots de passe, secrets, clés API
  et jetons ;
- inventaire des scripts de seed/nettoyage, rapports historiques, documents
  Emergent et dépendances privées ;
- contrôle de la CI et des références des GitHub Actions.

## Résultat du contrôle de secrets

Aucun format de clé privée, jeton GitHub, clé AWS ou clé Stripe n'a été détecté
dans les cinq commits actuels. Les correspondances génériques restantes sont des
noms de champs applicatifs, des variables d'environnement ou des identifiants de
tests. Ce contrôle réduit le risque mais ne remplace pas un outil spécialisé ni
une rotation des secrets ayant déjà servi ailleurs.

## Correctifs appliqués

- retrait du `.gitconfig` Emergent du contenu du projet ;
- blocage par défaut des scripts historiques capables de modifier une cible
  HTTP ou MongoDB distante ;
- épinglage des GitHub Actions sur des commits immuables ;
- ajout de Dependabot ;
- ajout de `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, modèles de pull request
  et d'issues, politique de versions et changelog.

## Points encore ouverts

1. Le propriétaire doit décider si le dépôt reste public ou devient privé.
2. Les règles de protection de `main` doivent être activées dans GitHub.
3. Aucun tag ni aucune release de référence ne doit être publié avant la
   décision de visibilité et le tri des documents historiques.
4. Les 62 fichiers de `test_reports/`, les huit documents
   `deployer-agent-docs/` et les documents `memory/` doivent faire l'objet d'une
   décision de conservation. Ils n'ont pas été supprimés automatiquement.
5. `emergentintegrations` et la roue `litellm` hébergée chez Emergent doivent
   être archivées ou remplaçables avant de pouvoir garantir une reconstruction.
6. La CI doit devenir une règle de fusion obligatoire dans GitHub.
7. La licence définitive et la propriété du code restent à confirmer.

## Limite

L'historique actuellement visible ne contient que cinq commits. Il ne permet pas
d'auditer un ancien dépôt, une branche supprimée ou des objets disparus lors de
la recréation du dépôt.
