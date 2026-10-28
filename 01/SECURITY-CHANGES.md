# KYLOT — Correctifs de sécurité, passes 1 à 10

Cette copie de travail applique neuf passes de correctifs identifiés pendant l'audit. Le ZIP original fourni par l'utilisateur n'a pas été modifié.

## Correctifs appliqués

1. **Inscription publique fermée par défaut**
   - `/api/auth/register` retourne désormais `403` sauf si `ALLOW_PUBLIC_REGISTRATION=true` est explicitement défini.
   - En production, ne pas définir cette variable. Les utilisateurs doivent être créés par un administrateur.

2. **Contrôle de propriété sur les clients et prospects**
   - Les mutations de clients partagent maintenant le même scope `own` que la liste.
   - Un utilisateur limité à ses propres données ne peut agir que sur un client lié à ses ventes ou créé par lui.
   - Les mutations, suppressions et conversions de prospects vérifient `assigned_to`.
   - Un utilisateur limité à `own` ne peut pas réassigner un prospect à une autre personne.

3. **Protection de la mémoire IA d'entreprise**
   - Le passage d'une mémoire personnelle vers `company` est désormais réservé aux administrateurs et responsables.
   - `user_id` est recalculé lors d'un changement de scope afin d'éviter une mémoire personnelle sans propriétaire ou une règle entreprise portant encore un propriétaire utilisateur.

4. **Suppression des JWT dans les URL PDF**
   - Les routes PDF utilisent maintenant `get_current_user`, avec révocation de session et suspension d'abonnement.
   - Le paramètre `?token=` a été supprimé.
   - Le frontend télécharge les PDF par Axios avec l'en-tête d'authentification, puis crée localement le fichier.

## Passe 2 — Entrées, paiement et exploitation

5. **Uploads bornés côté serveur**
   - lecture limitée à 10 Mo par défaut au lieu d'un chargement intégral non borné ;
   - maximum de 5 fichiers par requête IA ;
   - maximum de 10 pages par PDF ;
   - limite générale de requête de 20 Mo via `Content-Length` ;
   - limites configurables par variables d'environnement.

6. **Redirections Stripe protégées**
   - les URLs de retour du checkout et du portail sont validées contre `FRONTEND_URL` et `STRIPE_RETURN_ORIGINS` ;
   - une origine arbitraire fournie par le navigateur est refusée ;
   - `company_id` est désormais conservé sur les nouvelles transactions.

7. **Webhook Stripe renforcé**
   - taille du payload limitée à 1 Mo ;
   - index Mongo unique ajouté sur `stripe_events.event_id` pour garantir l'idempotence au niveau base.

8. **CORS fail-closed**
   - `*` est interdit en production ;
   - seules les origines configurées sont acceptées ;
   - méthodes et en-têtes autorisés explicitement.

9. **En-têtes HTTP défensifs**
   - `nosniff`, interdiction d'iframe, politique de referrer et permissions navigateur ;
   - HSTS en production.

10. **Readiness MongoDB**
    - `/health` reste une liveness légère ;
    - `/ready`, `/readyz` et `/api/ready` vérifient réellement MongoDB et retournent 503 si la base est indisponible.

11. **Configuration documentée**
    - ajout de `backend/.env.example` et `frontend/.env.example` sans secrets.

## Passe 3 — Sessions navigateur

12. **JWT retiré du stockage JavaScript**
    - le frontend ne conserve plus `pylot_token` dans `localStorage` ;
    - les anciennes clés sont supprimées au chargement et l'utilisateur devra se reconnecter une fois après déploiement ;
    - les exports CSV et PDF utilisent désormais le client HTTP central avec cookie.

13. **Cookie de session HttpOnly**
    - login et inscription placent l'access token dans un cookie `HttpOnly` ;
    - `Secure` est activé par défaut en production ;
    - `SameSite=lax` est utilisé par défaut pour limiter les requêtes cross-site ;
    - Axios envoie les credentials et CORS accepte les credentials uniquement depuis les origines explicitement autorisées.

14. **Compatibilité API préservée**
    - le token reste temporairement présent dans la réponse JSON pour les scripts/tests existants ;
    - le frontend officiel l'ignore et ne le stocke jamais.

## Passe 4 — Rétention et suppression des données

15. **Expiration automatique des données IA temporaires**
    - le contexte récent IA reçoit une expiration MongoDB à 30 minutes ;
    - les actions KIKS en attente expirent après 15 minutes ;
    - une action expirée est refusée même avant le passage du job TTL MongoDB.

16. **Suppression complète d'une entreprise**
    - registre central de 27 collections tenantées ;
    - suppression des prospects, notifications, journal, événements, absences, réinterventions, stock, préférences et données IA qui restaient auparavant orphelins ;
    - suppression des collections enfants avant l'entreprise pour permettre une reprise sûre ;
    - retour du nombre d'éléments supprimés par collection ;
    - conservation d'une preuve globale minimale dans `company_deletion_log`.

17. **Index multi-tenant**
   - index `company_id` ajouté sur chaque collection tenantée pour accélérer les requêtes et les suppressions ;
   - index TTL ajouté aux contextes IA et actions en attente.

## Passe 5 — Build, dépendances et garde-fous de livraison

18. **Build frontend strict remis au vert**
   - correction des dépendances manquantes des hooks React dans Commissions, ZoomableImage, Progression, Stock et Dashboard ;
   - build `CI=true` désormais réussi sans avertissement de compilation ;
   - ajout de six tests unitaires sur les règles de permissions frontend.

19. **Installation reproductible et dépendances critiques traitées**
   - ajout du lockfile Yarn et contrôle `--frozen-lockfile` ;
   - mises à jour ciblées des dépendances directes et résolutions transitives, sans migration forcée du framework ;
   - réduction de l'audit frontend de 103 avis, dont 2 critiques et 70 élevés, à 28 avis transitifs : 0 critique, 14 élevés et 14 modérés ;
   - les avis restants concernent principalement l'ancienne chaîne de build Create React App et sont documentés comme dette résiduelle.

20. **CI de livraison**
   - tests et build frontend sur chaque push et pull request ;
   - compilation syntaxique Python et tests du pré-vol ;
   - blocage explicite si Yarn signale une vulnérabilité critique de production ;
   - permissions GitHub Actions limitées à la lecture.

21. **Pré-vol de configuration production**
   - validation hors ligne des secrets minimaux, HTTPS, CORS, cookies, inscription, comptes initiaux et cohérence Stripe ;
   - mode strict pour refuser une livraison lorsque les intégrations attendues sont absentes ;
   - aucun secret ni contenu de secret n'est affiché ;
   - cinq tests couvrent les configurations sûres et les principaux cas de refus.

22. **Documentation d'exploitation**
   - README remplacé par des instructions réelles de développement et de validation ;
   - procédure de staging, déploiement progressif, retour arrière et risques résiduels dans `DEPLOYMENT.md`.

## Passe 6 — Incohérences de sécurité et de données

23. **Démarrage non destructif**
   - les données de démonstration et l'équipe fictive ne sont créées que sur opt-in explicite et jamais en production ;
   - la détection des chantiers orphelins journalise désormais le problème sans supprimer de données ;
   - un changement de variable d'environnement ne peut plus créer silencieusement un second admin ni promouvoir un utilisateur en super-admin.

24. **Rappels email strictement isolés**
   - construction des rappels séparée par `company_id` ;
   - recherches clients, ventes, commerciaux et administrateurs limitées à la même société ;
   - les identifiants historiques identiques entre deux sociétés ne peuvent plus provoquer de jointure croisée.

25. **Traitement Stripe récupérable**
   - cycle d'événement `processing` / `processed` / `failed` avec reprise des traitements échoués ou bloqués ;
   - arrêt du webhook si le stockage d'idempotence est indisponible ;
   - rattachement persistant de l'abonnement Stripe à l'utilisateur et à sa société ;
   - suspension, réactivation et résiliation résolues via la transaction tenantée ;
   - refus des lookup keys qui ne figurent pas dans le catalogue KYLOT.

26. **Opérations atomiques et création cohérente**
   - une confirmation KIKS est consommée atomiquement pour empêcher les doubles créations concurrentes ;
   - email administrateur et mot de passe d'une nouvelle société sont validés avant insertion ;
   - compensation de la société nouvellement créée si la création de son administrateur échoue.

27. **Session et CSRF**
   - suppression du refresh token inutilisé ;
   - jeton JSON désactivé par défaut et impossible à activer en production ;
   - inscription publique impossible en production, même en cas de variable erronée ;
   - cookies cross-site refusés en production tant qu'une protection CSRF dédiée n'existe pas.

28. **Défense multi-tenant complémentaire**
   - contexte IA court lu et purgé avec `user_id` et `company_id` ;
   - réconciliation des commerciaux limitée à la société à l'origine de l'action.

## Passe 7 — Chaîne backend, migrations et dernières références inter-entreprises

29. **Dépendances Python publiques assainies**
   - audit de 128 dépendances publiques initiales : 41 avis connus répartis sur huit paquets ;
   - mise à jour ciblée de FastAPI, Starlette, Motor, PyMongo, PyJWT, multidict, oauthlib et urllib3 ;
   - retrait de `ecdsa` et `python-jose`, inutilisés par l'application qui s'appuie sur PyJWT ;
   - nouvel audit de 126 dépendances publiques figées : aucune vulnérabilité connue ;
   - les paquets privés Emergent restent explicitement exclus du verdict public et doivent être contrôlés dans l'image réelle.

30. **Import et démarrage applicatif testés en CI**
   - ajout d'un jeu de dépendances cœur reproductible pour importer l'API sans services privés ;
   - tests de fumée sur les routes, la fermeture de l'inscription, CORS, HSTS, CSP et la désactivation de la documentation API ;
   - validation réelle avec les versions mises à jour de FastAPI, Starlette, Motor, PyMongo et PyJWT.

31. **Migrations sorties du démarrage production**
   - les migrations automatiques sont interdites en production ;
   - ajout de `python -m backend.migrate --apply`, avec verrou logique, statut `running/completed/failed` et reprise contrôlée ;
   - la procédure de livraison impose une sauvegarde avant cette commande.

32. **Brute-force et surface API renforcés**
   - compteur d'échecs de connexion déplacé de la mémoire du processus vers MongoDB ;
   - adresse email remplacée par une clé HMAC non réversible, verrou atomique et expiration TTL ;
   - documentation OpenAPI désactivée sans exception en production ;
   - CSP défensive sur l'API et mots de passe utilisateur portés à 12 caractères minimum.

33. **Références utilisateurs strictement tenantées**
   - participants d'événements dédupliqués puis vérifiés dans la société avant stockage ou notification ;
   - attribution et transfert de stock refusés si la source, le détenteur ou la destination n'appartient pas à la société ;
   - le nom du détenteur provient désormais du compte serveur, pas d'une valeur libre du navigateur.

## Passe 8 — Intégration de sécurité et paquet de livraison minimal

34. **Parcours backend exécutés sur une base jetable**
   - ajout de six tests d'intégration utilisant une base Mongo compatible en mémoire ;
   - vérification de l'injection de `company_id`, de l'isolation des listes, des événements, du stock, du verrouillage de connexion et de la révocation de session ;
   - vérification qu'une migration terminée est journalisée et ne s'exécute pas une seconde fois.

35. **Analyse statique Python dans la CI**
   - Bandit ajouté aux dépendances de test et exécuté à chaque push ;
   - aucun constat de gravité moyenne ou élevée sur le backend ;
   - les vingt alertes faibles restantes sont des faux positifs de mots de passe numériques ou des exceptions tolérées dans des opérations secondaires.

36. **Réduction du contenu livré**
   - le paquet `ship-ready` exclut les anciens rapports QA contenant des identifiants de démonstration historiques ;
   - les anciens scripts d'intégration visant une URL distante sont exclus du paquet de production ;
   - les tests CI actuels, le code, les migrations, les lockfiles et la documentation de déploiement restent inclus.

## Passe 9 — Réduction et verrouillage de la dette frontend

37. **Avis corrigibles supprimés**
   - SVGO forcé vers 2.8.4 et `postcss-selector-parser` vers 7.1.6 ;
   - tests et build production validés avec ces versions malgré l'ancien arbre Create React App ;
   - réduction de 28 à 18 avis : 0 critique, 10 élevés et 8 modérés.

38. **Plafond de sécurité explicite**
   - les dix avis élevés restants concernent uniquement `braces` et les huit modérés uniquement `sprintf-js`, dans les outils de build/test ;
   - aucune version corrigée n'est publiée pour ces deux avis dans l'arbre actuel ;
   - la CI échoue désormais si un autre module élevé apparaît ou si les plafonds 10/8 augmentent.

## Passe 10 — Nouvelle version ZIP (2), contrôle frais

39. **Mode hors ligne sans secret persistant**
   - suppression du stockage local du mot de passe dérivé, du JWT et du profil complet ;
   - abandon de la connexion locale qui pouvait survivre à une révocation serveur ;
   - cache IndexedDB cloisonné par utilisateur et intégralement purgé à la connexion/déconnexion ;
   - seules les modifications PUT/PATCH explicitement hors ligne sont rejouables ; POST/DELETE exigent le réseau pour éviter doublons et suppressions tardives.

40. **Contrôles de périmètre par ligne**
   - lecture directe, modification, suppression, restauration et confirmation d'un chantier soumises au même scope `own` que les listes ;
   - notes, bonus et validation de chantier utilisent le même garde-fou ;
   - suppression d'une vente limitée au filtre canonique du commercial lorsque sa vue est `own` ;
   - trois tests d'intégration couvrent l'IDOR chantier, la suppression de vente hors périmètre et les sources photo actives.

41. **Photos et pièces inline durcies**
   - schémas autorisés limités à HTTPS ou aux data-URI JPEG/PNG/WebP valides ;
   - base64 réellement décodé et borné à 4 Mo par image, 20 images par objet ;
   - métadonnées libres filtrées avant MongoDB ;
   - affichage et téléchargement frontend refusent également les schémas inattendus.

42. **Vie privée et secrets d'automatisation**
   - géocodage externe des adresses clients désactivé par défaut en production et visible dans la réponse API ;
   - notes clients soumises au scope du client ;
   - le cron ne transfère plus son Bearer secret lors d'une redirection vers un autre hôte.

43. **Validation de la nouvelle archive**
   - 39 tests backend et 6 tests frontend réussis ;
   - build production réussi ;
   - 0 vulnérabilité connue dans les dépendances Python publiques et le runtime frontend ;
   - Bandit : 0 constat moyen/élevé ;
   - interface `App`/`Layout` de l'auteur conservée, sans intégration de la proposition visuelle séparée.

## Fichiers modifiés

- `backend/server.py`
- `frontend/src/lib/api.js`
- `frontend/src/pages/Commissions.jsx`
- `frontend/src/pages/MonthlyReport.jsx`
- `frontend/src/contexts/AuthContext.jsx`
- `frontend/src/pages/Sales.jsx`
- `frontend/src/pages/Kanban.jsx`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/pages/Progression.jsx`
- `frontend/src/pages/Stock.jsx`
- `frontend/src/components/ZoomableImage.jsx`
- `frontend/src/lib/permissions.test.js`
- `frontend/package.json`
- `frontend/yarn.lock`
- `frontend/scripts/check-audit.js`
- `backend/.env.example`
- `backend/preflight.py`
- `backend/test_preflight.py`
- `backend/test_security_invariants.py`
- `backend/test_app_smoke.py`
- `backend/requirements-core.txt`
- `backend/requirements-test.txt`
- `backend/requirements.txt`
- `backend/migrate.py`
- `backend/test_integration_security.py`
- `frontend/.env.example`
- `.github/workflows/ci.yml`
- `README.md`
- `DEPLOYMENT.md`

## Vérifications effectuées

- compilation syntaxique Python : réussie ;
- neuf tests du pré-vol, dix invariants de sécurité, quatre tests de fumée et six tests d'intégration backend : réussis, soit 29 contrôles ;
- six tests des permissions frontend : réussis ;
- recherche résiduelle de JWT ajoutés aux URL PDF : aucune occurrence ;
- installation frontend avec lockfile gelé : réussie ;
- build frontend strict `CI=true` : réussi ;
- audit des dépendances frontend : 0 critique, 10 élevés, 8 modérés, tous confinés à l'ancienne chaîne de build/test ;
- audit des 126 dépendances Python publiques figées : aucune vulnérabilité connue ;
- audit des dépendances Python de test : aucune vulnérabilité connue ;
- analyse statique Bandit : aucun constat moyen ou élevé ;
- recherche de secrets à haut risque dans les sources : aucune clé Stripe, Google, MongoDB ou clé privée détectée ; un mot de passe synthétique subsiste dans un test RBAC.

## Important avant déploiement

- Sauvegarder la base et les variables de production.
- Déployer d'abord dans un environnement de test.
- Vérifier la connexion du compte existant, les exports PDF, les clients et les prospects.
- Ne jamais activer `ALLOW_PUBLIC_REGISTRATION` en production.
- Vérifier avant démarrage que les éventuels anciens doublons `stripe_events.event_id` ont été supprimés ; sinon la création de l'index unique échouera, volontairement, plutôt que de continuer sans garantie d'idempotence.
- Si frontend et API sont réellement sur deux sites différents, ne pas basculer aveuglément vers `SameSite=none` : il faudra activer `COOKIE_SECURE=true` et ajouter une protection CSRF dédiée. Le déploiement même-site reste recommandé.
- Les tests d'intégration backend avec une vraie base, l'audit transactionnel, la CSP du serveur frontend et l'audit des paquets privés Emergent restent à traiter.
- Planifier la migration de Create React App dans une branche dédiée pour supprimer les 18 avis de build/test sans version corrigée disponible dans l'arbre actuel.

## Passe 11 — Matrice étendue et entrées hostiles

44. **Isolation multi-entreprises et permissions élargies**
   - 62 appels directs, listes et mutations sont exercés avec deux sociétés et plusieurs rôles ;
   - clients, ventes, chantiers, équipe, primes, utilisateurs, IA, prospects, absences, événements, stock, notifications et statut de paiement sont couverts ;
   - les comptes suspendus, les commerciaux limités à leurs objets et les techniciens sans accès administratif sont vérifiés.

45. **Limites explicites sur les données métier**
   - tailles maximales ajoutées aux principaux textes, collections et imports avant écriture en base ;
   - logo des paramètres contrôlé comme une vraie image et limité aux sources autorisées ;
   - JWT expirés ou malformés, utilisateur supprimé et tentative d'injection d'identité de société couverts par des tests de non-régression.

46. **Contrôles de volume reproductibles**
   - import de 1 000 clients, rejet au-delà de 5 000 lignes, export en flux de 5 000 ventes et isolation de 5 000 clients parmi 10 000 validés sur base en mémoire ;
   - ces mesures servent de garde-fou local et ne remplacent pas une charge sur MongoDB et l'infrastructure réels.

47. **Bilan automatisé au 19 octobre 2026**
   - 109 contrôles de sécurité et robustesse, 40 tests backend standards et 23 tests frontend réussis ;
   - total : 172 tests automatisés réussis (109 sécurité/robustesse, 40 serveur, 23 interface) ;
   - les sept suites de sécurité sont exécutées par la CI.

## Passe 12 — Routes, logique métier et fuzzing structuré

48. **Inventaire automatique de la surface API**
   - 164 routes API inventoriées ;
   - 158 routes protégées appelées sans session et toutes refusées ;
   - inscription, crons et webhook Stripe testés séparément en mode fail-closed.

49. **Dates et heures calendaires**
   - rejet des jours impossibles, mois 13 et heures telles que `25:99` ;
   - validation appliquée aux ventes, absences, réinterventions, jours OFF, jours supplémentaires, heures supplémentaires et commissions.

50. **Cohérence financière et limites profondes**
   - refus d'une part financée supérieure au montant total ;
   - plafonds ajoutés aux prestations, catégories, statuts, tags IA, photos, paramètres, primes, permissions et préférences ;
   - trente-trois groupes de non-régression présents dans `audit/security_route_business_fuzz.py` et dans la CI ;
   - suppression du replay de session tiers, IA externe opt-in, suppression de notes revalidée et distinction Stripe entre paiement, essai et simple fin de session.

## Passe 13 — Recherche, identité hors ligne et mesure de couverture

51. **Recherche globale soumise aux permissions**
   - permissions révoquées et portées `own` appliquées à chaque type de résultat ;
   - annuaire utilisateur absent sans la permission `users.manage`.

52. **Session frontend tolérante aux pannes réseau**
   - une panne temporaire de `/auth/me` ne déconnecte plus un utilisateur déjà confirmé ;
   - un vrai `401` révoque toujours l'identité, la file hors ligne et les données locales sensibles.

53. **Couverture rendue visible**
   - 23 tests frontend couvrent les permissions, l'API, le hors-ligne et le contexte d'authentification ;
   - couverture mesurée de 3,11 % des lignes frontend et de 21 % des instructions serveur par la suite standard : la préproduction reste indispensable.
