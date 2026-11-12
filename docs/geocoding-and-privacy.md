# Géocodage — décision et données transmises

## Décision actuelle

Le géocodage externe est **activé** pour les environnements qui doivent proposer
la recherche d’adresse et la carte.

Configuration :

```text
ALLOW_EXTERNAL_GEOCODING=true
```

Service utilisé :

```text
data.geopf.fr
```

## Données transmises

### Complétion code postal / ville

Le frontend appelle uniquement le proxy serveur :

```text
GET /api/geocode?q=<code postal ou ville>
```

Le serveur refuse toute chaîne qui n’est pas :

```text
un code postal à 5 chiffres
ou un nom de ville
```

Aucune adresse complète, aucun nom, aucun téléphone et aucun email ne sont
transmis pour cette fonction.

### Carte clients

Lorsque la carte est utilisée avec le géocodage activé, le serveur peut envoyer
l’adresse complète d’un client au service de géocodage afin d’obtenir ses
coordonnées.

## Données non transmises

```text
nom du client
téléphone
email
notes
données de vente
données de commission
```

## Si le client refuse le transfert

Configurer :

```text
ALLOW_EXTERNAL_GEOCODING=false
```

Conséquences :

```text
autocomplétion code postal / ville désactivée
géocodage de la carte désactivé
saisie manuelle conservée
```

## À intégrer à la politique de confidentialité

La politique de confidentialité publiée doit mentionner :

```text
le recours à data.geopf.fr
les catégories de données transmises
la finalité : compléter une adresse / placer un point sur une carte
la possibilité de désactiver le service
```
