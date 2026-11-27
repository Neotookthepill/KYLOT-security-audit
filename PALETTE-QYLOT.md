# Palette Qylot

## Principe

Une couleur doit avoir un sens métier.  
Elle ne doit jamais servir uniquement à décorer.

```text
3 accents maximum par écran
le blanc / ardoise reste majoritaire
une même notion garde la même couleur partout
```

## Couleurs officielles

| Rôle | Couleur | Sens | Exemples |
|---|---|---|---|
| Indigo | `#4F46E5` | Volume, CA, activité commerciale | Ventes, CA généré, classement |
| Ciel | `#0EA5E9` | Planification, analyse | Agenda, montant moyen, CA du mois |
| Émeraude | `#059669` | Acquis, payé, couvert, validé | Commissions payées, stock couvert, marge solide |
| Ambre | `#F59E0B` | En attente, à surveiller | À traiter, reste à payer, stock bas |
| Rose | `#E11D48` | Bloqué, annulé, critique | Annulations, litiges, à commander, absence |
| Ardoise | `#64748B` | Neutre, information | Catégories, volumes, données secondaires |

## Règles

```text
❌ une couleur par catégorie
❌ une couleur par colonne
❌ vert pour autre chose que « acquis / couvert »
❌ rose pour autre chose que « bloqué / critique »
```

```text
✅ les catégories de sources restent neutres
✅ le rouge est réservé aux alertes réelles
✅ le vert est réservé aux résultats positifs
✅ l'ambre est réservé à l'attente
```

## Application

### Tableau de bord

```text
Ventes          → indigo
À traiter       → ambre
Agenda du jour  → émeraude
Montant moyen   → ciel
```

### Commissions

```text
Total commissions → indigo
Reste à payer     → ambre
Déjà payé         → émeraude
```

### Prospection

```text
CA généré           → indigo
Clients / volumes   → neutre
Rémunération        → émeraude
Commission réelle   → émeraude
Commission reportée → ambre
```

### Stock

```text
À commander   → rose
Stock bas     → ambre
Stock couvert → émeraude
```

### Planning

```text
À planifier → ardoise
En cours    → ambre
Terminé     → indigo
Encaissé    → émeraude
Absence     → rose
```

### Rapport mensuel

```text
Ventes comptées → indigo
Annulations     → rose
CA du mois      → ciel
Commissions     → émeraude
Sources         → neutres
```
