# Matrice de tests — 4 novembre 2026

Préproduction : https://kylot-preview.onrender.com  
Backend : `56b98e4`  
Frontend : `3fdfdc9`

## Résultats exécutés

| Suite | Résultat |
|---|---|
| Backend `pytest backend/test_*.py` | **117 passed** |
| E2E staging `staging_flow.js` | **22 checks** |
| E2E MFA `mfa_flow.js` | **9 checks** |
| E2E offline `offline_flow.js` | **5 checks** |
| E2E imports `import_flow.js` | **7 checks** |
| E2E téléphones `phone_flow.js` | **6 checks** |
| E2E événements `event_flow.js` | **10 checks** |
| Navigateur (`browser_matrix.js`) | **26 checks** (Chromium desktop + mobile) |
| Charge légère (`load_smoke.js`) | **110 requêtes, 0 erreur** |
| Frontend Jest | 34 tests |
| Sauvegarde Atlas | archive + checksum |
| Restauration Atlas | `kylot_staging_restore` vérifiée |

## Couvert

- isolation multi-tenant sur clients, ventes, chantiers, utilisateurs, challenges, audit, notifications ;
- auth : cookie HttpOnly/Secure/SameSite, mot de passe erroné, compte inactif, token absent/expiré/supprimé ;
- MFA : setup TOTP, challenge, code de secours, désactivation ;
- prospection : mois depuis chantier, date de fin, override manuel, permissions ;
- challenge : classement assistances/CA, ventes hors période, clôture/snapshot ;
- ventes DE : split 50/50, taux indépendants, anti-double comptage, mois de commission ;
- imports : collage en masse, doublons, fichier CSV avec mapping ;
- offline : file IndexedDB, absence d'écriture serveur, rejeu, vidange ;
- planning : multi-jours, jours supplémentaires, exclusions, dates invalides, soft-delete/restore ;
- rôles : commercial, technicien, comptable, responsable, sous-traitant, prospecteur ;
- ventes avancées : DE, taux indépendants, anti-double comptage, commission arrondie ;
- accessibilité de base : images, boutons, champs catégories clients ;
- responsive mobile sans débordement horizontal ;
- latence légère sur endpoints et pages ;
- sauvegarde/restauration.

## Non couvert / à faire

### P0

- MFA **obligatoire** : mécanisme disponible mais désactivé par défaut (`MFA_ENFORCE_ADMINS=false`) ;
- Firefox et WebKit/Safari : installation Playwright bloquée, non testés ;
- performance réelle et charge sur staging ;
- rate limiting login/MFA sous charge ;
- tests navigateur Safari/Firefox ;
- audit d'accessibilité complet (axe).

### P1

- imports PDF et XLSX réels ;
- conflits de synchronisation offline ;
- Stripe sandbox : checkout, webhook, remboursement, échec ;
- emails, IA, géocodage ;
- RGPD : export/suppression ;
- monitoring et alerte.

## Blocages externes

- Stripe : compte test, produits et clés non configurés.
- Emails/IA : clés non configurées.
- Charge réelle : pas d'outil de charge sur le staging.
