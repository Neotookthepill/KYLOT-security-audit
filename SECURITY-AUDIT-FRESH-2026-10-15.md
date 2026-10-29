# KYLOT — audit sécurité frais de la nouvelle archive

Date : 15 octobre 2026  
Source auditée : `KYLOT-main (2).zip`  
SHA-256 de l'archive source : `abb48931e6e022b60ca52239a43c09c54b4ce49e7614a7450d204c3e7365f066`  
Révision indiquée dans l'archive : `67ee69111a6be7f4e8acbfbe0f537958971aec81`

## Conclusion

La nouvelle version n'était pas prête à être exposée telle quelle : elle réintroduisait une session et un mot de passe dérivé dans `localStorage`, une connexion hors ligne survivant aux révocations serveur, des rejouements de mutations ambigus, plusieurs contrôles de périmètre incomplets et des photos arbitraires persistées dans MongoDB.

Ces points ont été corrigés dans cette copie. Aucun P0 restant n'a été démontré par l'audit statique et les tests locaux. Le code est désormais **candidat staging**, pas encore « production sans réserve » : un test sur l'infrastructure réelle, une restauration de sauvegarde et les parcours Stripe/email/IA réels restent obligatoires.

Le visuel d'origine est conservé. `frontend/src/App.js`, `frontend/src/components/Layout.jsx` et la structure de navigation de la nouvelle archive n'ont pas été remplacés par la proposition visuelle séparée.

## Échelle

- **P0** : compromission immédiate ou perte massive probable ; bloque tout déploiement.
- **P1** : faille sérieuse exploitable ou exposition importante ; bloque la production.
- **P2** : risque significatif sous conditions ou dette de sécurité prioritaire.
- **P3** : durcissement, maintenabilité ou défense en profondeur.

## Constats corrigés

### P1 — Secrets de session et authentification hors ligne dans le navigateur

La nouvelle archive stockait un vérificateur PBKDF2, le profil et un JWT complet dans `qylot_offline_creds`. Une XSS ou une extension malveillante pouvait récupérer une session durable ; le mode hors ligne pouvait continuer après désactivation du compte côté serveur.

Correction vérifiable :

- cookie de session `HttpOnly`, `Secure` en production et `SameSite=lax` : `backend/server.py:234` ;
- token absent de la réponse JSON par défaut et interdit en production : `backend/server.py:247` ;
- suppression des anciennes clés uniquement à titre de migration, sans nouveau stockage : `frontend/src/contexts/AuthContext.jsx:22` ;
- purge du cache local à la connexion et à la déconnexion : `frontend/src/contexts/AuthContext.jsx:58` et `frontend/src/lib/offline.js:32` ;
- révocation serveur via `token_epoch` : `backend/server.py:339` et `backend/server.py:917`.

### P1 — IDOR sur des ressources accessibles par identifiant direct

Les listes appliquaient souvent `own`, mais plusieurs routes unitaires chargeaient seulement `(company_id, id)`. Un rôle personnalisé disposant d'une action pouvait viser une vente ou un chantier d'un autre utilisateur de la même société.

Correction vérifiable :

- garde unique de périmètre chantier : `backend/server.py:2686` ;
- lecture, édition, suppression, restauration, confirmation, notes, bonus et validation l'utilisent ;
- suppression d'une vente soumise à `_own_sales_filter` : `backend/server.py:2438` ;
- notes clients soumises à `_scoped_client_query` : `backend/server.py:1404` et `backend/server.py:1413` ;
- tests d'intégration d'accès direct et de suppression hors scope : `backend/test_integration_security.py`.

### P1 — Photos arbitraires, stockage non borné et schémas actifs

Les chantiers et réinterventions acceptaient des chaînes/dictionnaires arbitraires. Cela permettait de gonfler les documents MongoDB, provoquer des erreurs de persistance et conserver une URL de schéma inattendu ensuite utilisée dans un lien de téléchargement.

Correction vérifiable :

- validation HTTPS ou data-URI JPEG/PNG/WebP : `backend/server.py:98` ;
- décodage base64 strict, 4 Mo par image et 20 images par objet : `backend/server.py:104` ;
- métadonnées filtrées : `backend/server.py:133` ;
- deuxième barrière dans l'affichage/téléchargement : `frontend/src/components/ProjectDialog.jsx:50` et `frontend/src/components/ZoomableImage.jsx`.

### P1 — Rejeu hors ligne de créations et suppressions

Une panne réseau après envoi pouvait être confondue avec un mode hors ligne et mettre en file une création ou une suppression déjà exécutée côté serveur. Le retour réseau pouvait alors dupliquer une vente ou appliquer tardivement une suppression.

Correction vérifiable :

- une erreur réseau quand le navigateur se croit en ligne est renvoyée à l'utilisateur ;
- seules les méthodes PUT/PATCH sont mises en attente hors ligne ; POST/DELETE exigent le réseau : `frontend/src/lib/api.js:13-39` ;
- clés de cache préfixées par l'identité : `frontend/src/lib/offline.js:19-35`.

### P1 — Configuration dangereuse au démarrage et inscription publique

L'inscription publique vers la société par défaut, les données de démonstration et les migrations automatiques étaient incompatibles avec une production sûre.

Correction vérifiable :

- inscription publique désactivée et impossible en production : `backend/server.py:800-808` ;
- données de démonstration sur opt-in uniquement : `backend/server.py:8590` ;
- migrations automatiques refusées en production : `backend/server.py:8600` ;
- commande de migration explicite, journalisée et idempotente : `backend/migrate.py` ;
- pré-vol de configuration : `backend/preflight.py`.

### P1 — Authentification, paiement et automatisation

Correction vérifiable :

- anti-brute-force partagé dans MongoDB avec identifiant HMAC et TTL : `backend/server.py:827-895` et `backend/server.py:8583` ;
- retours Stripe limités aux origines configurées : `backend/server.py:169` ;
- webhook Stripe borné, signé et idempotent : `backend/server.py:7268` ;
- le cron suit encore les redirections nécessaires mais ne transfère plus le Bearer vers un autre hôte : `.emergent/cron/dispatch_webhook.sh:60-66`.

### P2 — Vie privée du géocodage

La carte envoyait silencieusement des adresses clients à l'API BAN. Ce n'est pas nécessairement illégal, mais c'est un transfert de données qui doit être assumé et documenté.

Correction vérifiable : géocodage désactivé par défaut en production via `ALLOW_EXTERNAL_GEOCODING=false`, avec état exposé au frontend : `backend/server.py:1352-1365`.

### P2 — Dépendances connues vulnérables

Les dépendances directes/runtime ont été mises à jour et verrouillées. Résultat final :

- Python public : 0 vulnérabilité connue ;
- frontend runtime : 0 critique, 0 élevée, 0 modérée ;
- chaîne complète de développement : 11 chemins élevés `braces` et 8 modérés `sprintf-js`, confinés à CRA/Jest/Tailwind, non embarqués dans le runtime. Leur suppression complète nécessite de migrer hors de Create React App.

## Points forts conservés

- isolation `company_id` déjà très largement utilisée ;
- permissions structurées par ressource/action/scope ;
- journal d'audit métier ;
- index uniques/TTL et traitements Stripe récupérables ;
- nouvelle séparation liste légère / fiche chantier complète pour ne pas transporter toutes les photos ;
- rôles prospecteur et responsable prospecteur désormais filtrés dans les principales vues ;
- workflow chantier multi-jours conservé.

## Risques résiduels

### P1 avant production réelle

- La politique CSP du **site frontend** dépend encore de l'hébergeur. Les en-têtes de l'API sont bons (`backend/server.py:10575`), mais il faut imposer une CSP au reverse proxy/static hosting du frontend.
- Les clés privées Emergent ne sont pas auditées par le registre public. Elles doivent être vérifiées dans l'image réelle et rotées si elles ont été partagées.

### P2

- Le backend reste un monolithe de plus de 10 000 lignes. Les erreurs d'autorisation ont tendance à se répéter route par route ; séparer services, dépôts et politiques d'accès réduira cette classe de défauts.
- Les photos base64 restent stockées dans MongoDB. Malgré les limites, un stockage objet privé avec URL signée serait plus robuste et moins coûteux.
- Le cache IndexedDB contient volontairement des données métier sur l'appareil pendant la session. Il est maintenant isolé et purgé, mais le chiffrement au repos dépend du navigateur/OS.
- Le cookie d'accès dure 12 heures. Pour un futur usage multi-utilisateur sensible, préférer un accès court et une rotation contrôlée plutôt qu'allonger encore cette durée.
- Aucun test local ne remplace un essai avec le vrai MongoDB, les vrais webhooks Stripe, l'email et l'IA.

### P3

- Migrer les événements FastAPI `on_event` vers un gestionnaire `lifespan` ; les tests signalent la dépréciation.
- Migrer CRA vers Vite ou une chaîne maintenue afin de supprimer la dette `braces`/`sprintf-js`.
- Ajouter des tests navigateur E2E sur connexion, déconnexion, changement de rôle, hors ligne, chantier multi-jours et upload photo.

## Verdict de livraison

**Verdict : GO pour staging sécurisé, NO-GO pour une mise en production directe sans répétition générale.**

Les bloqueurs de code découverts sont corrigés et les tests locaux sont verts. Le passage production devient raisonnable après :

1. sauvegarde MongoDB puis restauration réellement testée ;
2. pré-vol strict avec les secrets réels ;
3. test E2E staging des rôles et des scopes ;
4. test Stripe/email/IA et cron sur les endpoints finaux ;
5. CSP frontend et HTTPS/HSTS vérifiés sur les réponses réellement servies ;
6. rotation des secrets qui auraient circulé dans des ZIP, chats ou logs.
