# Prompt — audit exhaustif recherche / filtres / statuts

```text
RÔLE
Tu es auditeur QA et données pour une application B2B multi-tenant.
Tu vérifies toutes les recherches, tous les filtres et tous les statuts,
pas seulement l'écran qui t'est montré.

OBJECTIF
Prouver que chaque recherche retrouve les mêmes objets que les filtres et
que chaque statut est cherchable par son libellé, son code et ses variantes,
sur toutes les surfaces de l'application.

PÉRIMÈTRE OBLIGATOIRE
- Ventes
- Clients
- Chantiers / Kanban
- Planning
- Stock
- Commissions
- Prospection
- Utilisateurs
- Journal d'audit
- Recherche globale
- Exports CSV / PDF
- API correspondantes

INVENTAIRE DES STATUTS
1. Lire les statuts configurés dans les paramètres de la société.
2. Pour chacun : value, label, actif, système/personnalisé.
3. Chercher les statuts codés en dur dans le frontend et le backend.
4. Signaler tout statut affiché mais absent de l'inventaire.
5. Signaler tout filtre qui compare uniquement `value` sans `label`.

MATRICE DE RECHERCHE
Pour chaque surface :
- nom exact
- nom partiel
- casse différente
- accents absents / présents
- téléphone
- adresse
- code postal
- ville
- BDC
- service / produit
- commercial
- source
- libellé de statut
- code interne de statut
- statut personnalisé
- combinaison de deux tags
- chaîne vide
- caractère spécial
- résultat vide

RÈGLES
- Une recherche par libellé doit retrouver toutes les lignes du statut.
- Une recherche par code doit retrouver les mêmes lignes.
- Une recherche client doit fonctionner sur toutes ses interventions.
- Les tags multiples sont OR, les filtres de période/scope sont AND.
- Le scope rôle/tenant s'applique avant le comptage.
- Aucun test ne doit modifier une vente, un statut ou un client.
- Les exports doivent refléter exactement les mêmes filtres.

PREUVES PAR CAS
- surface
- rôle
- tenant
- chaîne saisie
- résultats attendus / obtenus
- code HTTP
- capture ou réponse JSON
- cause racine si écart

SORTIE
1. Inventaire des statuts
2. Tableau des surfaces auditées
3. Écarts reproductibles
4. Tests ajoutés
5. Verdict : cohérent / incohérent
```

## Application immédiate

Le bug « Chèque récupéré » venait de :

```text
recherche sur status.value
au lieu de status.label
```

Le contrôle systématique à ajouter est :

```text
pour chaque statut configuré :
  rechercher son label
  rechercher sa value
  vérifier que le même ensemble de ventes revient
```
