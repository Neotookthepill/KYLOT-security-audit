# Inventaire statique des 172 routes KYLOT

Les colonnes sont des indices statiques conservateurs. Un tiret signifie que le contrôle n'est pas visible dans le corps de la route ; il peut exister dans un helper appelé.

| Méthode | Route | Ressource | Opération | Fonction/ligne | Auth attendue visible | Contrôle visible | ID direct | Société | Propriétaire | Audit | Idempotence | Limite |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| POST | `/auth/register` | auth | création/action | `register:801` | publique | — | — | oui | — | — | — | — |
| POST | `/auth/login` | auth | création/action | `login:899` | publique | — | — | oui | — | — | — | — |
| POST | `/auth/logout` | auth | création/action | `logout:917` | publique | — | — | — | — | — | oui | — |
| GET | `/auth/me` | auth | lecture/export | `me:942` | session | — | — | oui | — | — | — | — |
| POST | `/me/onboarding-complete` | me | création/action | `mark_onboarding_complete:961` | session | — | — | — | oui | — | oui | — |
| GET | `/search` | search | lecture/export | `global_search:992` | session | scope vente | — | oui | — | — | oui | oui |
| POST | `/clients/backfill-categories` | clients | création/action | `backfill_client_categories:1205` | admin | — | — | oui | — | — | — | — |
| GET | `/client-categories` | client-categories | lecture/export | `get_client_categories:1244` | session | permission | — | oui | — | — | — | — |
| PUT | `/client-categories` | client-categories | remplacement/action | `put_client_categories:1250` | session | permission | — | oui | — | oui | oui | — |
| PUT | `/clients/{cid}/category` | clients | remplacement/action | `assign_client_category:1267` | session | permission | oui | — | oui | oui | — | — |
| GET | `/clients` | clients | lecture/export | `list_clients:1303` | session | permission | — | oui | — | — | — | oui |
| GET | `/clients/map` | clients | lecture/export | `clients_map:1335` | session | permission | — | oui | — | — | — | oui |
| POST | `/clients` | clients | création/action | `create_client:1368` | session | permission | — | oui | oui | oui | — | — |
| PUT | `/clients/{cid}` | clients | remplacement/action | `update_client:1376` | session | permission | oui | — | — | oui | — | — |
| DELETE | `/clients/{cid}` | clients | suppression | `delete_client:1388` | session | permission | oui | — | — | oui | — | — |
| GET | `/clients/{cid}/notes` | clients | lecture/export | `list_client_notes:1404` | session | permission | oui | oui | — | — | — | oui |
| POST | `/clients/{cid}/notes` | clients | création/action | `add_client_note:1413` | session | permission | oui | oui | oui | — | — | — |
| DELETE | `/client-notes/{nid}` | client-notes | suppression | `delete_client_note:1426` | session | — | oui | oui | oui | — | — | — |
| POST | `/clients/bulk` | clients | création/action | `create_clients_bulk:1480` | session | permission | — | oui | oui | — | — | — |
| POST | `/clients/import/parse` | clients | création/action | `parse_import_file:1603` | session | permission | — | — | — | — | — | — |
| POST | `/clients/import/execute` | clients | création/action | `execute_import_file:1652` | session | permission | — | oui | oui | — | oui | — |
| POST | `/clients/import/pdf/parse` | clients | création/action | `parse_client_pdf:1821` | session | permission | — | oui | oui | — | oui | oui |
| POST | `/clients/import/pdf/create` | clients | création/action | `create_client_from_pdf:1926` | session | permission | — | oui | oui | — | oui | — |
| GET | `/sales` | sales | lecture/export | `list_sales:2092` | session | permission, scope vente | — | oui | — | — | — | oui |
| GET | `/sales/commercial-month-ca` | sales | lecture/export | `sales_commercial_month_ca:2121` | session | permission | — | oui | — | — | — | oui |
| POST | `/sales` | sales | création/action | `create_sale:2167` | session | permission | — | oui | oui | oui | — | — |
| PUT | `/sales/{sid}` | sales | remplacement/action | `update_sale:2269` | session | permission, scope vente | oui | oui | — | oui | — | — |
| POST | `/sales/check-attente-14j` | sales | création/action | `check_attente_14j:2391` | session | — | — | oui | — | — | oui | oui |
| DELETE | `/sales/{sid}` | sales | suppression | `delete_sale:2438` | session | permission, scope vente | oui | oui | — | oui | — | — |
| GET | `/projects` | projects | lecture/export | `list_projects:2626` | session | permission | — | — | — | — | — | oui |
| GET | `/planning/projects` | planning | lecture/export | `list_planning_projects:2635` | session | permission | — | — | — | — | — | oui |
| GET | `/projects/{pid}` | projects | lecture/export | `get_project_full:2654` | session | permission, scope projet | oui | oui | — | — | — | — |
| PUT | `/projects/{pid}` | projects | remplacement/action | `update_project:2705` | session | permission, scope projet | oui | oui | — | oui | — | oui |
| DELETE | `/projects/{pid}` | projects | suppression | `delete_project:2800` | session | permission, scope projet | oui | oui | oui | oui | — | — |
| POST | `/projects/{pid}/restore` | projects | création/action | `restore_project:2816` | session | permission, scope projet | oui | oui | — | oui | — | — |
| POST | `/projects/{pid}/confirm` | projects | création/action | `confirm_project:2835` | session | permission, scope projet | oui | oui | — | — | — | — |
| GET | `/projects/{pid}/notes` | projects | lecture/export | `list_project_notes:2908` | session | permission, scope projet | oui | oui | — | — | — | oui |
| PUT | `/projects/{pid}/notes/{technician_name}` | projects | remplacement/action | `upsert_project_note:2935` | session | scope projet | oui | oui | oui | — | oui | — |
| DELETE | `/projects/{pid}/notes/{technician_name}` | projects | suppression | `delete_project_note:2984` | session | scope projet | oui | oui | — | — | — | — |
| POST | `/ai/corrections` | ai | création/action | `log_ai_correction:3014` | session | manager | — | oui | oui | — | — | — |
| GET | `/ai/corrections` | ai | lecture/export | `list_ai_corrections:3031` | session | manager | — | oui | — | — | — | oui |
| DELETE | `/ai/corrections/{cid}` | ai | suppression | `delete_ai_correction:3038` | session | manager | oui | oui | — | — | — | — |
| GET | `/ai/memory` | ai | lecture/export | `list_ai_memory:3114` | session | — | — | — | — | — | — | oui |
| POST | `/ai/memory` | ai | création/action | `create_ai_memory:3121` | session | manager | — | oui | oui | oui | — | — |
| PATCH | `/ai/memory/{mid}` | ai | modification | `update_ai_memory:3142` | session | manager | oui | oui | oui | oui | — | — |
| DELETE | `/ai/memory/{mid}` | ai | suppression | `delete_ai_memory:3168` | session | manager | oui | oui | oui | oui | — | — |
| GET | `/dashboard/company-comparison` | dashboard | lecture/export | `dashboard_company_comparison:3300` | session | permission | — | oui | — | — | — | oui |
| GET | `/dashboard/executive` | dashboard | lecture/export | `dashboard_executive:3372` | session | permission, manager, scope vente | — | oui | — | — | — | oui |
| GET | `/dashboard/activity` | dashboard | lecture/export | `dashboard_activity:3698` | session | permission | — | oui | — | — | — | oui |
| GET | `/dashboard/stats` | dashboard | lecture/export | `dashboard_stats:3834` | session | permission, scope vente | — | oui | — | — | — | oui |
| POST | `/kiks/act` | kiks | création/action | `kiks_act:3966` | session | scope vente | — | oui | oui | — | — | oui |
| POST | `/kiks/confirm/{pending_id}` | kiks | création/action | `kiks_confirm:4075` | session | permission | oui | oui | oui | — | — | — |
| POST | `/ai/chat` | ai | création/action | `ai_chat:4101` | session | — | — | oui | oui | — | — | — |
| POST | `/ai/chat-multipart` | ai | création/action | `ai_chat_multipart:4129` | session | — | — | oui | oui | — | — | oui |
| POST | `/ai/action` | ai | création/action | `ai_action:4393` | rôles ventes | — | — | — | oui | — | — | — |
| POST | `/ai/action/execute` | ai | création/action | `ai_action_execute:4498` | rôles ventes | permission | — | oui | — | — | — | — |
| POST | `/ai/analyze-devis` | ai | création/action | `ai_analyze_devis:4719` | session | permission | — | — | oui | — | — | oui |
| GET | `/team` | team | lecture/export | `list_team:4848` | session | — | — | oui | — | — | — | oui |
| POST | `/team` | team | création/action | `create_team_member:4865` | admin | — | — | oui | — | — | oui | — |
| PUT | `/team/{tid}` | team | remplacement/action | `update_team_member:4923` | admin | — | oui | oui | — | — | oui | oui |
| DELETE | `/team/{tid}` | team | suppression | `delete_team_member:4977` | admin | — | oui | oui | — | — | — | — |
| GET | `/reports/monthly` | reports | lecture/export | `monthly_report:5074` | session | permission | — | — | — | — | — | oui |
| GET | `/dashboard/annual` | dashboard | lecture/export | `dashboard_annual:5082` | session | permission, scope vente | — | oui | — | — | — | oui |
| GET | `/commissions.pdf` | commissions.pdf | lecture/export | `commissions_pdf:5206` | session | permission | — | oui | — | — | — | oui |
| GET | `/reports/monthly.pdf` | reports | lecture/export | `monthly_report_pdf:5349` | session | permission | — | — | — | — | — | oui |
| GET | `/commissions` | commissions | lecture/export | `list_commissions:5638` | session | permission, scope vente | — | oui | — | — | oui | oui |
| GET | `/commissions/history` | commissions | lecture/export | `commissions_history:5755` | session | permission | — | — | — | — | — | oui |
| GET | `/bonuses` | bonuses | lecture/export | `list_bonuses:5998` | session | — | — | oui | — | — | — | oui |
| POST | `/bonuses` | bonuses | création/action | `create_bonus:6008` | session | manager | — | oui | oui | — | — | — |
| PUT | `/bonuses/{bid}` | bonuses | remplacement/action | `update_bonus:6030` | session | manager | oui | oui | — | — | — | — |
| DELETE | `/bonuses/{bid}` | bonuses | suppression | `delete_bonus:6043` | session | manager | oui | oui | — | — | — | — |
| GET | `/bonuses/progress` | bonuses | lecture/export | `bonuses_progress:6054` | session | — | — | oui | — | — | oui | oui |
| GET | `/bonuses/awards` | bonuses | lecture/export | `list_bonus_awards:6103` | session | — | — | oui | — | — | — | oui |
| GET | `/projects/{pid}/bonuses` | projects | lecture/export | `list_project_bonuses:6142` | session | scope projet | oui | oui | — | — | — | oui |
| POST | `/projects/{pid}/bonuses` | projects | création/action | `create_project_bonus:6154` | session | manager, scope projet | oui | oui | oui | — | oui | — |
| PUT | `/project-bonuses/{bid}` | project-bonuses | remplacement/action | `update_project_bonus:6195` | session | manager | oui | oui | — | — | — | — |
| DELETE | `/project-bonuses/{bid}` | project-bonuses | suppression | `delete_project_bonus:6209` | session | manager | oui | oui | — | — | — | — |
| GET | `/project-bonuses/monthly` | project-bonuses | lecture/export | `project_bonuses_monthly:6219` | session | — | — | oui | — | — | — | oui |
| GET | `/settings` | settings | lecture/export | `get_settings:6260` | session | — | — | oui | — | — | — | — |
| PUT | `/settings` | settings | remplacement/action | `update_settings:6308` | session | permission | — | oui | — | — | oui | — |
| GET | `/users` | users | lecture/export | `list_users:6334` | admin | — | — | oui | — | — | — | oui |
| POST | `/users` | users | création/action | `create_user:6342` | admin | — | — | oui | oui | oui | — | — |
| PUT | `/users/{uid}` | users | remplacement/action | `update_user:6381` | admin | — | oui | oui | — | — | — | — |
| DELETE | `/users/{uid}` | users | suppression | `delete_user:6414` | admin | — | oui | oui | oui | oui | — | — |
| GET | `/users/{uid}/permissions` | users | lecture/export | `get_user_permissions:6436` | admin | — | oui | oui | — | — | — | — |
| PUT | `/users/{uid}/permissions` | users | remplacement/action | `update_user_permissions:6444` | admin | — | oui | oui | — | oui | — | — |
| GET | `/roles/defaults` | roles | lecture/export | `get_role_defaults:6457` | admin | — | — | — | — | — | — | — |
| GET | `/export/sales.csv` | export | lecture/export | `export_sales:6464` | session | scope vente | — | oui | — | — | — | oui |
| GET | `/export/projects.csv` | export | lecture/export | `export_projects:6487` | session | — | — | oui | — | — | — | oui |
| POST | `/cron/rappel-chantiers-j1` | cron | création/action | `cron_rappel_chantiers_j1:6845` | publique | — | — | — | — | — | oui | — |
| POST | `/cron/rappel-chantiers-j1/test` | cron | création/action | `cron_rappel_test:6879` | admin | — | — | — | — | — | — | — |
| POST | `/cron/bilan-mensuel` | cron | création/action | `cron_bilan_mensuel:6972` | publique | — | — | — | — | — | oui | — |
| POST | `/cron/bilan-mensuel/test` | cron | création/action | `cron_bilan_test:7002` | admin | — | — | — | — | — | — | — |
| POST | `/payments/checkout` | payments | création/action | `create_checkout:7083` | admin | — | — | oui | oui | — | — | — |
| GET | `/payments/status/{session_id}` | payments | lecture/export | `get_payment_status:7144` | session | — | oui | oui | oui | — | — | — |
| POST | `/stripe/webhook` | stripe | création/action | `stripe_webhook:7268` | publique | — | — | — | — | — | oui | — |
| GET | `/subscription/me` | subscription | lecture/export | `my_subscription:7340` | session | — | — | oui | oui | — | — | — |
| GET | `/subscription/catalog` | subscription | lecture/export | `subscription_catalog:7385` | session | — | — | — | — | — | — | — |
| GET | `/overtime` | overtime | lecture/export | `list_overtime:7415` | session | permission | — | oui | — | — | — | oui |
| POST | `/overtime` | overtime | création/action | `upsert_overtime:7538` | session | permission | — | oui | oui | oui | oui | — |
| PUT | `/overtime/{oid}/validate` | overtime | remplacement/action | `validate_overtime:7616` | session | permission | oui | oui | oui | — | — | — |
| POST | `/overtime/{oid}/refuse` | overtime | création/action | `refuse_overtime:7638` | session | permission | oui | oui | oui | — | — | — |
| PUT | `/overtime/{oid}/reject` | overtime | remplacement/action | `reject_overtime:7659` | session | permission | oui | oui | — | — | — | — |
| GET | `/overtime/history` | overtime | lecture/export | `overtime_history:7672` | session | permission | — | oui | — | — | — | oui |
| POST | `/overtime/validate-tech` | overtime | création/action | `validate_all_pending_for_tech:7730` | session | permission | — | oui | oui | — | — | — |
| POST | `/payments/portal` | payments | création/action | `create_billing_portal:7755` | admin | — | — | — | oui | — | — | — |
| GET | `/superadmin/companies` | superadmin | lecture/export | `list_companies:7810` | super-admin | — | — | oui | — | — | — | oui |
| POST | `/superadmin/companies` | superadmin | création/action | `create_company:7819` | super-admin | — | — | oui | oui | — | — | — |
| DELETE | `/superadmin/companies/{cid}` | superadmin | suppression | `delete_company:7861` | super-admin | — | oui | oui | — | — | — | — |
| GET | `/company/me` | company | lecture/export | `my_company:7887` | session | — | — | oui | — | — | — | — |
| GET | `/notifications` | notifications | lecture/export | `list_notifications:8121` | session | — | — | oui | oui | — | — | oui |
| PUT | `/notifications/{nid}/read` | notifications | remplacement/action | `mark_notif_read:8131` | session | — | oui | oui | oui | — | — | — |
| POST | `/notifications/read-all` | notifications | création/action | `mark_all_notif_read:8139` | session | — | — | oui | oui | — | — | — |
| DELETE | `/notifications/{nid}` | notifications | suppression | `delete_notification:8145` | session | — | oui | oui | oui | — | — | — |
| GET | `/audit` | audit | lecture/export | `list_audit:8177` | admin | — | — | oui | — | — | — | oui |
| POST | `/admin/reconcile-commercials` | admin | création/action | `admin_reconcile_commercials:8461` | session | manager | — | oui | — | — | oui | — |
| GET | `/prospects` | prospects | lecture/export | `list_prospects:8683` | session | permission | — | oui | — | — | — | oui |
| POST | `/prospects` | prospects | création/action | `create_prospect:8699` | session | permission | — | oui | oui | oui | — | — |
| PUT | `/prospects/{pid}` | prospects | remplacement/action | `update_prospect:8717` | session | permission | oui | — | — | oui | — | — |
| DELETE | `/prospects/{pid}` | prospects | suppression | `delete_prospect:8736` | session | permission | oui | — | — | oui | — | — |
| POST | `/prospects/{pid}/convert` | prospects | création/action | `convert_prospect_to_client:8748` | session | permission | oui | oui | oui | oui | — | — |
| GET | `/prospects/meta/sources` | prospects | lecture/export | `prospect_sources_meta:8782` | session | — | — | — | — | — | — | — |
| GET | `/absences` | absences | lecture/export | `list_absences:8801` | session | — | — | oui | — | — | — | oui |
| POST | `/absences` | absences | création/action | `create_absence:8820` | session | permission | — | oui | oui | oui | — | — |
| DELETE | `/absences/{aid}` | absences | suppression | `delete_absence:8857` | session | permission | oui | oui | — | oui | — | — |
| GET | `/reinterventions` | reinterventions | lecture/export | `list_reinterventions:8890` | session | — | — | oui | — | — | — | oui |
| POST | `/reinterventions` | reinterventions | création/action | `create_reintervention:8931` | session | permission | — | oui | oui | oui | — | — |
| PUT | `/reinterventions/{rid}` | reinterventions | remplacement/action | `update_reintervention:8954` | session | permission | oui | oui | — | oui | — | — |
| DELETE | `/reinterventions/{rid}` | reinterventions | suppression | `delete_reintervention:8971` | session | permission | oui | oui | — | oui | — | — |
| GET | `/off-days` | off-days | lecture/export | `list_off_days:8991` | session | — | — | oui | — | — | — | oui |
| POST | `/off-days` | off-days | création/action | `create_off_day:9000` | session | permission | — | oui | oui | oui | oui | — |
| DELETE | `/off-days/{oid}` | off-days | suppression | `delete_off_day:9024` | session | permission | oui | oui | — | oui | — | — |
| GET | `/events` | events | lecture/export | `list_events:9088` | session | — | — | oui | — | — | — | oui |
| POST | `/events` | events | création/action | `create_event:9102` | session | permission | — | oui | oui | oui | — | — |
| PUT | `/events/{eid}` | events | remplacement/action | `update_event:9132` | session | permission | oui | oui | — | oui | — | — |
| DELETE | `/events/{eid}` | events | suppression | `delete_event:9159` | session | permission | oui | oui | — | oui | — | — |
| GET | `/stock/catalog` | stock | lecture/export | `stock_catalog:9282` | session | stock RBAC | — | oui | — | — | — | oui |
| GET | `/stock` | stock | lecture/export | `list_stock:9291` | session | manager, stock RBAC | — | oui | oui | — | — | oui |
| GET | `/stock/product/{product_key}/projects` | stock | lecture/export | `stock_product_projects:9508` | session | stock RBAC | oui | oui | — | — | — | oui |
| POST | `/stock/tech-create-and-hold` | stock | création/action | `tech_create_and_hold:9573` | session | — | — | oui | oui | oui | — | — |
| POST | `/stock` | stock | création/action | `upsert_stock:9628` | session | manager | — | oui | oui | — | oui | — |
| PUT | `/stock/{sid}/rename` | stock | remplacement/action | `rename_stock_product:9663` | session | manager | oui | oui | oui | oui | — | — |
| PUT | `/stock/{sid}/override` | stock | remplacement/action | `set_stock_override:9705` | session | manager | oui | oui | oui | oui | — | — |
| DELETE | `/stock/{sid}/override/{field}` | stock | suppression | `delete_stock_override:9729` | session | manager | oui | oui | oui | oui | — | — |
| POST | `/stock/{sid}/receive` | stock | création/action | `receive_stock:9749` | session | manager | oui | oui | oui | — | — | — |
| DELETE | `/stock/{sid}` | stock | suppression | `delete_stock:9771` | session | manager | oui | oui | — | — | — | — |
| GET | `/stock/{sid}/holders` | stock | lecture/export | `list_stock_holders:9783` | session | manager, stock RBAC | oui | oui | oui | — | — | — |
| POST | `/stock/{sid}/holder` | stock | création/action | `set_stock_holder:9798` | session | manager | oui | oui | oui | oui | — | — |
| POST | `/stock/{sid}/transfer` | stock | création/action | `transfer_stock:9837` | session | manager | oui | oui | oui | oui | — | oui |
| POST | `/stock/{sid}/holder-adjust` | stock | création/action | `adjust_holder_stock:9909` | session | stock RBAC | oui | oui | oui | oui | — | — |
| GET | `/stock/movements` | stock | lecture/export | `list_stock_movements:9944` | session | manager, stock RBAC | — | oui | oui | — | — | oui |
| GET | `/me/dashboard-config` | me | lecture/export | `get_my_dashboard_config:10015` | session | — | — | oui | oui | — | — | — |
| PUT | `/me/dashboard-config` | me | remplacement/action | `put_my_dashboard_config:10025` | session | — | — | oui | oui | — | oui | — |
| DELETE | `/me/dashboard-config` | me | suppression | `reset_my_dashboard_config:10036` | session | — | — | oui | oui | — | — | — |
| POST | `/projects/{pid}/complete` | projects | création/action | `complete_project:10072` | session | scope projet | oui | oui | — | oui | — | — |
| GET | `/sales/unmatched-commercials` | sales | lecture/export | `list_unmatched_commercials:10250` | session | permission | — | oui | — | — | — | oui |
| POST | `/sales/{sid}/bind-commercial` | sales | création/action | `bind_commercial:10286` | session | permission, manager | oui | oui | — | oui | — | — |
| GET | `/prospecteurs` | prospecteurs | lecture/export | `list_prospecteurs:10436` | session | — | — | oui | — | — | — | oui |
| GET | `/prospection` | prospection | lecture/export | `list_prospection:10441` | session | — | — | oui | oui | — | — | oui |
| PUT | `/prospection/{sid}` | prospection | remplacement/action | `update_prospection_commission:10466` | session | — | oui | oui | — | — | — | — |
| GET | `/sale-statuses` | sale-statuses | lecture/export | `get_sale_statuses:10481` | session | — | — | oui | — | — | — | — |
| GET | `/sale-statuses/usage` | sale-statuses | lecture/export | `get_sale_statuses_usage:10488` | session | — | — | oui | — | — | — | — |
| PUT | `/sale-statuses` | sale-statuses | remplacement/action | `put_sale_statuses:10501` | session | permission | — | oui | — | — | oui | — |
| POST | `/sale-statuses/reassign` | sale-statuses | création/action | `reassign_sale_status:10542` | session | permission | — | oui | oui | — | oui | — |
| GET | `/health` | health | lecture/export | `_health:10604` | publique | — | — | — | — | — | — | — |
| GET | `/healthz` | healthz | lecture/export | `_health:10604` | publique | — | — | — | — | — | — | — |
| GET | `/api/health` | health | lecture/export | `_health:10604` | publique | — | — | — | — | — | — | — |
| GET | `/api/healthz` | healthz | lecture/export | `_health:10604` | publique | — | — | — | — | — | — | — |
| GET | `/ready` | ready | lecture/export | `_ready:10611` | publique | — | — | — | — | — | — | — |
| GET | `/readyz` | readyz | lecture/export | `_ready:10611` | publique | — | — | — | — | — | — | — |
| GET | `/api/ready` | ready | lecture/export | `_ready:10611` | publique | — | — | — | — | — | — | — |
| GET | `/api/version` | version | lecture/export | `_version:10625` | publique | — | — | — | — | — | — | — |
