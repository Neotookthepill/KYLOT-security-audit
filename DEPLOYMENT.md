# Livraison KYLOT — procédure contrôlée

Cette procédure vise un déploiement mono-utilisateur sûr et réversible. Une exécution réussie ne dispense pas de vérifier le parcours métier sur l'environnement de staging.

## 1. Conditions de passage

Le déploiement est bloqué si l'un de ces points échoue :

- CI verte sur le commit exact à livrer ;
- `python3 backend/preflight.py --strict` réussi avec les variables de production ;
- sauvegarde MongoDB récente et restauration déjà testée ;
- HTTPS actif sur le front et l'API ;
- en-têtes de sécurité vérifiés sur **la page HTML du frontend**, pas seulement sur l'API ;
- `/health` et `/ready` répondent correctement en staging ;
- connexion, déconnexion, renouvellement de session et droits d'accès validés ;
- création/modification d'un client et d'un prospect validées ;
- upload et export PDF validés avec un fichier normal et un fichier trop volumineux ;
- fonctions IA, email et Stripe validées si elles sont activées ;
- secret du webhook Stripe configuré depuis l'endpoint de production, pas depuis le poste local.
- événements Stripe `checkout.session.*`, `invoice.*`, `customer.subscription.updated/deleted`, `charge.refunded` et `charge.dispute.created` activés et testés en staging ;
- deux transferts de stock simultanés testés contre un vrai MongoDB (pas uniquement `mongomock`).
- aucun doublon `(company_id, product_key)` présent dans `stock`, afin que l'index unique puisse être créé au démarrage.

Avant le déploiement, exécuter sur une copie sauvegardée puis sur la cible cette détection non destructive :

```javascript
db.stock.aggregate([
  { $match: { product_key: { $type: "string" } } },
  { $group: { _id: { company_id: "$company_id", product_key: "$product_key" }, count: { $sum: 1 }, ids: { $push: "$id" } } },
  { $match: { count: { $gt: 1 } } }
])
```

Le résultat doit être vide. S'il ne l'est pas, ne supprimer aucune ligne automatiquement : comparer les quantités, détenteurs et mouvements, fusionner sous contrôle métier, refaire une sauvegarde puis relancer le contrôle.

## 2. Configuration production minimale

Utiliser `backend/.env.example` comme inventaire, jamais comme fichier de production. Les secrets doivent venir du gestionnaire de secrets de l'hébergeur.

Réglages obligatoires :

- `ENVIRONMENT=production`
- `FRONTEND_URL=https://…`
- `CORS_ORIGINS=https://…` sans `*`
- `ALLOW_PUBLIC_REGISTRATION=false`
- `ALLOW_DEMO_DATA=false`
- `ALLOW_TOKEN_RESPONSE=false`
- `RUN_STARTUP_MIGRATIONS=false`
- `EXPOSE_API_DOCS=false`
- `COOKIE_SECURE=true`
- `COOKIE_SAMESITE=lax` ; le mode `none` est refusé tant qu'une protection CSRF dédiée n'existe pas
- `ALLOW_EXTERNAL_GEOCODING=false` sauf validation juridique explicite du transfert d'adresses au service tiers
- `ALLOW_EXTERNAL_AI=false` par défaut ; activer seulement après validation du fournisseur, du contrat/DPA et de l'information des utilisateurs
- `MAX_INLINE_IMAGE_BYTES=4194304` et `MAX_PHOTOS_PER_ENTITY=20` (adapter uniquement après test de charge)
- `PHOTO_ALLOWED_HOSTS=` ou une liste explicite d'hôtes HTTPS approuvés ; une liste vide interdit les images distantes
- `TRUST_PROXY_HEADERS=false`, sauf si le proxy de confiance remplace lui-même `X-Forwarded-For`
- limites d'import et d'IA renseignées à partir de `backend/.env.example`
- `JWT_SECRET` aléatoire, unique, d'au moins 32 caractères
- mots de passe admin et super-admin longs, uniques et différents

Ne pas réutiliser une clé ou un mot de passe de staging en production.

### En-têtes du frontend statique

Les en-têtes ajoutés par FastAPI protègent les réponses de l'API, mais ne protègent pas automatiquement le fichier `index.html` servi par l'hébergeur du frontend. Configurer sur ce dernier, puis vérifier depuis l'extérieur :

- `Strict-Transport-Security: max-age=31536000; includeSubDomains` ;
- `X-Content-Type-Options: nosniff` ;
- `X-Frame-Options: DENY` et `Content-Security-Policy` avec `frame-ancestors 'none'` ;
- `Referrer-Policy: strict-origin-when-cross-origin` ;
- `Permissions-Policy: camera=(), microphone=(), geolocation=()` ;
- une CSP adaptée aux seuls domaines réellement utilisés. La CSP doit prévoir l'API KYLOT et, tant qu'ils ne sont pas auto-hébergés, Google Fonts, `api-adresse.data.gouv.fr` et les tuiles OpenStreetMap. Ne jamais utiliser `*` pour simplifier.

Le dépôt ne connaît pas le proxy/CDN final : cette protection ne peut donc être déclarée validée qu'après contrôle des réponses HTTP publiques de production.

## 3. Déploiement progressif

1. Geler le commit candidat et conserver l'identifiant de l'image ou du build.
2. Sauvegarder MongoDB avant toute mise à jour.
3. Exécuter une fois `python -m backend.migrate --apply` sur la cible sauvegardée. La commande refuse une exécution concurrente et journalise son état dans `migration_runs`.
4. Déployer en staging avec une copie anonymisée ou un jeu de test, jamais avec des données client brutes.
5. Exécuter le pré-vol strict puis les tests métier de la section 1.
6. Déployer en production sans modifier simultanément le code et les secrets, sauf rotation planifiée.
7. Vérifier immédiatement `/health`, `/ready`, les erreurs serveur, la connexion et un parcours métier sans effet financier.
8. Surveiller les erreurs 4xx/5xx, la latence, MongoDB, l'envoi d'emails et les webhooks Stripe pendant au moins une heure.

## 4. Retour arrière

Revenir au build précédent si la disponibilité, l'authentification, l'isolation des données ou la facturation sont affectées.

1. Stopper les opérations automatiques qui pourraient continuer à écrire.
2. Redéployer l'image précédente, sans effacer la base.
3. Si le format de données a changé, appliquer la procédure de restauration testée ; ne jamais improviser une suppression en production.
4. Vérifier `/ready`, la connexion et les données d'un compte de contrôle.
5. Consigner l'heure, le commit, le symptôme et la décision.

## 5. Vérifications sécurité avant ouverture

- Confirmer qu'aucun secret réel n'existe dans Git, les logs, les archives ZIP ou le bundle front.
- Faire tourner les clés qui ont déjà été partagées hors du gestionnaire de secrets.
- Limiter les accès MongoDB et Stripe au strict nécessaire.
- Activer les sauvegardes et alertes de disponibilité.
- Tester qu'un utilisateur ne peut ni lire ni modifier l'identifiant d'une autre société.
- Tester le refus des types et tailles de fichiers interdits.
- Conserver les journaux de sécurité sans contenu client sensible ni jeton d'authentification.

## 6. Risques résiduels connus

- Le backend reste un monolithe volumineux ; sa séparation en couches doit être progressive après sécurisation des parcours critiques.
- La suite automatisée backend ne couvre pas encore MongoDB, Stripe et Emergent de bout en bout.
- Le verrou optimiste des stocks est couvert en mémoire, mais doit encore être validé avec deux processus contre la même instance MongoDB de staging.
- Le frontend charge actuellement des polices Google et la carte utilise `api-adresse.data.gouv.fr` ainsi que les tuiles OpenStreetMap. Ces appels exposent au minimum l'adresse IP, l'agent utilisateur et la zone ou commune consultée aux fournisseurs concernés. Les documenter, les autoriser dans la CSP et la politique de confidentialité, ou auto-héberger/remplacer ces ressources.
- L'audit Yarn du 18 octobre 2026 ne trouve aucune vulnérabilité connue sur 209 paquets, mais signale plusieurs résolutions forcées incompatibles avec les plages demandées par l'ancien arbre Create React App. Le build et les tests passent ; une migration planifiée vers un outillage maintenu reste recommandée.
- `backend/requirements.txt` conserve `emergentintegrations`, qui n'est pas disponible sur l'index Python public. L'audit de l'environnement installé ne trouve aucune vulnérabilité connue, mais ce paquet privé doit être contrôlé dans l'image réelle de déploiement.
- Les bases de vulnérabilités évoluent : les audits Python et JavaScript doivent être rejoués sur le commit et l'image exacts à livrer.

Ces risques empêchent de parler de sécurité absolue. Ils doivent être suivis, avec priorité aux tests d'isolation multi-tenant et aux parcours de paiement avant l'ouverture à plusieurs utilisateurs.
