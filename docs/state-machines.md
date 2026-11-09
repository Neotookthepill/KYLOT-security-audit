# Qylot — état des lieux des machines à états implicites

Date : 9 novembre 2026

## Décision d’architecture

**Ne pas introduire XState ni un moteur de workflow global.**

Le métier Qylot repose sur des statuts de vente **configurables** (`sale_statuses`) et sur des
règles devenues implicites dans plusieurs couches. Un moteur rigide casserait les statuts
personnalisés et les transitions libres utilisées aujourd’hui.

La bonne décision est une **couche de contrats de workflow** :

1. une seule définition des états, phases et invariants ;
2. des fonctions pures de lecture (`phase`, `isTerminal`, `can*`) ;
3. des gardes uniquement sur les actions destructives ou irréversibles ;
4. les mêmes noms d’événements et les mêmes libellés côté API, UI et tests ;
5. un manifeste lisible par un agent.

Cette approche améliore :

- **UX** : mêmes actions, mêmes libellés, mêmes raisons de blocage partout ;
- **DX** : une seule source, tests purs, pas de conditions `status !== ...` dispersées ;
- **AX** : manifeste stable, événements nommés, capacités explicites, test IDs constants.

---

# 1. Inventaire des machines implicites

## 1.1 Vente — cycle de vie

**Statuts par défaut**

```text
attente_prog
attente_fi
en_cours
chantier_fini
commercial_cheque
argent_recupere
litige
annule
```

**Statuts personnalisés** : ajoutés via `sale_statuses`, avec ordre, couleur,
visibilité et `hides_from_projects`.

**Transitions réelles** : largement libres dans l’UI. Les règles métier sont
dispersées sous forme de listes :

```text
status not in ("annule", "litige")
status not in ("annule", "litige", "non_financable")
status in ("argent_recupere", "annule", "litige")
```

**Phases implicites**

| Phase | Statuts | Sens |
|---|---|---|
| `pending_finance` | `attente_fi` | financement à valider |
| `pending_schedule` | `attente_prog` | à planifier |
| `in_progress` | `en_cours` | chantier en cours |
| `work_done` | `chantier_fini` | travaux finis |
| `pending_cheque` | `commercial_cheque` | chèque à récupérer |
| `paid` | `argent_recupere`, `virement_recu` | encaissé |
| `dispute` | `litige` | litige |
| `cancelled` | `annule` | annulé |
| `non_financable` | `non_financable` | non finançable |

**Risques**

- `desired_intervention_date` porte aussi deux pseudo-états :
  `attente_financement`, `attente_14j`.
- Les mêmes listes sont recopiées dans les ventes, commissions, dashboard,
  planning, stock, exports et IA.
- Un statut personnalisé peut être classé « actif » ou « fermé » différemment
  selon la page.
- Suppression d’une vente avec chantier : règle uniquement backend.

**Décision**

Ne pas figer les transitions entre statuts. Ajouter une **phase obligatoire**
à chaque statut (par défaut calculée), puis utiliser la phase pour :

```text
actif / fermé
commissionnable
visible dans le planning
compte dans le CA
autorise la suppression
autorise la clôture
```

---

## 1.2 Chantier — cycle de vie

**États**

```text
status      : a_planifier | en_cours | termine | encaisse
cancelled   : booléen séparé
scheduled_date
duration_days
additional_days
```

**Transitions observées**

```text
création vente → a_planifier ou en_cours
planification → en_cours
clôture technicien → termine
sale = argent_recupere → encaisse / fermé
annulation vente → cancelled + soft delete
```

**Risques**

- `termine` et `encaisse` se chevauchent.
- `cancelled` est un état terminal caché hors du champ `status`.
- Le Kanban, le planning et les commissions n’ont pas la même définition
  d’un chantier « fermé ».
- Plusieurs jours travaillés : `termine` peut être repassé à `en_cours`.

**Décision**

Machine **explicite** pour le chantier, car ses états sont stables :

```text
a_planifier → en_cours → termine → encaisse
      ↘ cancelled
```

Les transitions restent tolérantes :

- `termine → en_cours` autorisé pour correction ;
- `encaisse` terminal ;
- `cancelled` terminal ;
- suppression = soft delete + audit, jamais un statut.

---

## 1.3 Commission

**Champs**

```text
commission_rate
commission_month
commission_paid
commission_deferred
commercial_slot
```

**États implicites**

```text
à calculer
à payer
payée
reportée
annulée (via statut vente)
non finançable
```

**Risques**

- `commission_paid` est un booléen, sans date de paiement ni auteur.
- Le mois de commission est parfois déduit de la date de vente.
- Une vente annulée après paiement n’a pas d’état de reprise explicite.
- Prospection utilise un mois différent.

**Décision**

Ajouter un **état dérivé** :

```text
commissionState(sale) =
  cancelled | not_eligible | deferred | to_pay | paid
```

Et conserver `commission_paid` comme donnée, pas comme machine.

---

## 1.4 Prospection

**Champs**

```text
prospect_status
commission_month
prospect_commission_month
```

**États**

```text
prospect
en cours
converti
perdu
commission réelle
commission reportée
```

**Risque réel déjà rencontré**

Une valeur `attente_financement` dans un champ « mois » a produit :

```text
undefined atte
```

**Décision**

Valider le format `AAAA-MM` à l’écriture et à la lecture.
La machine de prospection doit être dérivée de la vente convertie, pas recalculée
avec des règles locales.

---

## 1.5 Challenge

**États**

```text
à venir
actif
terminé
archivé
```

**Aujourd’hui** : déduits des dates, sans champ `status` explicite.

**Risques**

- dates modifiables après clôture ;
- participants/rewards modifiables après résultats ;
- égalités et rang recalculés à chaque lecture ;
- challenge de Noël actif.

**Décision**

Ajouter un état calculé **et** un verrou :

```text
active  : dates + not closed_at
closed  : closed_at définitif
```

Ne pas autoriser l’édition des participants/récompenses après `closed_at`.

---

## 1.6 Synchronisation hors ligne

**États**

```text
online
offline
pending
syncing
conflict
error
```

**Bug corrigé**

Le timer de 20 s passait en `syncing` même avec une file vide,
ce qui faisait clignoter la barre.

**Décision**

Machine à états explicite :

```text
idle → syncing → idle
idle → conflict → resolving → idle
idle → error → retry → syncing
```

Événements :

```text
QUEUE_ADDED
SYNC_STARTED
SYNC_SUCCEEDED
SYNC_FAILED
CONFLICT_FOUND
CONFLICT_RESOLVED
```

---

## 1.7 Authentification / MFA

**États**

```text
loading
anonymous
authenticated
mfa_required
mfa_setup_required
mfa_grace
session_expired
```

**Risques**

- plusieurs booléens (`authLoading`, `mfaChallenge`, `mfa_setup_required`)
  peuvent se contredire ;
- `/auth/me` peut renvoyer 401 transitoire ;
- grâce MFA basée sur des dates.

**Décision**

Un seul état d’authentification, dérivé :

```text
anonymous | loading | mfa | grace | authenticated | expired
```

---

## 1.8 Formulaires et dialogues

Chaque formulaire a une machine implicite :

```text
idle → dirty → submitting → success | error
```

**Risques**

- double soumission ;
- fermeture pendant sauvegarde ;
- perte de saisie ;
- bouton actif alors que rien n’a changé.

**Décision**

Machine générique `formMachine` :

```text
idle | dirty | submitting | success | error
```

avec :

```text
canSubmit = dirty && !submitting
canClose = !submitting || confirm
```

---

## 1.9 Imports

```text
idle → parsing → preview → committing → done | error
```

**Risques**

- import partiel ;
- doublons ;
- lignes invalides ;
- annulation après commit.

**Décision**

Journaliser chaque batch et rendre l’import **idempotent** par clé externe.

---

## 1.10 Abonnement / Stripe

États probables :

```text
trialing
active
past_due
cancelled
incomplete
```

**Décision**

Utiliser l’état Stripe comme source unique.  
Ne jamais déduire l’abonnement d’un booléen local.

---

## 1.11 Assistant IA

```text
idle
listening
attachments
drafting
preview
executing
error
```

**Risques**

- action proposée puis exécutée sans confirmation ;
- pièces jointes après fermeture ;
- mode vocal concurrent.

**Décision**

Machine unique par conversation, action exécutable seulement depuis `preview`
et après événement `CONFIRM`.

---

## 1.12 Dashboard — période et cache

Machine récemment corrigée :

```text
month | prev | next | year | custom
```

**Risque trouvé**

La clé de cache supprimait la query string :

```text
dashboard/executive?period=month
dashboard/executive?period=prev
```

partageaient la même entrée.

**Décision**

La machine de période doit inclure :

```text
period
cacheKey(period)
requestId
data freshness
```

Ne jamais écrire une réponse dont la période ne correspond plus à l’état courant.

---

## 1.13 Navigation / sidebar

États :

```text
expanded | collapsed
drawer_open | drawer_closed
desktop | mobile
```

**Bug corrigé** : le composant sidebar était recréé à chaque navigation,
ce qui remettait le scroll à zéro.

**Décision**

La position de scroll est un état UI persistant, pas un effet de bord du routeur.

---

## 1.14 Notifications et onboarding

```text
unread | read
onboarding_open | done
```

Moins critiques, mais doivent utiliser les mêmes conventions d’événements.

---

# 2. Contrat cible

Créer une couche `workflow` avec trois niveaux.

## Niveau 1 — Descripteurs de domaine

```js
SALE_PHASES
PROJECT_STATES
COMMISSION_STATES
CHALLENGE_STATES
```

Chaque descripteur contient :

```text
id
label
phase
terminal
billable
commissionable
projectVisible
planningVisible
allowedActions
```

## Niveau 2 — Fonctions pures

```text
salePhase(status)
projectState(project)
commissionState(sale)
canDeleteSale(sale, project)
canCloseProject(project)
canEditChallenge(challenge)
```

## Niveau 3 — Événements

```text
SALE_STATUS_CHANGED
PROJECT_SCHEDULED
PROJECT_COMPLETED
PROJECT_CANCELLED
COMMISSION_PAID
CHALLENGE_CLOSED
SYNC_STARTED
AUTH_MFA_REQUIRED
```

Ces noms doivent être identiques :

- backend ;
- frontend ;
- tests ;
- audit ;
- documentation agent.

---

# 3. Décisions de non-changement

Pour ne rien casser :

```text
Les statuts de vente restent configurables.
Les transitions libres de vente restent autorisées.
Aucune donnée existante n'est migrée.
Les statuts personnalisés gardent leur libellé et leur ordre.
Les routes et les payloads ne changent pas.
```

On ajoute des **phases calculées** et des **gardes** sans imposer un graphe rigide.

---

# 4. Plan de déploiement

## Phase 0 — Contrats

- ajouter `workflows.js` / `workflows.py` ;
- tests purs ;
- manifeste JSON ;
- aucune modification d’UI.

## Phase 1 — Lecture

- les pages utilisent les sélecteurs pour les libellés et les filtres ;
- comportement identique ;
- tests de non-régression.

## Phase 2 — Gardes

- suppression de vente avec chantier ;
- clôture de challenge ;
- paiement de commission ;
- transitions de chantier ;
- réponse 409 avec code stable.

## Phase 3 — Nettoyage

- supprimer les listes de statuts dupliquées ;
- supprimer les booléens contradictoires ;
- ajouter télémétrie.

---

# 5. Critères de réussite

```text
Une seule définition de chaque état
Aucune liste de statuts dupliquée dans les pages
Actions autorisées calculées, pas devinées
Messages de blocage explicites
Manifeste lisible par un agent
Tests de transitions purs
Aucune régression fonctionnelle
```

---

# 6. Mise en œuvre — phase 1

Branchement sans changement de comportement :

```text
Sales.jsx          : CA de recherche via isSaleCountedInCA
Commissions.jsx    : éligibilité via isSaleCommissionable
ProjectDialog.jsx  : vente encaissée via salePhase
```

Le message de suppression de vente est aligné sur la règle backend :
un chantier lié bloque la suppression.

# 7. Conclusion

La meilleure décision n’est pas d’ajouter un moteur de state machine lourd.

C’est de rendre explicites les **phases**, **invariants** et **capacités** déjà
présents dans le code, avec des fonctions pures et un manifeste stable.

Cela améliore l’UX, la DX et l’AX sans imposer un graphe rigide à un produit
dont les statuts de vente sont volontairement personnalisables.
