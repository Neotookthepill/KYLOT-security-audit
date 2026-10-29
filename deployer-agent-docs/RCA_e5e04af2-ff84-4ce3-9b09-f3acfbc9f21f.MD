# RCA — QYLOT/CPF "32 ventes à attribuer" (Ventes page)

## Scope
READ-ONLY production MongoDB diagnosis. No data changed, no redeploy.
- Deployment: `sales-dispatch-6` (QYLOT), active run `e5e04af2-ff84-4ce3-9b09-f3acfbc9f21f`.
- DB: `sales-dispatch-6-test_database`, collection `sales`.

## Note on company identity
The `companies` collection holds only two companies: **KEYLOT** (`id:"default"`) and **Acme SARL**. There is no literal `CPF`/`QYLOT` record — those are aliases. All 32 unmatched sales carry `company_id:"default"` (KEYLOT). So "CPF" here = `company_id:"default"`.

## Query
`sales` where `commercial_unmatched == true`:
- Total: **32** — exactly matches the "32 ventes à attribuer" counter.
- `distinct company_id` → `["default"]` (all 32).
- `distinct commercial` → `["LA DIRECTION"]` — a SINGLE distinct value, which proves there are NO hidden whitespace / case / accent variants on the `commercial` field.

## Exact stored values (repr) + counts

### commercial (all 32)
- `'LA DIRECTION'` × 32 — uppercase, single interior space, 12 chars, no leading/trailing whitespace.
- `commercial_user_id`: `null` on all 32.

### commercial_2 (3 distinct values)
| commercial_2 (repr) | count | commercial_2_user_id | is_de |
|---|---|---|---|
| `''` (empty) | 26 | `null` (or field absent) | `false` |
| `'Nolan'` | 4 | `'632abfa1-cf71-4d13-ba9b-d87b26cd71f6'` | `true` |
| `'Théo Dudal'` | 2 | `'9e8273cb-6791-4223-b13f-03fb9485694c'` | `true` |

`'Théo Dudal'` contains `é` (U+00E9); no stray whitespace observed. The 6 sales with a `commercial_2` set are exactly the ones with `is_de:true` and a populated `commercial_2_user_id`.

## Root cause
The endpoint `GET /api/sales/unmatched-commercials` excludes only sales whose `commercial` name NORMALIZES to exactly `"direction"`. These 32 sales store the primary commercial as the exact string **`'LA DIRECTION'`** (with the French article "LA"), which normalizes to `"la direction"` — NOT `"direction"`. Therefore the exclusion filter does not catch them, and all 32 fall through into the "à attribuer" counter even though they are Direction sales. `commercial_user_id` is `null` on every one of the 32, which is why `commercial_unmatched` is `true` to begin with.

## Suggested fixes
1. **Code (E1):** Broaden the normalization/exclusion in `GET /api/sales/unmatched-commercials` so a primary commercial that normalizes to `"la direction"` (strip the leading French article "la"/"le"/"les", or match `direction` as a contained token) is treated the same as `"direction"` and excluded. This would drop all 32 out of the counter.
2. **Data alternative (change_mongo_data):** If the preferred canonical value is the bare `"Direction"`, normalize the stored `commercial` field on these 32 docs (`company_id:"default"`, `commercial:"LA DIRECTION"`) to the exact value the exclusion expects. Note this is a production-data edit and out of scope for this read-only pass.

Either fix removes the 32 from the counter. Fix #1 (code) is the durable one since new "LA DIRECTION" entries will keep appearing otherwise.
