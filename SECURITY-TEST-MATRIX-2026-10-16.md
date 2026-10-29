# KYLOT — Matrice de tests sécurité exhaustive

Date : 16 octobre 2026  
Version auditée : copie locale issue de `KYLOT-main (2).zip`, renforcée sans remplacement du design.

## Lecture du résultat

- **PASS** : comportement exécuté et conforme.
- **FAIL** : scénario exécuté et défaut reproduit.
- **À TESTER EN STAGING** : dépend d'un vrai service, d'une vraie infrastructure ou de secrets de test qui ne sont pas disponibles localement.
- **REVUE** : vérification statique du code, sans prétendre simuler toute l'infrastructure.

Une couverture absolument infinie n'existe pas. Cette matrice couvre les familles de risques réalistes : succès, erreurs, abus, accès directs, concurrence, réseau, fichiers, intégrations et exploitation.

## Résultats exécutés

| Groupe | Résultat | Détail |
|---|---:|---|
| Tests serveur sûrs | **PASS** | 39/39 |
| Tests interface | **PASS** | 6/6 |
| Compilation Python | **PASS** | tous les modules compilent |
| Build frontend de production | **PASS** | bundle produit correctement |
| Contrôles adversariaux | **FAIL** | 3/21 passent, 18/21 exposent une imperfection |
| Dépendances Python utilisées en production | **PASS** | 0 vulnérabilité connue |
| Dépendances frontend de production | **PASS** | 0 vulnérabilité connue sur 209 dépendances |
| Arbre frontend complet | **FAIL non-runtime** | 11 alertes high `braces`, 8 moderate `sprintf-js`, dans l'outillage build/test |
| Analyse statique Python Bandit | **PASS critique** | 0 high, 0 medium, 38 low |

## Authentification et sessions

| Scénario | Statut | Observation |
|---|---|---|
| Inscription publique fermée en production | PASS | réponse 403 |
| Connexion valide | PASS | cookie HttpOnly créé |
| Mauvais mot de passe | PASS | refus générique |
| Tentatives répétées | PASS | verrouillage persistant en base |
| Token absent, invalide ou expiré | PASS | endpoints protégés refusés |
| Déconnexion | PASS | token courant révoqué |
| Suppression d'un utilisateur | PASS par conception | les tokens ne retrouvent plus d'utilisateur |
| Réinitialisation du mot de passe | **FAIL P1** | les anciennes sessions restent valides jusqu'à 12 h |
| Cookie Secure/SameSite en production | PASS | contrôlé par le preflight |
| MFA administrateur | À TESTER / ABSENT | aucune seconde authentification implémentée |

## Autorisations, rôles et multi-tenant

| Scénario | Statut | Observation |
|---|---|---|
| Isolation société A / société B sur clients, ventes, projets et utilisateurs | PASS | tests d'intégration locaux |
| Identifiant d'une autre société envoyé dans le corps | PASS | remplacé/refusé côté serveur |
| Accès direct à une vente appartenant à un autre commercial | PASS | 404 |
| Accès direct à un chantier par un autre commercial | PASS | 404 |
| Deux techniciens avec le même prénom | **FAIL P1** | `Jean Dupont` peut ouvrir le chantier de `Jean Martin` |
| Deux personnes avec le même nom de famille | **FAIL P1** | le rapprochement accepte un seul token commun |
| Vente historique liée uniquement par prénom | **FAIL P1** | filtre trop large, unicité non vérifiée |
| Heures supplémentaires avec homonyme | **FAIL P1** | un technicien peut hériter de l'éligibilité d'un autre |
| 172 routes HTTP inventoriées | REVUE | 14 sont publiques ou protégées par secret/signature ; les autres exigent une session |
| Matrice de tous les rôles sur toutes les routes | À TESTER EN STAGING | nécessite plusieurs vrais comptes par rôle et données réalistes |

## Entrées, fichiers et contenu actif

| Scénario | Statut | Observation |
|---|---|---|
| Nombre et taille des photos | PASS | limites présentes |
| Schémas `javascript:` et formats non autorisés | PASS | refusés |
| Base64 déclaré PNG mais contenu non-PNG | **FAIL P2** | les octets réels ne sont pas vérifiés |
| URL HTTPS de photo arbitraire | **FAIL P2** | permet un pixel de suivi externe |
| Nombre et taille des fichiers IA | PASS | limites présentes |
| PDF avec trop de pages | PASS | refusé |
| PDF compressé pathologique / image géante | À TESTER EN STAGING | risque mémoire/CPU pendant le rendu 180–240 DPI |
| Requête avec `Content-Length` excessif | PASS | 413 |
| Requête chunked/sans `Content-Length` excessive | **FAIL P2** | aucune limite applicative sur le flux reçu |
| CSV/XLSX malformés, cellules géantes et formules | À TESTER EN STAGING | corpus hostile requis |

## Emails, cron et paiements

| Scénario | Statut | Observation |
|---|---|---|
| Email avec formulaire ou lien HTTP | PASS | refusé |
| Email demandant un mot de passe | **FAIL P2** | le validateur fort est écrasé par une seconde définition |
| Texte du lien différent de la vraie destination | **FAIL P2** | même cause |
| Secret cron absent ou incorrect | PASS | 401 |
| Rejeu cron séquentiel avec `run_id` | PASS logique | doublon détecté |
| Rejeu cron simultané | **FAIL P2** | pas d'index unique atomique `(run_id, name)` |
| Signature Stripe invalide | PASS | webhook rejeté |
| Rejeu Stripe | PASS | index unique et cycle processing/failed/processed |
| Checkout Stripe, trial, paiement, annulation, impayé, chargeback | À TESTER EN STAGING | Stripe test mode et webhooks réels requis |
| Livraison réelle des emails et anti-spam | À TESTER EN STAGING | fournisseur et domaine réels requis |

## Données, concurrence et traçabilité

| Scénario | Statut | Observation |
|---|---|---|
| Double création locale d'une prime | PASS sur Mongo simulé | doit être rejoué sur un vrai Mongo avec index unique |
| Deux transferts de stock simultanés | PASS sur Mongo simulé | le code reste read-modify-write ; test réel transactionnel requis |
| Index composé société + identifiant | **FAIL P2** | index critiques manquants |
| Modification d'un utilisateur ou mot de passe tracée | **FAIL P2** | absence d'entrée d'audit dans `update_user` |
| Migration rejouée | PASS | marqueur de migration idempotent |
| Sauvegarde et restauration complète | À TESTER EN STAGING | nécessite un dump réel puis restauration isolée |
| Panne Mongo pendant une écriture | À TESTER EN STAGING | injection de panne réelle nécessaire |

## IA et confidentialité

| Scénario | Statut | Observation |
|---|---|---|
| Isolation locale du contexte IA par société/utilisateur | PASS | filtres présents |
| Expiration du contexte court | PASS | TTL 30 minutes |
| Devis et coordonnées envoyés au fournisseur IA | **RISQUE P2** | transfert externe sans consentement visible |
| Prompt injection dans un devis/photo | À TESTER EN STAGING | corpus hostile et compte IA de test requis |
| Sorties IA invalides ou inventées | PARTIEL | parsing défensif, mais tests métier insuffisants |
| Indisponibilité, timeout et quota IA | À TESTER EN STAGING | fournisseur réel requis |
| Politique de conservation/DPA fournisseur | À VALIDER | contrôle juridique et contractuel |

## Frontend, hors-ligne et appareil

| Scénario | Statut | Observation |
|---|---|---|
| JWT absent du stockage JavaScript | PASS | session HttpOnly |
| Cache hors-ligne séparé par utilisateur | PASS | clé d'identité dédiée |
| Cache vidé à la connexion/déconnexion | PASS | données IndexedDB supprimées |
| POST/DELETE rejoués hors ligne | PASS | opérations ambiguës bloquées |
| Données métier présentes en clair dans IndexedDB | RISQUE P3 | exposition sur appareil partagé ou compromis |
| Mots de passe masqués dans l'admin | **FAIL P2** | champs texte visibles |
| Consigne de longueur cohérente | **FAIL P3** | interface annonce 6, serveur exige 12/16 |
| Chrome, Safari, Firefox, mobile et PWA | À TESTER EN STAGING | campagne multi-navigateurs nécessaire |
| Coupure réseau pendant chaque opération métier | À TESTER EN STAGING | tests E2E navigateur requis |

## Secrets et chaîne de livraison

| Scénario | Statut | Observation |
|---|---|---|
| Secrets absents du ZIP renforcé livré | PASS | anciens scripts exclus du paquet |
| Secrets/URL de preview dans la source téléchargée | **FAIL P0 si encore valides** | 23 anciens scripts contiennent un endpoint réel ou des identifiants connus |
| Rotation des secrets et purge de l'historique Git | À FAIRE | impossible à confirmer depuis la copie ZIP |
| Configuration production fail-closed | PASS | preflight présent |
| Déploiement HTTPS, proxy, logs, sauvegardes | À TESTER EN STAGING | infrastructure réelle requise |

## Blocage de mise en production

Le produit ne doit pas être déclaré prêt tant que les P1 suivants ne sont pas corrigés et retestés :

1. remplacer tout rapprochement de sécurité par nom/prénom par un `user_id` immuable ;
2. révoquer toutes les sessions lors d'un changement de mot de passe ;
3. changer les identifiants potentiellement exposés et purger l'historique Git ;
4. faire passer les contrôles adversariaux actuellement en échec ;
5. exécuter les scénarios « staging » avec Stripe, email, IA, vrai Mongo, sauvegarde et navigateurs réels.

## Commandes reproductibles

```bash
PYTHONPATH=. ./.venv/bin/pytest -q \
  backend/test_security_invariants.py backend/test_preflight.py \
  backend/test_app_smoke.py backend/test_integration_security.py

PYTHONPATH=. ./.venv/bin/python audit/security_adversarial_checks.py

cd frontend
CI=true npm test -- --watchAll=false --runInBand
npm run build
```
