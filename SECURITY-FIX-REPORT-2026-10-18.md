# KYLOT — rapport final des corrections de sécurité

Date : 18 octobre 2026 — validation étendue le 19 octobre 2026  
Périmètre : copie locale issue de `KYLOT-main (2).zip`  
Objectif : corriger les constats des trois campagnes adversariales sans modifier le design ni retirer de fonctionnalité métier.

## Verdict

Les problèmes reproductibles trouvés localement ont été corrigés et leurs tests de non-régression passent. La copie est **prête à être déployée en préproduction contrôlée**, mais elle ne doit pas encore être qualifiée de « totalement sûre » ou « prête production » sans les essais externes listés à la fin de ce document.

Résultat cumulé :

- 54/54 scénarios adversariaux historiques réussis ;
- 10/10 groupes de scénarios HTTP multi-rôles et multi-entreprises réussis, couvrant 62 tentatives directes, listes et mutations ;
- 8/8 groupes d'entrées hostiles et de sessions réussis ;
- 4/4 contrôles de volume borné réussis ;
- 33/33 groupes routes, intégrité métier, authentification, paiement et fuzzing structuré réussis ;
- 40/40 tests serveur standards réussis ;
- 23/23 tests interface réussis ;
- compilation Python réussie ;
- build frontend de production réussi ;
- Bandit sur le serveur : 0 constat élevé, 0 moyen, 0 faible après qualification des faux positifs ;
- audit de l'environnement Python installé : 0 vulnérabilité connue ;
- audit Yarn : 0 vulnérabilité connue sur 209 paquets ;
- 172 tests automatisés réussis au total (109 sécurité/robustesse, 40 serveur, 23 interface).
- couverture mesurée : 21 % des instructions du serveur par les 40 tests standards et 3,11 % des lignes du frontend ; les 487 tests HTTP historiques nécessitent un environnement de préproduction réel.

## Correctifs appliqués et preuves

### P1 — pertes de données et autorisations critiques

1. **Suppression d'un client avec historique bloquée.** Une suppression renvoie maintenant `409` si des ventes, chantiers ou notes dépendent encore du client. Preuve : `backend/server.py:1475-1500`.
2. **Suppression d'une vente avec chantier bloquée.** La cascade qui supprimait les chantiers et leurs photos a été retirée ; la route renvoie `409`. Preuve : `backend/server.py:2609-2631`.
3. **Révocation des anciennes sessions après changement de mot de passe.** Les tokens portent un horodatage précis et le compte conserve une époque de révocation en millisecondes. Preuve : `backend/server.py:354-381`, `backend/server.py:6600-6625`.
4. **Homonymes supprimés des décisions d'accès.** Les rapprochements sensibles n'autorisent plus un utilisateur uniquement parce qu'il partage un prénom ou un nom avec une autre personne ; les identifiants canoniques, l'email exact ou le nom complet normalisé sont utilisés. Couverture : `audit/security_adversarial_checks.py`.
5. **Concurrence stock et primes protégée.** Les écritures critiques sont atomiques et les contraintes uniques empêchent les doubles créations concurrentes. Couverture : `ConcurrencyChecks` dans `audit/security_adversarial_checks.py`.

### P2 — session, navigateur et authentification

6. **Brouillons IA séparés par utilisateur.** La clé du brouillon dépend de l'identité connectée et le composant recharge un état propre lors d'un changement d'utilisateur. Preuve : `frontend/src/components/AIHelper.jsx:22`, `frontend/src/components/AIHelper.jsx:325-344`, `frontend/src/components/AIHelper.jsx:429-455`.
7. **Purge au logout et à l'expiration.** Cache IndexedDB, file hors ligne et données de session sensibles sont effacés au logout et après toute réponse `401`. Preuve : `frontend/src/lib/offline.js:32-54`, `frontend/src/lib/api.js:67-84`, `frontend/src/contexts/AuthContext.jsx`.
8. **Protection anti-bruteforce complétée.** Les échecs sont limités par compte et par source réseau, stockés dans MongoDB et expirés automatiquement. Un tiers ne peut plus rendre le bon mot de passe inutilisable uniquement en provoquant le verrou du compte. Les en-têtes proxy ne sont acceptés que sur configuration explicite. Preuve : `backend/server.py:868-1001`.
9. **Tokens retirés du stockage JavaScript.** L'interface utilise le cookie HttpOnly et ne garde plus de jeton ou de mot de passe dans le navigateur. Le rejeu hors ligne est limité aux opérations PUT/PATCH prévues.

### P2 — fichiers, imports, exports et entrées

10. **Photos vérifiées réellement.** Nombre, taille, base64, schéma, hôte HTTPS autorisé et signature binaire PNG/JPEG/WebP sont contrôlés ; changer seulement l'extension ou le type déclaré ne suffit plus. Preuve : `backend/server.py:101-148`.
11. **Requêtes sans `Content-Length` bornées.** Le serveur compte aussi les octets des requêtes envoyées en flux ou en chunks.
12. **Imports CSV/XLSX bornés.** Maximum de lignes, colonnes et caractères par cellule avant traitement ; les dimensions XLSX sont contrôlées avant l'itération. Preuve : `backend/server.py:93-99`, `backend/server.py:1660-1730`.
13. **Aucun fichier complet renvoyé au navigateur.** L'aperçu est limité à 20 lignes ; les lignes restent temporairement côté serveur derrière un identifiant opaque, lié à la société et à l'utilisateur, puis expirent. Preuve : `backend/server.py:1733-1821`, index TTL `backend/server.py:8773`.
14. **Exports CSV neutralisés et produits en flux.** Les valeurs commençant comme une formule de tableur sont neutralisées et les gros exports ne sont plus construits entièrement en mémoire. Preuve : `backend/server.py:6699-6711` et routes d'export associées.
15. **Dates et nombres stricts.** Dates impossibles, durées négatives, échéances nulles, valeurs `NaN` et ajustements de stock démesurés sont refusés par les modèles.

### P2 — IA, confidentialité et intégrations

16. **Coût IA borné.** Prompts limités, quotas distribués par minute et par jour, expiration TTL et erreurs fournisseur génériques. Preuve : `backend/server.py:4058-4090`, `backend/server.py:8774`.
17. **Noms traités comme texte dans la recherche IA.** Les caractères de regex contenus dans un nom client ne peuvent plus élargir la recherche.
18. **Données internes réduites selon le rôle.** Un technicien ne reçoit plus les emails/objectifs commerciaux, les règles de primes, la configuration de commissions, les absences nominatives ou les statistiques globales auxquelles il n'a pas droit.
19. **Géocodage externe désactivé par défaut.** Les adresses clients ne partent pas vers un service tiers sans activation explicite.
20. **Stripe, cron et redirections durcis.** Signature et idempotence Stripe, origines de retour autorisées, secrets cron et redirections inter-hôtes contrôlés.

### P2/P3 — cohérence métier et traçabilité

21. **Une permission de lecture ne permet plus d'ajouter une note.** L'écriture d'une note exige maintenant `clients.edit`. Preuve : `backend/server.py:1516-1526`.
22. **Chantier futur impossible à terminer.** Le refus s'applique aux chantiers d'un jour comme aux chantiers multi-jours. Preuve : `backend/server.py:10358-10376`.
23. **Actions sensibles journalisées.** Imports, équipe, primes, paramètres et mises à jour privilégiées alimentent le journal d'audit.
24. **Erreurs secondaires visibles.** Les échecs de notification, journalisation de stock, géocodage et contexte IA ne sont plus avalés silencieusement ; ils sont consignés sans retourner de détail interne au navigateur.
25. **Données temporaires expirées.** Tentatives de connexion, quotas IA, actions IA en attente et lots d'import ont des index TTL. Preuve : `backend/server.py:8769-8774`.
26. **Archives QA neutralisées.** Les anciens rapports de test ont été conservés comme historique, mais les adresses administrateur, mots de passe et URL de prévisualisation qu'ils contenaient ont été remplacés par des valeurs factices. Les secrets de CI ressemblant à des clés Stripe ont également été renommés pour éviter toute ambiguïté.
27. **Champs métier désormais bornés.** Les noms, coordonnées, notes, prestations, affectations, événements, absences, prospects et imports qui n'avaient pas de plafond explicite sont refusés avant stockage lorsqu'ils sont démesurés. Preuve : modèles Pydantic de `backend/server.py`.
28. **Télémétrie intrusive retirée.** Le script Emergent et le replay PostHog codé en dur ne sont plus chargés par la page de production.
29. **IA externe sous contrôle explicite.** En production, les textes et documents ne peuvent partir vers le fournisseur IA que si `ALLOW_EXTERNAL_AI=true` a été volontairement configuré.
30. **Permission de notes fermée.** Supprimer une note exige maintenant la permission `clients.edit`, l'appartenance de la note et l'accès réel au client concerné.
31. **État Stripe corrigé.** Une session `complete` mais impayée ne donne plus accès ; les essais `trialing` sont reconnus séparément du paiement.
28. **Logo des paramètres soumis au validateur d'images.** Une fausse image, un contenu trop lourd ou une URL distante non autorisée ne peut plus contourner les contrôles appliqués aux photos métier. Preuve : `backend/server.py:6046-6055` et `backend/server.py:6533-6543`.
29. **Dates et périodes réellement calendaires.** Absences, réinterventions, jours OFF, jours supplémentaires, heures et mois de commission refusent maintenant les valeurs seulement « bien formées » mais impossibles, comme le 31 février ou le mois 13.
30. **Cohérence financière renforcée.** Une part financée ne peut plus dépasser le montant total de la vente et les mois financiers sont validés avant stockage.
31. **Structures imbriquées bornées.** Prestations, catégories, statuts, tags IA, photos, paramètres, primes et préférences possèdent des plafonds explicites, y compris sur les chaînes qu'elles contiennent.
32. **Recherche globale alignée sur les permissions réelles.** Les résultats clients, ventes, chantiers et réinterventions respectent désormais les permissions et la portée `own`; l'annuaire utilisateur reste invisible sans `users.manage`.

## Tests de non-régression ajoutés

- `audit/security_adversarial_checks.py` : 21 scénarios — identités, homonymes, sessions, photos, concurrence, taille des requêtes, routes publiques et secrets ;
- `audit/security_adversarial_round2.py` : 20 scénarios — confidentialité par rôle, CSV, IA, validation métier, exports et erreurs fournisseur ;
- `audit/security_adversarial_round3.py` : 13 scénarios — suppressions, import volumineux, navigateur partagé, verrouillage, date future, permissions et audit ;
- `audit/security_e2e_matrix.py` : 10 groupes couvrant 62 appels — accès direct, listes et mutations entre deux sociétés, permissions commerciales et techniciennes, comptes suspendus et super-administration ;
- `audit/security_hostile_inputs.py` : 8 groupes — champs démesurés, limites imbriquées, logos falsifiés, JWT expirés ou malformés, utilisateur supprimé, révocation et champs inconnus ;
- `audit/security_scale_checks.py` : 4 groupes — import de 1 000 clients, refus au-delà de 5 000 lignes, export en flux de 5 000 ventes et isolation de 5 000 clients parmi 10 000 ;
- `audit/security_route_business_fuzz.py` : 33 groupes — inventaire des routes, refus anonyme des routes protégées, secrets des routes techniques, dates/heures/mois réels, cohérence du financement, plafonds imbriqués, télémétrie, IA externe, permissions de notes, recherche globale, états Stripe, comptes désactivés, coût du login, offline et concurrence du stock ;
- `backend/test_security_invariants.py` : garde-fous statiques conservés et alignés sur la vérification binaire des images.

Ces tests sont reproductibles localement et doivent rester dans la CI.

## Ce qui reste obligatoirement à tester en préproduction

Ces points dépendent de vrais services ou d'une infrastructure absente de la copie locale ; ils ne sont donc pas inventés ni déclarés validés :

1. **Matrice E2E dans de vrais navigateurs :** la matrice HTTP locale couvre désormais deux sociétés et les principaux rôles, mais les mêmes parcours doivent être rejoués dans l'interface, avec cookies réels et plusieurs sessions simultanées.
2. **MongoDB réel :** concurrence multi-processus, index effectivement créés, transactions/pannes entre deux écritures et tests de charge avec un volume représentatif.
3. **Stripe sandbox :** paiement réussi/refusé, événements en retard ou désordonnés, replay concurrent, remboursement, impayé, annulation et changement d'abonnement.
4. **Emails et cron :** délivrabilité, destinataires, HTML final, limitation d'envoi, secret réel et exécution répétée.
5. **IA réelle :** prompt injection texte/image/PDF, timeout, indisponibilité, quotas, contenu dangereux et absence de fuite entre deux sociétés.
6. **Fichiers hostiles :** images/PDF polyglottes, métadonnées EXIF, archives ou documents très compressés, mesure CPU/RAM et antivirus si des fichiers sont conservés.
7. **Mode hors ligne réel :** deux navigateurs, coupure pendant une écriture, retour réseau, conflit, compte désactivé pendant la coupure et appareil partagé.
8. **Exploitation :** TLS/proxy, CORS/CSP/HSTS observés depuis Internet, rotation des secrets, logs/alertes, sauvegarde puis restauration chronométrée.
9. **Parcours produit :** recettes métier complètes clients → vente → chantier → photos → paiement → export, avec données volumineuses et cas d'annulation.

## Décision de livraison recommandée

- **Aujourd'hui :** intégrer cette copie sur une branche dédiée et la déployer en staging avec des secrets neufs.
- **Après la campagne ci-dessus :** ouvrir un pilote limité à l'utilisateur actuel avec sauvegardes et surveillance.
- **Production élargie :** seulement après réussite documentée de la matrice multi-rôles, de Stripe, des sauvegardes/restaurations et des scénarios hors ligne.

Le design d'origine a été conservé. Les changements concernent la sécurité, la cohérence des données, la confidentialité, la traçabilité et les tests.
