# KYLOT — audit sécurité, passe 2 (constats nouveaux uniquement)

Date : 16 octobre 2026  
Périmètre : copie locale renforcée de `KYLOT-main (2).zip`  
Règle de cette passe : ne pas recompter les défauts déjà documentés dans `SECURITY-TEST-MATRIX-2026-10-16.md`.

## Résultat net

- 20 nouveaux scénarios adversariaux ont été écrits et exécutés.
- 20/20 échouent sur le comportement de sécurité attendu.
- Les tests habituels restent stables : 39/39 serveur et 6/6 interface réussissent.
- Aucun fichier fonctionnel ni visuel n'a été modifié pendant cette passe. Seuls ce rapport et `audit/security_adversarial_round2.py` ont été ajoutés.

Cela ne signifie pas « 20 brèches exploitables à distance ». Plusieurs tests représentent différentes manifestations d'une même faiblesse. Après regroupement, la passe établit **12 problèmes nouveaux** : 4 de gravité P1, 7 P2 et 1 P3.

## P1 — à corriger avant mise en production

### P1-01 — Injection de formules dans les exports CSV

**Preuve.** Une valeur client commençant par `=WEBSERVICE(...)` et une prestation commençant par `+HYPERLINK(...)` ressortent comme cellules actives dans les exports. Le CSV est écrit directement depuis les champs en base sans neutraliser les préfixes `=`, `+`, `-` et `@` : `backend/server.py:6477-6484` et `backend/server.py:6506-6516`.

**Risque.** Un commercial ou une importation peut enregistrer une valeur piégée. Quand l'administrateur ouvre le CSV dans Excel ou LibreOffice, la formule peut provoquer une requête externe, une fuite de données ou une action trompeuse. L'attaque vise le poste de l'administrateur, pas le serveur.

**Correction.** Appliquer une fonction unique à chaque cellule texte exportée : si le premier caractère significatif est `=`, `+`, `-` ou `@`, préfixer la valeur avec une apostrophe. Ajouter les mêmes contrôles aux futurs exports XLSX.

### P1-02 — Expression régulière injectée dans l'action IA de changement de statut

**Preuve.** Le nom `.*` est interprété comme une expression régulière et résout la première vente disponible. Les valeurs `bdc` et `client_name` sont concaténées dans `$regex` sans `re.escape` : `backend/server.py:4369-4388`. L'exécution accepte ensuite à nouveau les données fournies par le client : `backend/server.py:4497-4508` et `backend/server.py:4575-4588`.

**Risque.** Un utilisateur autorisé à éditer les ventes peut modifier le statut d'une vente différente de celle demandée. Un motif pathologique peut aussi augmenter le coût de la requête MongoDB.

**Correction.** Échapper systématiquement les chaînes avec `re.escape`, exiger une correspondance exacte ou un identifiant immuable, refuser les résultats ambigus et lier l'exécution à un aperçu signé côté serveur plutôt que de faire confiance à `resolved_sale_id` envoyé par le navigateur.

### P1-03 — Coût IA et déni de service sans limite métier

**Preuve.** `AIChatIn`, `KiksActIn` et `AIActionIn` acceptent chacun un message d'un million de caractères : `backend/server.py:3892-3893`, `backend/server.py:3959-3962` et `backend/server.py:4315-4320`. Les appels IA aux lignes `3965`, `4100` et `4392` n'ont ni quota par utilisateur, ni plafond journalier, ni limitation de fréquence dédiée.

**Risque.** Un compte authentifié compromis ou mal utilisé peut multiplier les appels coûteux, saturer le fournisseur et générer une facture importante. La limite HTTP globale ne constitue pas une limite de tokens ou de coût.

**Correction.** Limiter les messages texte (par exemple 8–16 kio), estimer les tokens, ajouter un quota par utilisateur/société et une limite de fréquence distribuée. Refuser avant d'appeler le fournisseur.

### P1-04 — Un technicien peut s'attribuer une quantité de stock arbitraire

**Preuve.** `StockAdjustIn.delta` n'a aucune borne : `backend/server.py:9243-9246`. Le test a envoyé `+1 000 000 000` et l'API a répondu 200 en enregistrant ce stock : `backend/server.py:9908-9940`.

**Risque.** L'inventaire, les commandes et la traçabilité peuvent être rendus faux sans validation d'un responsable. Un technicien peut déclarer une entrée illimitée sur son propre stock.

**Correction.** Borner le delta, distinguer consommation/réception, rattacher les sorties à un chantier autorisé, faire valider les entrées importantes et conserver un rapprochement avec le dépôt ou un justificatif.

## P2 — important

### P2-01 — Une route métier globale peut être déclenchée par tout compte connecté

**Preuve.** Un technicien a appelé `POST /api/sales/check-attente-14j`; la réponse a été 200 et une notification a été créée. La route ne vérifie ni rôle ni permission : `backend/server.py:2391-2435`.

**Risque.** Déclenchements répétés, notifications non sollicitées et modification du marqueur `attente_14j_notified_at` par un rôle qui ne gère pas les ventes.

**Correction.** Réserver la route à un cron signé ou aux managers, avec idempotence atomique et journalisation.

### P2-02 — Données internes visibles par des rôles qui n'en ont pas besoin

**Preuves dynamiques.** Un technicien connecté peut actuellement lire :

- les taux et paliers de commission via `/settings` (`backend/server.py:6259-6305`) ;
- les emails et objectifs commerciaux via `/team` (`backend/server.py:4847-4862`) ;
- les règles et montants de primes commerciales via `/bonuses` (`backend/server.py:5997-6004`) ;
- les jours OFF individuels avec nom et motif via `/off-days` (`backend/server.py:8990-8996`) ;
- les nombres de ventes par statut via `/sale-statuses/usage` (`backend/server.py:10487-10497`).

**Risque.** Divulgation interne inutile : rémunération, objectifs, adresse email, absence ou motif personnel, volume de litiges et activité commerciale. Ces décisions de visibilité doivent être confirmées avec le propriétaire produit ; par défaut, le moindre privilège recommande de masquer ces données.

**Correction.** Définir une matrice champ × rôle, filtrer les réponses côté serveur et réserver les endpoints d'administration aux permissions correspondantes. Ne pas compter uniquement sur le fait que l'écran n'est pas affiché.

### P2-03 — Dates et heures syntaxiquement correctes mais impossibles

**Preuve.** `2026-99-99` est accepté comme date de vente et d'événement ; `99:99` est accepté comme heure. Les expressions régulières ne valident que la forme : `backend/server.py:717-725`, `backend/server.py:9036-9057`.

**Risque.** Planning incohérent, tris faux, rappels manqués et erreurs lors de conversions ultérieures.

**Correction.** Utiliser les types Pydantic `date` et `time`, puis sérialiser en ISO. Vérifier également `end_time > start_time`.

### P2-04 — Valeurs métier négatives ou absurdes acceptées

**Preuve.** Une vente accepte `payment_installments=-50` (`backend/server.py:700-707`). Un chantier accepte `scheduled_date="not-a-date"` et `duration_days=-99` (`backend/server.py:757-769`).

**Risque.** Échéanciers impossibles, calculs de planning erronés et enregistrements impossibles à exploiter proprement.

**Correction.** Ajouter des bornes métier (`1..N`), valider les dates réelles et contrôler les relations entre champs.

### P2-05 — Valeurs financières non finies acceptées

**Preuve.** `objectif_ca=NaN` et `objectif=NaN` passent la validation : `backend/server.py:5828-5837` et `backend/server.py:4821-4828`.

**Risque.** Totaux et comparaisons deviennent non déterministes, l'encodage JSON peut échouer et les tableaux de bord peuvent afficher des résultats faux.

**Correction.** Utiliser des types décimaux ou `allow_inf_nan=False`, puis vérifier `isfinite` avant toute écriture financière.

### P2-06 — Détails d'erreurs internes renvoyés au navigateur

**Preuve statique.** Plusieurs réponses incorporent directement `str(e)` ou `{e}`, notamment `backend/server.py:1594`, `1849`, `1872`, `4167`, `4200`, `4408`, `4743`, `4771`, `4790`, `7124` et `7786`.

**Risque.** Les réponses peuvent révéler des chemins, noms de fournisseurs, identifiants de requête, structure de fichiers ou autres détails utiles à un attaquant.

**Correction.** Journaliser l'exception côté serveur avec un identifiant de corrélation ; renvoyer au client un message stable et générique.

### P2-07 — Exports chargés entièrement en mémoire

**Preuve.** Jusqu'à 50 000 ventes/projets et 50 000 clients sont chargés, puis le CSV entier est dupliqué par `StringIO.getvalue()` : `backend/server.py:6472-6484` et `backend/server.py:6502-6516`.

**Risque.** Pic mémoire, latence et indisponibilité lors d'un gros export ou de plusieurs exports simultanés.

**Correction.** Paginer le curseur MongoDB et produire réellement le CSV par morceaux ; ajouter un plafond et une tâche asynchrone pour les gros volumes.

## P3 — cohérence produit

### P3-01 — Événement avec fin antérieure au début

**Preuve.** Les modèles acceptent librement `start_time` et `end_time`, et `create_event` les enregistre sans vérifier leur ordre : `backend/server.py:9036-9057` et `backend/server.py:9101-9118`.

**Risque.** Affichage incohérent du planning et notifications avec horaire impossible.

**Correction.** Valider les heures, exiger les deux ou aucune, et imposer une fin postérieure au début.

## Scénarios recensés dans cette passe

| Domaine nouveau | Scénarios exécutés ou revus |
|---|---:|
| Export et contenu actif | 3 |
| Action IA et résolution de vente | 1 |
| Coût/volume IA | 2 |
| Permissions secondaires et confidentialité | 6 |
| Stock et intégrité métier | 2 |
| Dates, heures et valeurs numériques | 5 |
| Erreurs et performance | 2 |
| **Total** | **21 familles de vérification**, dont **20 tests automatisés** |

## Ce qui doit encore être testé hors environnement local

Cette passe approfondit le code, mais ne peut pas simuler honnêtement les éléments suivants sans un environnement de staging isolé :

1. vrai MongoDB sous concurrence, panne réseau et reprise après crash ;
2. Stripe test mode avec webhook, rejeu, retard, remboursement, impayé et chargeback ;
3. fournisseur email réel, rebonds, liens, délivrabilité et limitation ;
4. fournisseur IA réel, prompt injection, timeout, quota, coût et contenu malveillant dans PDF/image ;
5. sauvegarde complète, restauration sur une base vide et mesure du temps de reprise ;
6. tests E2E avec chaque rôle, deux sociétés, homonymes, Chrome/Safari/Firefox/mobile et coupures réseau ;
7. charge avec volumes réalistes (clients, ventes, photos, exports, planning) ;
8. configuration du proxy, HTTPS, cookies, logs, alertes et secrets du déploiement final.

## Ordre de correction recommandé

1. Neutraliser les CSV et corriger la résolution regex de l'action IA.
2. Borner et limiter les appels IA ; borner et contrôler les mouvements de stock.
3. Fermer la route `check-attente-14j` et appliquer la matrice de visibilité aux cinq lectures secondaires.
4. Centraliser les validateurs date/heure/nombre fini/longueur et les appliquer à tous les modèles.
5. Masquer les exceptions internes et rendre les exports réellement progressifs.
6. Faire repasser les 20 tests de ce fichier, puis les 39 + 6 tests de non-régression.
7. Exécuter la campagne staging ci-dessus avant toute déclaration « prêt production ».

## Reproduction

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest audit.security_adversarial_round2 -v

PYTHONPATH=. ./.venv/bin/pytest -q \
  backend/test_security_invariants.py backend/test_preflight.py \
  backend/test_app_smoke.py backend/test_integration_security.py

cd frontend
CI=true npm test -- --watchAll=false --runInBand
```

