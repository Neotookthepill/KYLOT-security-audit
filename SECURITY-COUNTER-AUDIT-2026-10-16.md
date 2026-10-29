# KYLOT — contre-audit technique, sécurité et produit

Date : 16 octobre 2026  
Périmètre : copie locale de `KYLOT-main (2).zip`, après les renforcements déjà documentés  
Méthode : lecture du dépôt, inventaire statique de toutes les routes, tests adversariaux isolés, tests de non-régression et build local  
Contrainte respectée : aucun fichier fonctionnel ou visuel n'a été modifié pendant cette contre-audit

## Résumé simple pour le propriétaire

La nouvelle version est nettement plus solide que le code d'origine : les sessions ne sont plus stockées comme un token lisible dans le navigateur, la séparation entre sociétés est présente dans une grande partie du serveur, les fichiers sont mieux bornés, Stripe vérifie ses signatures et les tests existants restent verts.

Elle n'est toutefois **pas encore prête pour la production**. Cette nouvelle passe a trouvé neuf problèmes distincts qui n'étaient pas comptés dans les deux audits précédents. Les plus importants sont des suppressions irréversibles : supprimer une vente peut supprimer ses chantiers et leurs photos, tandis que supprimer un client peut laisser ses ventes et son historique sans client correspondant. Des données client préparées dans l'assistant IA peuvent aussi rester dans l'onglet après une déconnexion et être relues par l'utilisateur suivant.

Les 13 tests adversariaux de cette passe échouent comme prévu sur l'état actuel. Cela ne représente pas 13 attaques distantes différentes : plusieurs tests démontrent les diverses conséquences d'une même faiblesse. En parallèle, les contrôles normaux restent stables : **39/39 tests serveur, 6/6 tests interface, compilation Python et build de production réussis**.

Verdict : **non prêt pour production**. Une fois les P1 corrigés, les P2 principaux corrigés ou explicitement acceptés, et la campagne staging réussie, le produit pourra passer au stade **pilote limité**.

## Périmètre réellement inspecté

- backend FastAPI et modèles Pydantic ;
- frontend React, session navigateur et mode hors ligne ;
- 172 routes HTTP, dont 102 routes d'écriture ;
- authentification, rôles, permissions et séparation par société ;
- clients, ventes, chantiers, notes, équipe, primes, paramètres et planning ;
- imports CSV/XLSX, exports, photos et PDF ;
- IA, Stripe, emails, cron et redirections ;
- dépendances, build, analyse statique et tests existants ;
- documents des audits précédents, recontrôlés comme des éléments de preuve et non comme des vérités automatiques.

L'inventaire complet route par route se trouve dans `ROUTE-INVENTORY-2026-10-16.md` et la spécification rôle × ressource × portée dans `AUTHORIZATION-MATRIX-2026-10-16.md`. Les colonnes « société », « propriétaire », « audit », « idempotence » et « limite » de l'inventaire sont des marqueurs statiques : une protection placée dans un helper peut ne pas apparaître sur la ligne de route. Une absence dans cette table est donc un signal de revue, pas à elle seule une faille confirmée.

## Nouveaux constats uniquement

### CA3-01 — P1 — Suppression d'une vente destructrice pour les chantiers et photos

**Statut : confirmé par test HTTP local.**

- **Scénario :** un utilisateur autorisé à supprimer une vente supprime une vente déjà reliée à un chantier terminé et à des photos.
- **Prérequis :** session valide et permission `sales.delete` sur la vente.
- **Impact :** le chantier, ses photos et son historique opérationnel sont supprimés sans corbeille, confirmation métier ni restauration dédiée. La traçabilité et des preuves de réalisation peuvent disparaître avec une seule action.
- **Preuve :** `DELETE /api/sales/sale-history` répond `200 {"ok":true}` et le projet `project-history` n'existe plus. La route appelle directement `delete_many` sur les projets liés : `backend/server.py:2437-2448`.
- **Observé :** suppression physique de la vente puis de tous ses projets liés.
- **Attendu :** refus si un historique existe, ou archivage transactionnel/soft-delete avec restauration et politique de rétention.
- **Correction minimale :** remplacer la cascade physique par un statut `archived/deleted_at`; exiger une confirmation renforcée ; conserver photos, chantier et journal ; réserver la purge définitive à une procédure séparée.
- **Non-régression :** `test_deleting_sale_preserves_linked_project_and_photos` dans `audit/security_adversarial_round3.py`.

### CA3-02 — P1 — Suppression d'un client laissant un historique orphelin

**Statut : confirmé par test HTTP local.**

- **Scénario :** un administrateur supprime un client encore référencé par une vente.
- **Prérequis :** session valide et permission `clients.delete`.
- **Impact :** les ventes, chantiers, notes ou exports peuvent conserver un `client_id` qui ne pointe plus vers aucun client. Les écrans et rapports deviennent incohérents et l'historique n'est plus explicable.
- **Preuve :** `DELETE /api/clients/client-live` répond `200`, supprime le client mais ne contrôle pas les collections liées : `backend/server.py:1387-1396`.
- **Observé :** suppression physique sans vérification de dépendances.
- **Attendu :** réponse `409` tant que des données actives dépendent du client, ou anonymisation/archivage cohérent de tout le graphe.
- **Correction minimale :** compter les références avant suppression, bloquer si elles existent et proposer une action d'archivage ; définir séparément l'anonymisation RGPD.
- **Non-régression :** `test_deleting_client_with_history_is_blocked_or_soft_deleted`.

### CA3-03 — P2 — Brouillons IA et données de vente réutilisables par le compte suivant

**Statut : confirmé statiquement ; exploitation réelle à confirmer en E2E multi-compte.**

- **Scénario :** l'utilisateur A prépare avec l'IA une vente contenant nom, téléphone, adresse, montant et conversation, se déconnecte sans fermer l'onglet, puis l'utilisateur B se connecte dans ce même onglet.
- **Prérequis :** navigateur partagé, même onglet et connexion successive de deux comptes.
- **Impact :** exposition de données client et possibilité de reprendre un aperçu/action appartenant à la session précédente. Si les deux comptes appartiennent à des sociétés différentes, cela devient une fuite inter-entreprises côté navigateur.
- **Preuve :** clé globale `kylot_ai_draft_v1` dans `frontend/src/components/AIHelper.jsx:22`, lecture/écriture globale aux lignes `335-342` et `429-438`; préremplissage client dans `kylot_prefill_sale` aux lignes `561-585`. La déconnexion aux lignes `frontend/src/contexts/AuthContext.jsx:72-77` nettoie IndexedDB mais pas `sessionStorage`.
- **Observé :** les clés ne contiennent ni `user_id` ni `company_id` et ne sont pas supprimées au logout.
- **Attendu :** aucune donnée A visible ou exécutable après la connexion de B.
- **Correction minimale :** supprimer ces deux clés à toute déconnexion et avant toute nouvelle identité ; idéalement partitionner les clés par `company_id:user_id` et ne jamais restaurer un aperçu d'action sans revalidation serveur.
- **Non-régression :** `test_ai_session_draft_is_partitioned_by_authenticated_user` et `test_logout_clears_sensitive_session_storage`.

### CA3-04 — P2 — Expiration automatique de session sans purge locale

**Statut : confirmé statiquement ; impact E2E à confirmer.**

- **Scénario :** le cookie expire ou le compte est désactivé pendant que l'application est ouverte ; une requête reçoit `401` et redirige vers la connexion.
- **Prérequis :** session expirée/révoquée et données déjà mises en cache ou préparées.
- **Impact :** les données hors ligne et brouillons peuvent rester sur l'appareil alors que l'identité serveur n'est plus valide. Le prochain utilisateur local peut retrouver des informations de l'ancien compte.
- **Preuve :** l'intercepteur `401` redirige mais n'appelle ni `clearOfflineData` ni une purge des clés de session : `frontend/src/lib/api.js:67-82`.
- **Observé :** redirection uniquement.
- **Attendu :** purge locale sûre, réinitialisation de l'identité et redirection.
- **Correction minimale :** centraliser `clearSensitiveClientState(reason)` et l'appeler au logout explicite, au `401`, au changement d'utilisateur et au changement de société.
- **Non-régression :** `test_automatic_session_expiry_clears_offline_and_draft_data`.

### CA3-05 — P2 — Imports CSV/XLSX non bornés après l'upload

**Statut : confirmé par validation locale et lecture du parseur.**

- **Scénario :** un compte autorisé importe un XLSX compressé contenant énormément de lignes/colonnes, ou appelle l'étape d'exécution avec un tableau JSON gigantesque et des cellules très longues.
- **Prérequis :** session valide et permission de création de clients.
- **Impact :** consommation mémoire/CPU, réponse très volumineuse et indisponibilité locale ou du processus. La limite sur les octets uploadés ne borne pas le nombre de cellules après décompression.
- **Preuve :** `_read_xlsx_bytes` itère toute la feuille sans `max_row/max_column` (`backend/server.py:1586-1599`); l'aperçu retourne aussi `rows_full` en entier (`1602-1634`); `ClientImportExecuteIn` ne borne ni mapping, ni lignes, ni colonnes, ni longueur de cellule (`1637-1648`). Un modèle de 100 000 lignes contenant des cellules de 100 000 caractères est accepté par Pydantic.
- **Observé :** aucune erreur de validation avant traitement.
- **Attendu :** rejet rapide avant allocation/traversée excessive et réponse limitée au seul aperçu.
- **Correction minimale :** limites explicites de lignes, colonnes, caractères par cellule, taille JSON et temps de parsing ; ne jamais renvoyer `rows_full` au navigateur ; conserver temporairement l'import côté serveur avec identifiant opaque.
- **Non-régression :** trois tests `test_client_import_*`, `test_import_preview_*` et `test_xlsx_parser_*`.

### CA3-06 — P2 — Verrouillage de compte déclenchable par un tiers et absence de frein par source

**Statut : confirmé par test HTTP local.**

- **Scénario :** un tiers connaît l'email d'un utilisateur, envoie cinq mots de passe faux, puis l'utilisateur légitime tente son vrai mot de passe.
- **Prérequis :** connaissance de l'adresse email ; aucun compte attaquant requis.
- **Impact :** déni de service ciblé de 15 minutes, répétable. À l'inverse, la défense par email seule ne borne pas clairement une campagne de mots de passe pulvérisés sur de nombreux comptes depuis une même source.
- **Preuve :** après cinq échecs, le vrai mot de passe reçoit `429` avec environ 14 minutes restantes. Le compteur ne dépend que du HMAC de l'email : `backend/server.py:827-895`; la route de login est aux lignes `898-906`.
- **Observé :** le mécanisme anti-bruteforce fonctionne, mais l'attaquant peut verrouiller la victime.
- **Attendu :** ralentissement progressif et limites combinées compte + source, sans offrir un verrouillage durable facile à provoquer.
- **Correction minimale :** ajouter un limiteur distribué par IP/source fiable derrière proxy, un plafond global et une alerte ; préférer backoff progressif/CAPTCHA après seuil plutôt qu'un verrou dur uniquement par compte.
- **Non-régression :** `test_correct_password_is_not_denied_by_an_attacker_lockout` et `test_login_defence_includes_source_level_throttling`.

**Qualification importante :** le verrouillage existant est bien une protection, pas une « absence de sécurité ». Le défaut est son arbitrage disponibilité/sécurité et son caractère déclenchable par un tiers.

### CA3-07 — P2 — Un chantier d'une journée future peut être terminé immédiatement

**Statut : confirmé par test HTTP local.**

- **Scénario :** un technicien assigné termine aujourd'hui un chantier planifié au `2099-01-01`.
- **Prérequis :** technicien assigné au chantier et au moins une photo acceptée.
- **Impact :** planning, statut de vente, notifications et preuve d'exécution deviennent faux ; une facturation ou un encaissement pourrait être déclenché trop tôt.
- **Preuve :** la route répond `200` et écrit `status="termine"`. Le contrôle de date future n'existe que dans la branche `len(pdays) > 1` : `backend/server.py:10071-10145`, particulièrement `10126-10141`.
- **Observé :** chantier mono-jour futur terminé.
- **Attendu :** refus `400` pour toute journée future, mono-jour ou multi-jours.
- **Correction minimale :** calculer le jour concerné avant la branche, puis appliquer une seule validation de date.
- **Non-régression :** `test_single_day_future_project_cannot_be_completed_early`.

### CA3-08 — P2 — Opérations sensibles sans journal d'audit

**Statut : confirmé statiquement pour les fonctions listées.**

- **Scénario :** import massif, création/modification/suppression d'un membre, modification d'une prime ou des paramètres de société.
- **Prérequis :** compte disposant de la permission correspondante.
- **Impact :** après erreur, abus ou compromission, il manque une preuve applicative complète indiquant qui a changé quoi et quand. Les retours arrière et investigations deviennent difficiles.
- **Preuve :** aucun appel `log_audit` dans `execute_import_file`, `create_team_member`, `update_team_member`, `delete_team_member`, `create_bonus`, `update_bonus`, `delete_bonus`, `update_settings`. Exemples : `backend/server.py:1651-1675`, `4864-4977`, `5997-6049`, `6307-6317`.
- **Observé :** écriture métier sans entrée d'audit explicite.
- **Attendu :** journal immuable avec acteur, société, ressource, avant/après ou résumé, horodatage et corrélation.
- **Correction minimale :** enveloppe commune pour les écritures sensibles ; pour les imports, journaliser fichier haché, nombre créé/modifié/ignoré et stratégie, sans copier les données personnelles complètes.
- **Non-régression :** `test_sensitive_configuration_and_bulk_writes_are_audited`.

`update_user` n'est pas recompté ici : son absence d'audit figurait déjà dans la campagne précédente.

### CA3-09 — P3 — Une permission de lecture autorise l'écriture d'une note client

**Statut : confirmé techniquement ; décision produit nécessaire.**

- **Scénario :** un commercial possède `clients.view=own` mais `clients.edit=false`, puis ajoute une note à son propre client.
- **Prérequis :** accès en lecture au client concerné.
- **Impact :** la matrice de permissions ne reflète pas le comportement réel. Si une note est considérée comme modification du dossier client, un rôle lecture seule peut écrire du contenu, potentiellement trompeur ou sensible.
- **Preuve :** le test reçoit `200`; la route vérifie `clients.view` et insère la note : `backend/server.py:1412-1422`.
- **Observé :** écriture accordée malgré `clients.edit=false`.
- **Attendu :** `403`, ou permission dédiée `client_notes.create` documentée et visible dans l'administration.
- **Correction minimale :** décider la politique. Si les lecteurs doivent collaborer, créer une permission explicite ; sinon exiger `clients.edit`.
- **Non-régression :** `test_client_view_permission_does_not_grant_note_write_permission`.

Ce point est classé P3 car le comportement peut être volontaire. Il ne doit pas être présenté comme une brèche confirmée tant que la règle métier n'est pas tranchée.

## Comparaison avec les audits précédents

| Passe | Ce qu'elle a surtout établi | Ce que la contre-audit ajoute |
|---|---|---|
| Audit initial | cookies/sessions, IDOR principaux, fichiers, rejeu hors ligne, configuration de production, Stripe/cron/redirections, géocodage et dépendances | ne remet pas en cause ces correctifs ; vérifie qu'ils restent présents |
| Matrice et passe adversariale 1 | homonymes, historique sans identifiants canoniques, révocation après changement de mot de passe, photos distantes/magic bytes, index/concurrence, IA/PII, stockage hors ligne | évite de recompter ces défauts et cherche les opérations destructrices et la transition entre utilisateurs |
| Passe 2 | CSV actif, regex IA, coût IA, stock, route globale, confidentialité interne, dates/nombres non finis, erreurs et exports mémoire | ajoute suppressions incohérentes, persistance des brouillons, import décompressé non borné, verrouillage ciblé, date future mono-jour et audit manquant |

### Faux positifs et corrections de gravité

- **13 tests en échec ne signifient pas 13 brèches distantes.** Ils se regroupent en neuf constats, dont un P3 dépend de la politique produit.
- **Le verrouillage de connexion protège réellement contre le bruteforce.** Le risque nouveau est le déni de service ciblé et l'absence de limite complémentaire par source.
- **`sessionStorage` n'est pas partagé entre tous les navigateurs et disparaît à la fermeture de l'onglet.** Le scénario CA3-03 nécessite le même onglet sur un appareil partagé ; sa gravité reste donc P2, pas P0/P1.
- **L'ajout de note avec permission de lecture peut être intentionnel.** Sans règle produit écrite, il reste P3.
- **L'inventaire statique de route peut sous-détecter un contrôle placé dans un helper.** Seuls les constats reproduits ou vérifiés dans le corps des fonctions sont qualifiés de confirmés.
- **Les anciens scripts contenant une URL et des identifiants ressemblant à un environnement de prévisualisation restent un P0 conditionnel déjà signalé.** Il faut vérifier leur validité et effectuer une rotation si nécessaire, mais cette passe ne les recompte pas comme nouveau problème.

## Cartographie des rôles et opérations critiques

L'application utilise principalement `super_admin`, `admin`, `responsable`, `commercial`, `technicien` et `sous_traitant`, complétés par des permissions par ressource et parfois une portée `own/team/all`.

| Ressource / action | Admin / responsable | Commercial | Technicien / sous-traitant | Risque restant vérifié |
|---|---|---|---|---|
| Clients — lecture | société selon permission | propres clients selon scope | selon permission | routes principales filtrées ; lectures secondaires à revoir selon audit 2 |
| Clients — création/édition | selon permission | selon permission | normalement refusé | note client utilise `view` au lieu d'une permission d'écriture |
| Clients — suppression | selon permission | selon permission configurée | normalement refusé | suppression physique avec dépendances non contrôlées |
| Ventes — lecture/édition | société | propres/équipe/toutes selon scope | normalement refusé | anciens homonymes déjà signalés |
| Ventes — suppression | selon permission | selon scope et permission | refus attendu | cascade physique vers les chantiers |
| Chantiers — lecture/action | société | selon permission | assignés | date future mono-jour contournable ; homonymes déjà signalés |
| Équipe/utilisateurs | administration | lecture partielle | lecture trop large déjà signalée | plusieurs mutations équipe sans audit |
| Primes/paramètres | manager/permission | lecture selon endpoints | lecture trop large déjà signalée | mutations sans audit |
| Imports/exports | permission dédiée | possible selon droits | refus attendu | import décompressé/JSON non borné ; CSV actif déjà signalé |
| IA | selon rôles et capacités | actions vente/client selon droits | chat selon exposition | brouillon local non partitionné ; limites/coût déjà signalés |
| Paiement/Stripe | admin et webhook signé | pas d'administration | aucun | tests externes encore requis |

### États de compte

| État | Couverture locale | Conclusion |
|---|---|---|
| Actif | tests serveur et adversariaux | largement couvert localement |
| Désactivé | protection hors ligne et lecture serveur déjà testées dans les passes précédentes | correction présente, E2E staging à refaire |
| Supprimé | révocation et résidus locaux partiellement couverts | transition navigateur encore incomplète |
| Mot de passe changé | sessions existantes déjà signalées dans la passe précédente | pas recompté ; correction/révocation à valider |
| Session expirée (`401`) | nouveau contrôle statique | purge locale absente |
| Deux sociétés successives dans le même onglet | test statique du stockage, pas d'E2E réel | CA3-03 à reproduire sur staging |

## Matrice des scénarios couverts et non couverts

| Domaine | Couvert localement dans les trois campagnes | Reste à vérifier honnêtement |
|---|---|---|
| Authentification | cookie HttpOnly, inscription prod, brute-force par compte, désactivation, expiration statique | timing/énumération à grande échelle, MFA admin, proxy réel, sessions simultanées |
| Autorisations | plusieurs IDOR société/propriétaire, homonymes, notes, rôles secondaires | matrice E2E complète de chaque route avec deux sociétés et tous les rôles |
| Valeurs limites | vide, négatif, dates invalides, NaN, longueurs IA/import, futur | Unicode/invisibles sur tous les champs, arrondis financiers exhaustifs |
| Rejeu/idempotence | offline, Stripe statique, certaines créations/suppressions | concurrence réelle multi-processus et pannes entre deux écritures |
| Clients/ventes/chantiers | CRUD critique, suppressions liées, fin de chantier | restauration métier complète, facturation réelle et gros historiques |
| Fichiers/photos | taille/nombre, types, URL distante, magic bytes statique | polyglottes, EXIF, bombes images/PDF avec sandbox dédiée |
| Imports/exports | CSV actif, parseurs, dimensions, mémoire statique | fichiers malformés variés, mesure CPU/RAM, grands volumes réels |
| IA | regex, validation d'action, persistance locale, taille/coût statique | fournisseur réel, prompt injection multimodale, timeout, quota, conservation |
| Stripe | signature, tenant et idempotence dans le code/tests locaux | sandbox Stripe : ordre, retard, replay concurrent, refund, chargeback, impayé |
| Emails/cron | secrets, rôles et construction statique | délivrabilité, rebonds, injection HTML finale, limitation d'envoi |
| Frontend/offline | token retiré, purge logout IndexedDB, brouillons de session | deux navigateurs, service worker, crash/reprise, conflits réels |
| Déploiement | build, variables, CORS et headers applicatifs partiels | TLS/proxy, CSP/HSTS effectifs, logs, alertes, sauvegarde/restauration |

## Résultats reproductibles

### Nouvelle campagne

Commande :

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest audit.security_adversarial_round3 -v
```

Résultat : **13 tests exécutés, 13 échecs attendus sur le comportement actuel**. Les échecs prouvent que les garde-fous décrits par les tests ne sont pas encore présents.

### Non-régression

- serveur : **39/39 réussis** ;
- interface : **6/6 réussis** ;
- compilation Python : réussie ;
- build frontend de production : réussi ;
- analyse statique backend Bandit : **0 haute, 0 moyenne, 21 faibles** ; les faibles sont surtout des `try/except/pass` et un faux positif de mot de passe littéral `"0"` ;
- audit Python : une exécution précédente sur le même `requirements.txt` indiquait **0 vulnérabilité connue** ; la relance de cette passe n'a pas abouti à cause de l'environnement local de cache/mise à niveau, donc elle n'est pas présentée comme une nouvelle confirmation ;
- audit JavaScript : pas de `package-lock.json` et Yarn indisponible dans cette relance. Le dernier scan réussi sur la même source indiquait **0 vulnérabilité runtime** sur 209 dépendances et des alertes dans l'outillage de développement (`braces`, `sprintf-js`).

## Protections solides constatées

- cookie de session HttpOnly et configuration production plus stricte ;
- inscription publique et données de démonstration bloquables en production ;
- requêtes principales largement filtrées par `company_id` via `cq/with_company` ;
- contrôles de portée sur les ventes et chantiers principaux ;
- CORS et préflight couverts par des tests ;
- signature Stripe et logique d'idempotence présentes ;
- limites de taille/nombre sur plusieurs entrées fichier et photo ;
- permissions par défaut en mode refus pour les ressources inconnues ;
- nettoyage IndexedDB au logout explicite ;
- suite de tests existante et build toujours verts après les campagnes d'audit.

Ces points réduisent fortement le risque par rapport au build d'origine, mais ne compensent pas les suppressions destructrices ni les scénarios de données résiduelles.

## Roadmap recommandée

### Étape 1 — blocants avant tout pilote

1. Corriger CA3-01 et CA3-02 avec archivage, dépendances contrôlées, restauration et tests.
2. Purger et partitionner tout stockage sensible à la déconnexion, au `401` et au changement d'identité (CA3-03/04).
3. Corriger aussi les P1 encore ouverts de la passe 2 : CSV actif, regex IA, coût/quota IA et mouvements de stock.
4. Révoquer tout secret ou compte de prévisualisation dont la présence dans les anciens scripts est confirmée.

### Étape 2 — avant staging partagé

1. Borner complètement l'import et ne plus renvoyer toutes les lignes au navigateur (CA3-05).
2. Ajouter défense combinée compte/source sur la connexion (CA3-06).
3. Unifier la règle de date de fin de chantier (CA3-07).
4. Journaliser les mutations sensibles (CA3-08).
5. Trancher puis documenter la permission de note client (CA3-09).
6. Faire repasser les trois suites adversariales puis les 39 + 6 tests normaux.

### Étape 3 — avant production

1. Exécuter toute la campagne staging ci-dessous avec données fictives.
2. Faire un test de charge mesuré et un test de concurrence avec vrai MongoDB.
3. Restaurer réellement une sauvegarde dans une base vide.
4. Vérifier proxy/TLS, cookies, CORS, CSP/HSTS, logs, alertes et rotation de secrets dans l'environnement final.
5. Obtenir une validation métier écrite de la matrice rôle × ressource × action.

## Tests précis à faire sur staging

1. Créer deux sociétés A/B et six rôles par société ; tenter lecture, création, modification, suppression et export sur chaque ressource avec identifiants propres, collègues et autre société.
2. Enchaîner connexion A, brouillon IA avec fausses données client, logout, connexion B dans le même onglet ; vérifier l'absence totale de résidu. Refaire après expiration forcée du cookie.
3. Créer client → vente → chantier → photos → notes ; tenter chaque suppression ; vérifier archivage, restauration et intégrité des références.
4. Tester changement de mot de passe, désactivation et suppression pendant une session ouverte, en ligne puis hors ligne.
5. Importer CSV/XLSX aux limites autorisées, puis au-delà : lignes, colonnes, cellule géante, XLSX compressé, fichier malformé, formule et extension trompeuse ; mesurer mémoire/CPU.
6. Lancer deux modifications concurrentes sur stock, vente, commission, prime et synchronisation offline ; vérifier absence de double application ou perte silencieuse.
7. Stripe en mode test : succès, échec, webhook signé invalide, double envoi, ordre inversé, retard, remboursement, chargeback, abonnement annulé et société incohérente.
8. Email de test : contenu client échappé, liens sûrs, rebond, erreur fournisseur, rafale, limitation et absence de données sensibles dans les logs.
9. IA avec fournisseur de test : prompt long, injection dans texte/PDF/image, hallucination, réponse ambiguë, timeout, indisponibilité, quota, confirmation et rejeu d'action.
10. Coupures réseau aux moments critiques de création/suppression/synchronisation ; redémarrage du navigateur ; conflits entre deux appareils.
11. Charge réaliste : clients, ventes, chantiers, photos, planning, dashboard, imports et exports simultanés ; fixer des seuils de latence et mémoire.
12. Sauvegarde complète, suppression de la base de staging, restauration dans une base vide, contrôle d'intégrité et mesure RPO/RTO.

## Limites de cette contre-audit

- Aucun service réel Stripe, email ou IA n'a été contacté.
- Aucun secret de production n'a été utilisé.
- Aucun test destructeur n'a été exécuté sur une infrastructure externe.
- Le faux MongoDB local permet d'isoler la logique HTTP, mais ne reproduit pas les transactions, index, verrous et courses d'un vrai cluster.
- Les tests navigateur multi-compte, multi-onglet et multi-appareil restent à exécuter sur staging.
- Une couverture infinie est impossible ; l'inventaire complet permet maintenant de suivre les routes restantes au lieu de prétendre qu'elles sont toutes dynamiquement testées.

## Verdict argumenté

**État actuel : non prêt pour production.**

Le produit compile, ses tests normaux passent et les renforcements précédents sont réels. Néanmoins, les deux suppressions physiques peuvent provoquer une perte irréversible ou une base incohérente ; les résidus de session peuvent exposer des données dans un navigateur partagé ; et l'import peut encore consommer des ressources non bornées. Ce sont des motifs suffisants pour bloquer une mise en production multi-utilisateur.

**Passage possible en staging :** oui, dans un environnement isolé avec uniquement des données fictives.  
**Passage en pilote limité :** après correction des P1, correction des P2 principaux et succès de la campagne staging.  
**Passage en production :** seulement après tests externes Stripe/email/IA, concurrence réelle, charge, sauvegarde/restauration et validation de la configuration finale.
