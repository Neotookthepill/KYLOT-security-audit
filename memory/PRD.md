# KYLOT / Archilot — Product Requirements

## Original problem statement
Multi-tenant SaaS pour direct sales et planning chantier d'une entreprise d'intervention à domicile.
Unifie création clients, tracking ventes, planification techniciens, commissions, réinterventions,
et assistant IA (KIK'S) capable d'exécuter des actions plateforme.

## User personas
- **Admin / Responsable** : accès total, config, gestion équipe, commissions
- **Commercial** : ventes propres, commissions propres, création clients
- **Technicien / Sous-traitant** : planning/kanban propre uniquement
- **Comptable** : commissions, ventes (lecture)
- **Super Admin** : cross-company (Emergent)

## Core requirements
- Multi-tenant strict (`company_id` sur tous les records), zéro suppression sur suspension
- RBAC granulaire par ressource × action × scope (own/team/all)
- Dashboard KPI cliquable, ranking, primes, notifications 14j
- Kanban / Calendar avec statuts custom + workflow (planifier → PROG → terminé)
- Commissions avec règles évolutives (CA + remise), historique cumulé mois par mois
- Réinterventions avec photos (avant/après)
- Assistant IA KIK'S multimodal (voix/photo/PDF), mémoire company-scoped, actions plateforme
- Global Search Cmd+K, Journal d'activité B2B, Onboarding premier login
- Pricing 3 plans (Essentiel / Équipe / Entreprise) basé sur nb utilisateurs

## Implémenté le 2026-10-14
- Chèque : option « Autre (préciser) » pour un nombre d'échéances libre (ex. 7 fois) — NewSaleSheet + EditSaleSheet (`ChequeInstallmentsSelect.jsx`)
- Nouvelle source de vente « Sous-traitance » (saleConstants, rapport mensuel, backend)
- Fix CA DE 50/50 dans le Classement du dashboard (`/dashboard/executive` → `_add_ranking_share`), testé par curl (10 000 € → 5 000 / 5 000)
- Module Prospecteur : rôle `prospecteur` (compte dédié, ne voit que sa page en lecture seule), menu entre Commissions et Stock, champ Prospecteur + commission fixe (€, boutons 400/500/600) dans Nouvelle/Modifier vente, page `/prospecteur` (stats, recherche, filtre, commission éditable admin/responsable uniquement). Endpoints `GET /api/prospecteurs`, `GET /api/prospection`, `PUT /api/prospection/{sid}`. Testé iteration_28 (100 %).
- Rôle `responsable_prospecteur` : voit tous les prospecteurs + CA généré + prestation/montant (commission non modifiable). Les prospecteurs ne voient plus ni prestation ni montant (masqués côté API). Vérifié par curl + screenshot.
- Le responsable prospection apparaît aussi dans le choix « Prospecteur » de Nouvelle/Modifier vente (libellé « (Responsable prospection) »).
- Fix retrait technicien multi-jours : la question « Uniquement un jour / Tout le chantier » s'affiche systématiquement (Planning ET Kanban, jours consécutifs ET jours supplémentaires), avec sélecteur de jour + puces « Retiré le jj/mm » restaurables. Testé iteration_29 (7/7).
- Page Carte (`/carte`, menu entre Clients et Utilisateurs) : carte Leaflet/OpenStreetMap, un point par client coloré selon sa catégorie client (mêmes couleurs que la page Clients), filtres par catégorie, popup (nom, adresse, téléphone, catégories, « Ouvrir la fiche client »). Géocodage gratuit via api-adresse.data.gouv.fr, mis en cache sur le client (`geo_lat`, `geo_lng`, `geo_key`), relocalisé si l'adresse change. Endpoint `GET /api/clients/map` (même périmètre RBAC que /clients).
- Prospecteur : filtre de période identique aux Ventes (Aujourd'hui / Semaine / Mois / Mois préc. / Année / Personnalisé), bloc « CA par prospecteur ». Rémunération = salaire de base (réglage société `prospect_smic_threshold` = 3 ventes/mois → `prospect_smic_amount` = 1 867 € par défaut) + commissions fixes saisies par vente. Barre de progression « x / 3 ventes » côté prospecteur.
- Règle rémunération prospecteur révisée : base 1 867 € acquise dès la 1re vente (couvre les ventes 1 à 3), commissions fixes ajoutées à partir de la 4e vente (ordre chronologique). Champ `prospect_commission_month` (YYYY-MM) choisi par admin/responsable via colonne « Mois com. » : déplace la rémunération sans changer le CA (le CA reste au mois de la vente). `PUT /api/prospection/{sid}` accepte `prospecteur_commission` et/ou `prospect_commission_month`.
- Ventes : la recherche reconnaît les sources (R1, Assist, CQ, CA, TAP, Sous-traitance / ST) en correspondance exacte + bandeau « Résultat de la recherche : X ventes · CA HT » (hors annulés/litiges, période sélectionnée).
- Carte : champ « Aller à une ville… » à côté du titre (géocodage api-adresse type municipality, zoom animé).
- Fiche client (ClientDetailDialog, ouverte depuis Clients ou la Carte) : section « Notes » multiples (auteur + date), ajout par tous ceux qui voient le client, suppression par l'auteur ou admin/responsable. Collection `client_notes`, endpoints `GET/POST /api/clients/{cid}/notes`, `DELETE /api/client-notes/{nid}`.
- Commission responsable prospection : carte « x / 12 ventes · 1 % ou 2 % · montant » sur la page Prospecteur (admin, responsable, responsable prospection). Calcul mois par mois sur le CA (mois de vente) de toutes les ventes prospecteurs hors annulés/litiges. Réglages société `prospect_mgr_goal_sales` (12), `prospect_mgr_rate_below` (1 %), `prospect_mgr_rate_above` (2 %).
- Fix commission évolutive selon CA : (1) ventes sans palier enregistré (créées/éditées via EditSaleSheet) → fallback seuil 30 000 € / 10 % / 13 % (ou réglages société) au lieu d'être ignorées ; (2) DE : le commercial 2 hérite du type évolutif (`commission_type_2` vide → hérite de `commission_type`) et est recalculé sur SON CA mensuel ; (3) EditSaleSheet affiche/sauve le palier évolutif ; NewSale/EditSale envoient `commission_type_2`. Vérifié par curl (35 k€ → toutes à 13 %, y compris slot DE).
- Progression annuelle : dédoublonnage des prénoms seuls (« Thomas », « Nolan », « Lucelia »…) fusionnés dans le nom complet unique correspondant (insensible accents/casse), CA et objectif repris.
- Responsable prospection : salaire de base propre (`prospect_mgr_base_amount`, défaut 2 329,97 € brut, non soumis à la base prospecteur) + commission % + primes configurables (`prospect_mgr_bonuses` : liste {name, metric ca|sales, threshold, amount}, mensuelles, cumulables, sur le CA/nb ventes de l'équipe). Éditeur dans Paramètres (`ProspectMgrBonuses.jsx`), carte détaillée sur la page Prospecteur (base + commission + primes = total).
- Chantiers multi-jours : validation journée par journée (`POST /projects/{pid}/complete` avec `day`, stockée dans `project.days_done`). Statut global « termine » + notifications seulement quand toutes les journées (consécutives + `extra_dates`) sont validées ; journée future refusée (date Europe/Paris). Sélecteur de journée dans la confirmation ; Planning colore chaque case selon sa propre journée. Vérifié curl + screenshot.
- Prospecteur : la ligne du responsable prospection dans « CA et rémunération par prospecteur » affiche sa base responsable (2 329,97 €).
- Connexion hors ligne : après une connexion réussie en ligne, empreinte PBKDF2-SHA256 (150 000 itérations, sel aléatoire) + jeton + profil gardés sur l'appareil (`qylot_offline_creds`, plusieurs comptes possibles). Sans réseau, le login vérifie l'empreinte et ouvre la session. Messages : « Identifiants incorrects (connexion hors ligne) » / « Connectez-vous une première fois avec Internet ». La synchro ne supprime plus une opération sur 401 (attente de reconnexion). Vérifié par screenshot.
- Mobile (iPhone) : Stock en cartes, ProjectDialog dates empilées, feuilles Vente plein écran, pieds de page/entêtes qui passent à la ligne (Paramètres, Rapport, Commissions, Planning), padding homogène p-4 md:p-8, espace sous la bulle d'aide, colonnes collantes Heures sup opaques, correctif champs date iOS (index.css). Bug desktop Stock corrigé (colonne « Besoin chantiers » affichait le seuil d'alerte). Libellé « RAC ». Testé iteration_31/32.
- Mode hors ligne : adaptateur axios (`lib/api.js`) + `lib/offline.js` (IndexedDB via idb-keyval) — GET servis depuis le cache sans réseau, créations/modifs/suppressions mises en file d'attente (ids temporaires `offline-*` remappés), rejouées dans l'ordre au retour du réseau (événement online + toutes les 20 s). Conflits champ par champ → dialogue bloquant « Garder ma version / Garder la version actuelle » (les champs non conflictuels sont conservés). Bandeau `OfflineBar` (hors ligne / X en attente / synchronisation). Session conservée hors ligne (déconnexion seulement sur 401). Service worker `public/sw.js` (coquille de l'app, production uniquement). Testé iteration_30 (tous les flux OK après corrections).
- Ventes « Direction » : nom « Direction » reconnu (y compris « LA DIRECTION », « Directeur », « DG »… — correspondance par mot) comme attribution valide (plus compté dans « ventes à attribuer »), option « Direction » dans le dialogue d'attribution (`bind-commercial` user_id `__direction__`). Vérifié par curl.



## What's been implemented (session iter203-218, Feb 2026)
- ✅ **iter218 — Chantier vert quand la vente est encaissée (`argent_recupere`)** : `CalendarPage.jsx` calcule un `effectiveStatus` — si `p.sale_status === "argent_recupere"`, l'affichage bascule sur `encaisse` (vert émeraude) même si `project.status` est resté `termine` côté base. Le bouton « Chantier terminé » est également masqué dans ce cas (cycle clos). Fix le bug GORNY : chantier encaissé restait bleu dans le Planning.
- ✅ **iter217 — Admin peut renotifier « Chantier terminé »** : le bouton vert « Chantier terminé » reste visible pour admin/responsable/super_admin même quand le chantier est déjà `termine` (libellé changé en « Renotifier commercial » dans ce cas). Le backend `complete_project` acceptait déjà l'appel admin de façon idempotente — la notification cloche + email sont donc renvoyées à chaque clic. Seul `encaisse` (argent récupéré) masque le bouton.
- ✅ **iter216 — Synchronisation temps réel Kanban ↔ Planning** : quand un statut de chantier change (drag & drop dans le Kanban, sauvegarde depuis `ProjectDialog` sur le Planning, ou validation « Chantier terminé »), un événement `kylot:project-updated` est diffusé. Les deux pages (`Kanban.jsx` et `CalendarPage.jsx`) l'écoutent et rechargent leur liste instantanément. Résultat : le changement de couleur et de colonne se reflète immédiatement des deux côtés.
- ✅ **iter215 — Planning : chantiers visibles peu importe le statut** : `_fetch_projects_list` accepte désormais un paramètre `keep_closed`. Le Kanban Chantiers garde son ancien comportement (masque `argent_recupere`, `annule`, `litige`). Le Planning (`/api/planning/projects`) utilise `keep_closed=True` et n'exclut plus que `annule`. Fix la disparition des chantiers finis / à encaisser / chèque récupéré du calendrier — à la demande de l'utilisateur, un chantier reste visible peu importe son statut, sauf s'il est annulé.
- ✅ **iter214 — Fix erreur cryptique "String should match pattern"** : `EditSaleSheet.jsx` et `NewSaleSheet.jsx` envoyaient `sale_date: form.sale_date` — quand vide, Pydantic (`Optional[str]` avec pattern strict YYYY-MM-DD) rejetait la chaîne vide. Corrigé en `sale_date: form.sale_date || null`. En parallèle, `formatApiError` (lib/api.js) traduit maintenant les erreurs Pydantic 422 en français lisible (« Date de vente : format invalide (attendu AAAA-MM-JJ) », « Nom client est obligatoire », etc.) au lieu d'afficher le message technique brut.
- ✅ **iter213 — Jours non consécutifs sur un chantier + suppression du champ Priorité** : nouveau champ `extra_dates: List[str]` sur `ProjectUpdate` — permet d'ajouter des dates isolées non consécutives (ex : chantier lundi + mercredi + vendredi). UI dans `ProjectDialog` : section « Jours supplémentaires (non consécutifs) » avec date picker + bouton Ajouter + chips avec ×. Le rendu Planning fusionne dates consécutives + extras dans l'ordre chronologique — le label « (2/3) » reste cohérent. Le champ « Priorité » a été retiré du dialogue Chantier (jugé inutile par l'utilisateur ; le champ reste en DB pour compat).
- ✅ **iter212 — Email « Chantier terminé » aux admins** : le toggle `chantier_terminated` de la page Paramètres envoie désormais l'email aux administrateurs & responsables (en plus du commercial concerné qui le reçoit toujours via le flux direct de `complete_project`). Modification dans `_notify_project` (kind=terminated) : liste des destinataires = tous les users `admin`/`responsable` avec email valide. Description du toggle mise à jour.
- ✅ **iter211 — Retrait technicien : ce jour OU tout le chantier** : sur un chantier multi-jours, décocher un technicien depuis une case précise ouvre un dialogue à 3 boutons : « Uniquement ce jour » (ajoute à `day_exclusions[date]`), « Tout le chantier » (retrait global), « Annuler ». La liste de checkboxes affiche « Retiré ce jour » avec badge ambre + `line-through` quand une exclusion existe. Le Planning applique automatiquement les exclusions par jour au rendu. Backend : nouveau champ `day_exclusions: Dict[str, List[str]]` dans `ProjectUpdate`. Testé HTTP 200 sur `GET /projects`.
- ✅ **iter210 — Commissions : masquage individuel des mois (mode fantôme)** : chaque onglet de mois passé/futur peut être masqué via un bouton × au hover (mois courant non masquable). Persistance localStorage `pylot_hidden_months`. Toggle « Afficher les mois masqués (N) » révèle les onglets ghostés (italique + opacité 40%) avec bouton « restaurer ». Bouton « Tout restaurer » à côté. Les données ne sont jamais perdues — seul l'affichage change.
- ✅ **iter209 — Planning indépendant de Chantiers** : nouveau endpoint `GET /api/planning/projects` gated par `planning.view` (au lieu de `projects.view`). Frontend `CalendarPage.jsx` bascule dessus. Retirer « Chantiers » à un technicien ne vide plus son planning. Refactor de la logique métier dans `_fetch_projects_list(user, include_deleted, perm_resource)`. Testé : `GET /api/projects` et `GET /api/planning/projects` retournent chacun HTTP 200.
- ✅ **iter208 — Menu Chantiers masqué pour techniciens** : `Layout.jsx` — `denyRoles: ["technicien", "sous_traitant"]` sur l'entrée « Chantiers ». `App.js` — `HomeRedirect` techniciens/sous-traitants → `/planning`. `PermRoute` fallback global changé en `/planning`. Le bouton vert « Chantier terminé » reste accessible depuis la fiche chantier ouverte via le Planning (iter206 déjà en place).
- ✅ **iter207 — Renommage stock par technicien** : nouvel endpoint `PUT /api/stock/{sid}/rename` — un technicien peut renommer un produit qu'il a lui-même créé (`created_by_technician_by_me`). Manager peut renommer n'importe quel produit. Anti-collision par `product_key` normalisé. Trace via `stock_movements` et `audit_log`. Frontend : composant `ProductNameCell` avec crayon inline dans « Mon stock ».
- ✅ **iter206 — Fix accès technicien sur chantier** : matching FUZZY (accent-insensible + tokens partagés) sur `PUT /api/projects/{pid}` et `POST /api/projects/{pid}/complete` — remplace le regex strict `^Sébastien$`. Fixe simultanément « Chantier introuvable » à l'ajout de photo et à la validation « Chantier terminé » côté technicien mobile. Idem sur `isAssignedTech`/`withYouOthers` dans `ProjectDialog.jsx` → le bouton vert « Chantier terminé » apparaît maintenant pour les techniciens assignés même si l'accent/le nom complet diverge. Bonus : PINCH mobile + drag tactile ajoutés au lightbox photo du chantier (`onTouchStart`/`Move`/`End`) → zoom fonctionnel sur iOS/Android.
- ✅ **iter205 — Commissions : mois passés + exclusion non finançable** : ajout d'une fenêtre glissante `pastMonths` (défaut 6, max 24) — onglets mois précédents + option "Payé au mois de… (il y a X mois)" dans le sélecteur, pour affecter une vente ancienne à un mois passé. Bouton `-` à gauche pour étendre la fenêtre passée. Statut `non_financable` exclu au même titre que `annule`/`litige` sur `/api/commissions` (frontend filter), `/api/commissions.pdf`, `/api/commissions/history` et le compte des commissions à valider du Dashboard.

- ✅ **iter204 — Anti-doublon commissions** : garde backend `/api/commissions` — si les 2 slots d'une vente DE désignent le même commercial (par `user_id` ou nom normalisé), on force `is_de=False` → une seule ligne. Dédup finale par `(sale_id, commercial normalisé)`. Fix « BDC 2204 Billot apparaît 2× sur Thomas ». Key React `${sale_id}-${slot}` pour supporter les vraies DE.
- ✅ **iter203 — Extraction devis/photo plus fiable** : passage de `gpt-4o-mini` → `gpt-4o` (vision) sur `/ai/analyze-devis`, `/clients/import/pdf/parse`, et l'auto-extract in-chat. Prompt renforcé avec règle « recopie mot-à-mot, plutôt null que faux ». DPI PDF 180 → 240.

## What's been implemented (session récente iter178-179)
- ✅ Historique des primes gagnées (backend `/api/commissions/history` + composant frontend `CommissionHistory.jsx`) — matrice commercial × mois, 6/12/24 mois glissants
- ✅ Bug filtre Commissions par commercial : match accent-insensible (Théo ↔ theo ↔ THEO)
- ✅ Photos sur réintervention : modèle backend `photos: List[str]` + camera/galerie dans `ReinterventionDialog` (compression 1600px JPEG 0.8, max 8, lightbox)
- ✅ Bloc "À faire aujourd'hui" sur Dashboard (TodayTodos, localStorage par user)
- ✅ Sécurité multi-tenant : audit IDOR, suspension sans suppression, webhook idempotent
- ✅ Pricing basé sur nb users (Essentiel/Équipe/Entreprise)
- ✅ Global Search Cmd+K
- ✅ B2B Activity Journal (audit log lisible)
- ✅ First-login Onboarding Dialog
- ✅ Backend KIK'S actions (`/api/kiks/act` + `/api/kiks/confirm/{id}`)
- ✅ Frontend AIHelper wiring `/ai/action` + `/ai/action/execute` (déjà en place)
- ✅ (2026-10-15) Responsive mobile global (fiche chantier, stock en cartes, ventes plein écran, rapport mensuel, planning) + libellé paiement « RAC »
- ✅ (2026-10-15) Vente en DE : type de commission indépendant pour le commercial 2 (Fixe / Évolutive selon CA), dans Nouvelle vente et Modifier la vente — `commission_type_2` envoyé explicitement
- ✅ (2026-10-15) Journées OFF : saisie d'une période « Du … Au … » (une journée OFF créée par jour, max 366)
- ✅ (2026-10-15) Rôles prospection (prospecteur / responsable prospecteur) : visibilité limitée aux ventes avec prospecteur (ventes, clients, carte, chantiers, planning, réinterventions, dashboards) même si des permissions plus larges sont accordées
- ✅ (2026-10-15) Planning simplifié pour les rôles prospection : accès automatique au Planning, pastilles colorées « nom — adresse, ville », non cliquables (pas de fiche détaillée, données réduites côté API)
- ✅ (2026-10-15) Page Prospecteur : bloc « CA et rémunération par prospecteur » refait en cartes (nb de ventes en gros, % de l'équipe, CA, rémunération, classement #1 mis en avant) — suppression des barres





## Roadmap / Backlog

### P1
- Câblage frontend KIK'S Actions vers `/api/kiks/act` (recherche client/vente, list projets par statut) — endpoints backend déjà prêts, il manque un routeur NLU côté AIHelper
- Emails Resend (BLOCKED — domaine à vérifier côté Emergent)

### P2
- Multi-company user switching + planning unifié technicien inter-sociétés
- Extension photos réintervention → export PDF SAV
- Filtre "Mon commercial" par défaut pour les commerciaux dans Commissions

### P3
- Push Notifications (Web Push + APNs/FCM)
- Refactoring `server.py` (>9400 lignes) → modules `routes/models/services`

## Blocked / Support
- Production DB mapping ("Blanc Pro" vs "CPF" company_id) → support@emergent.sh
- Resend domain verification → support@emergent.sh

## Key API endpoints (récents)
- `GET /api/commissions/history?months=12` — matrice historique
- `POST /api/reinterventions` — accepte `photos: List[str]` (data URI)
- `POST /api/kiks/act` + `POST /api/kiks/confirm/{id}` — actions IA opérationnelles
- `GET /api/search?q=` — global search Cmd+K

## Credentials de test
Voir `/app/memory/test_credentials.md`.
