# Politique de versions

Tant que la préproduction n'est pas validée, les commits de `main` ne sont pas
des releases commerciales. Une baseline doit référencer un commit exact et une
CI réussie.

Après validation du pilote, KYLOT suivra une version `MAJEURE.MINEURE.CORRECTIF` :

- **MAJEURE** : rupture d'API, migration irréversible ou changement métier
  incompatible ;
- **MINEURE** : fonctionnalité rétrocompatible ;
- **CORRECTIF** : sécurité, bug ou amélioration sans rupture attendue.

Chaque release doit contenir les changements, migrations, limites connues,
preuves de validation et procédure de retour arrière.
