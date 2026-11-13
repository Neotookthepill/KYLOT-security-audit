# E2E P1

`node e2e/run.mjs` sert le build frontend et vérifie, avec les API mockées :

```text
- colonnes Ventes masquées puis réaffichées
- ouverture du panneau latéral
- onglets Kanban mobile
- chargement progressif 12 → 17 cartes
- assistant mobile dans la nav, sans bulle flottante
```

Prérequis locaux : `playwright` et un build frontend à jour.

Le script est exécutable localement avec Playwright installé.
L'intégration CI automatique n'est pas active : l'installation du navigateur
dans l'environnement CI n'a pas encore été stabilisée.
