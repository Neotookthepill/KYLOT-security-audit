# Contribuer à KYLOT

1. Créer une branche dédiée et une pull request.
2. Décrire le périmètre, les risques et le retour arrière.
3. Ajouter ou adapter les tests protégeant le comportement modifié.
4. Ne jamais utiliser de donnée client réelle dans le code, les tests ou les
   captures.
5. Attendre la réussite de la CI avant fusion.

Toute modification d'authentification, d'autorisation, de `company_id`, de
Stripe, d'import, de stock, de commission, de migration ou de mode hors ligne
exige une recette métier explicite.

Les scripts historiques de seed et de nettoyage refusent les environnements
distants par défaut. Leur activation sur un environnement jetable exige une
origine explicitement autorisée et l'acquittement documenté dans le code.

Le dépôt n'ayant pas encore de licence définitive, aucune contribution externe
ne doit être acceptée avant clarification des droits associés.
