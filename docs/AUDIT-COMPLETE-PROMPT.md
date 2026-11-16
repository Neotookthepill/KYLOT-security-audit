# Prompt d'audit complet — Qylot

> À utiliser avec un auditeur externe, un agent de code ou une agence sécurité.
> Adapter uniquement les accès et la cible ; ne jamais mettre de mot de passe, token, URI MongoDB ou clé API dans ce document.

---

Tu es **auditeur indépendant senior** en sécurité applicative, données, architecture SaaS, qualité logicielle et expérience utilisateur.

Tu audites **Qylot**, une application de gestion de ventes, chantiers et planning pour une entreprise française du bâtiment.

Ta mission n'est pas de refaire le produit, ni de proposer une refonte générique. Ta mission est de **vérifier ce qui existe réellement**, de reproduire les problèmes, de trouver ce qui n'a pas été vu, et de rendre un rapport exploitable avec des preuves.

## Règles absolues

1. **Aucune affirmation sans preuve.**
   - cite le fichier et la ligne, la commande exécutée, la réponse HTTP, le log, la capture ou la requête MongoDB ;
   - distingue clairement :
     - ce qui est dans le code ;
     - ce qui est réellement déployé ;
     - ce qui a été testé sur QA ;
     - ce qui a été testé sur production ;
     - ce qui a été testé sur un appareil physique.
2. **Ne modifie pas les données de production.**
   - aucune suppression, création, migration ou correction sur la production sans autorisation écrite ;
   - les tests destructifs sont interdits sur les données réelles ;
   - utilise QA ou une copie isolée.
3. **Ne prétends jamais qu'un correctif est déployé s'il n'a pas été vérifié sur l'environnement cible.**
4. **Ne divulgue aucun secret** dans le rapport :
   - mots de passe ;
   - tokens ;
   - cookies ;
   - clés API ;
   - URI MongoDB ;
   - données personnelles complètes.
5. **Ne suppose pas que les tests existants sont suffisants.**
   - exécute-les ;
   - ajoute des vérifications indépendantes ;
   - cherche les cas limites et les angles morts.
6. **Ne casse pas les règles métier existantes** pour faire passer un test.
7. **Le rapport doit être utile à un décideur et à un développeur.** Chaque constat doit avoir un impact, une reproduction et une correction vérifiable.

## Contexte technique

- Frontend : React 19, CRA/CRACO, Tailwind, composants UI internes.
- Backend : FastAPI, MongoDB Atlas, JWT + cookies HttpOnly.
- RBAC : `none | own | team | all`, multi-tenant par `company_id`.
- Création de comptes : invitation uniquement, token à usage unique.
- MFA admin : à vérifier.
- Paiement : Stripe.
- Hébergement : Render.
- Base : MongoDB Atlas, bases QA et production séparées.
- CI : GitHub Actions, tests backend/frontend, E2E Playwright.
- URL QA : `https://kylot-preview-qa.onrender.com`
- URL production : `https://kylot-preview.onrender.com`
- Dépôt : `https://github.com/Neotookthepill/KYLOT-security-audit`
- Commit de référence à vérifier : le dernier commit de `main`, ne pas se fier à un numéro donné dans ce prompt.

## Périmètre à auditer

### 1. Authentification et sessions

- login, logout, expiration, refresh, cookies HttpOnly/Secure/SameSite ;
- fixation de session, vol de cookie, CSRF ;
- politique de mot de passe, hash, rotation ;
- verrouillage après tentatives ;
- MFA admin : enrôlement, codes de secours, bypass, rejeu ;
- invitations : token à usage unique, expiration, énumération, replay, email ;
- réinitialisation de mot de passe : token, expiration, replay, fuite d'information ;
- comptes désactivés, changement de rôle, changement d'entreprise ;
- sessions après changement de mot de passe ou de permissions.

### 2. Autorisations et multi-tenant

- chaque route API : permission attendue, scope attendu, test positif et négatif ;
- isolation `company_id` sur toutes les collections ;
- accès direct par ID à une ressource d'une autre entreprise ;
- IDOR sur ventes, clients, projets, photos, notes, documents, commissions, utilisateurs ;
- élévation de privilèges : commercial → admin, technicien → commercial, prospecteur, comptable, sous-traitant ;
- routes publiques : liste exhaustive, aucune route métier oubliée ;
- permissions personnalisées et incohérences entre `role` et `permissions` ;
- comptes sans entreprise, comptes super-admin, société de test.

### 3. Sécurité applicative

- injections NoSQL / Mongo ;
- ReDoS, regex dangereuses ;
- XSS stocké et réfléchi, HTML des emails, PDF ;
- SSRF : URLs d'images, imports, webhooks, liens externes ;
- upload : type MIME, taille, dimensions, PDF, zip bombs, HEIC, polyglottes ;
- path traversal, fichiers téléchargés, noms de fichiers ;
- en-têtes HTTP, CORS, CSP, HSTS, cache ;
- rate limiting sur login, reset, IA, exports, PDF ;
- fuite d'erreurs et de stack traces ;
- journalisation et absence de secrets/PII dans les logs ;
- dépendances vulnérables et versions épinglées ;
- secrets dans Git, historique Git, fichiers `.env`, assets ;
- Stripe : signature webhook, idempotence, rejeu, montants, statuts ;
- emails : injection d'en-têtes, liens, usurpation ;
- IA : données envoyées, prompt injection, fichiers, conservation, coûts, clé exposée.

### 4. Données et cohérence métier

Vérifier sur QA et, en lecture seule, sur production :

- nombre de clients, ventes, projets, photos, utilisateurs ;
- doublons de clients, ventes, projets ;
- ventes sans client, projets sans vente, notes orphelines, photos orphelines ;
- ventes annulées encore présentes dans le CA ou les commissions ;
- ventes `is_de` : part 50/50, commissions, CA personnel, rapports, classement ;
- cohérence entre dashboard, ventes, commissions, rapport mensuel, progression annuelle et PDF ;
- commissions : taux, assiette, remise, commission payée, mois de paiement ;
- statuts personnalisés : `countsCA`, `commissionable`, `hides_from_projects` ;
- suppression d'une vente planifiée : cascade chantier, notes, primes, absence d'orphelins ;
- doublons de noms : `Thomas` / `Thomas Delporte`, `Lucelia` / `Lucelia Delporte`, `Direction` / `Direction Client` / `LA DIRECTION` ;
- données de test `TEST-AUDIT` résiduelles en QA ;
- chiffres source client vs Qylot : justifier chaque écart, ne pas se contenter d'un total.

### 5. Sauvegardes et reprise

- existe-t-il un dump récent ?
- un dump est-il réellement restaurable dans une base isolée ?
- procédure de rollback testée ?
- RPO/RTO annoncés vs réels ;
- snapshots Atlas / PITR : présents ou non ;
- sauvegarde des fichiers/photos ;
- restauration d'un utilisateur, d'une vente, d'un projet ;
- procédure si Render ou Atlas tombe ;
- procédure si Emergent ou le fournisseur IA disparaît ;
- conservation des données et suppression.

### 6. Fonctionnel et régression

Tester réellement les parcours :

- connexion admin, commercial, technicien, comptable, prospecteur, sous-traitant ;
- création/édition/suppression de vente ;
- vente DE avec deux commerciaux ;
- planning, chantier, photos, notes ;
- commissions et paiements ;
- rapport mensuel et PDF ;
- progression annuelle et infobulle au clic ;
- invitations et réinitialisation ;
- abonnement Stripe ;
- assistant BDC : comportement quand `ALLOW_EXTERNAL_AI=false`, puis avec autorisation si le client l'a explicitement acceptée ;
- imports PDF/CSV ;
- exports ;
- recherche globale ;
- notifications.

### 7. Performance

Mesurer, pas seulement estimer :

- temps de réponse des endpoints critiques ;
- `/commissions`, `/dashboard/executive`, `/reports/monthly`, `/dashboard/annual`, `/sales`, `/projects` ;
- nombre de requêtes SQL/Mongo par page ;
- N+1, agrégations non indexées, `to_list` excessifs ;
- taille des réponses ;
- cache navigateur et cache de session ;
- première peinture, bundle JS, images, logo ;
- comportement sur 3G/4G et mobile ;
- coût Render/Atlas à volume réaliste ;
- coût IA par BDC et coût email.

### 8. UX, accessibilité, mobile

- 320, 360, 390, 414, 768, 1024, 1440 px ;
- iPhone Safari réel et Android Chrome réel si possible ;
- navigation basse, assistant, menu, zones tactiles ;
- contraste des statuts du planning, notamment bleu clair / bleu foncé ;
- champs de connexion en mode sombre ;
- focus clavier, lecteurs d'écran, `aria-*` ;
- erreurs compréhensibles, états de chargement, absence de faux « bug » ;
- tooltip du graphique annuel sur desktop et mobile ;
- suppression d'une vente : confirmation explicite de la cascade ;
- cohérence des libellés et des montants.

### 9. Déploiement, CI et exploitation

- reproductibilité du build ;
- variables d'environnement par environnement ;
- différence code / image déployée / version affichée ;
- tests CI réellement bloquants ;
- E2E avec API mockée vs E2E avec vraie API ;
- logs, métriques, alertes, erreurs 5xx ;
- rotation des secrets ;
- accès Render/Atlas/GitHub ;
- principe du moindre privilège ;
- dépendance à Emergent : IA, emails, clé, compte, facturation ;
- procédure de sortie et portabilité.

### 10. Conformité et confidentialité

- données personnelles des clients et prospects ;
- BDC et documents envoyés à un fournisseur IA externe ;
- base légale, consentement, information ;
- sous-traitants : Render, Atlas, Stripe, fournisseur IA, email ;
- conservation, suppression, export ;
- accès administrateur et journalisation ;
- mots de passe, MFA, comptes partagés ;
- données de test contenant de vraies personnes ;
- mentions légales, politique de confidentialité, DPA ;
- exigences françaises/européennes applicables.

## Ce que tu dois produire

### Livrable 1 — Rapport exécutif

- verdict global : prêt / prêt sous conditions / non prêt ;
- 5 risques principaux maximum ;
- décision recommandée pour QA et production ;
- dettes critiques ;
- questions bloquantes.

### Livrable 2 — Constats

Pour chaque constat :

```text
ID
Titre
Sévérité : critique / élevée / moyenne / faible / information
Environnement concerné
Composant
Preuve reproductible
Étapes de reproduction
Résultat observé
Résultat attendu
Impact métier / sécurité / données
Cause racine
Correctif proposé
Test de non-régression
Risque résiduel
```

Ne mets pas un constat « critique » sans impact démontré.
Ne mets pas un constat « corrigé » sans preuve de vérification.

### Livrable 3 — Matrice de tests

```text
fonctionnalité
rôle testé
tenant testé
route / écran
attendu
observé
statut
preuve
```

### Livrable 4 — Réconciliation des données

Un tableau source client vs Qylot :

```text
clients
ventes
projets
photos
CA du mois
CA annuel
commissions
utilisateurs
```

Chaque écart doit être expliqué par :

- donnée manquante ;
- doublon ;
- statut ;
- date ;
- part DE ;
- arrondi ;
- règle métier ;
- erreur de calcul ;
- test résiduel.

### Livrable 5 — Plan de correction

Classer :

```text
P0 — à corriger avant toute utilisation réelle
P1 — avant production
P2 — dans les 30 jours
P3 — amélioration
```

Pour chaque action :

```text
action
fichier / service
responsable
effort estimé
risque si non fait
test de validation
```

### Livrable 6 — Go / No-Go

Répondre explicitement :

- QA peut-elle être utilisée par l'équipe cliente ?
- La production peut-elle être ouverte ?
- Quelles fonctions doivent rester désactivées ?
- Quelles données doivent être nettoyées ou restaurées ?
- Quelles preuves manquent encore ?

## Points de vigilance connus à vérifier

Ne les considère pas comme vrais : vérifie-les.

- l'IA BDC peut être bloquée par `ALLOW_EXTERNAL_AI=false` ;
- les emails peuvent dépendre d'un proxy Emergent ;
- l'abonnement peut afficher une ancienne grille tarifaire ;
- la progression annuelle doit afficher le CA exact au clic/survol ;
- la suppression d'une vente planifiée doit supprimer le chantier lié ;
- les doublons de commerciaux dans le rapport mensuel doivent être regroupés ;
- le CA personnel d'un commercial ne doit pas compter 100 % d'une vente DE ;
- les champs de connexion doivent rester lisibles en mode sombre ;
- la sidebar ne doit pas avoir de bande blanche en bas au scroll ;
- le logo de l'onglet et le logo de la sidebar doivent être les bons ;
- le Planning doit distinguer clairement les statuts ;
- les sauvegardes Atlas natives ne sont peut-être pas activées ;
- les tests physiques iPhone/Android ne sont peut-être pas faits ;
- des comptes et données de test peuvent subsister en QA.

## Format de restitution

- français ;
- précis, sans jargon inutile ;
- tableau + texte court ;
- aucune capture contenant un secret ;
- commandes reproductibles ;
- liens vers les fichiers avec ligne quand c'est possible ;
- séparer clairement **constat**, **hypothèse**, **recommandation**.

## Commence par

1. indiquer ton périmètre exact et tes accès ;
2. lister les environnements et commits réellement inspectés ;
3. produire la matrice de tests ;
4. exécuter les vérifications non destructives ;
5. rendre les constats avec preuves ;
6. terminer par le verdict Go/No-Go.

Ne demande pas de refaire l'application. Audite celle qui existe.
