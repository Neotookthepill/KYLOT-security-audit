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

En CI, le workflow installe Playwright et Chromium puis lance ce script.
