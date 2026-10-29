# RCA — KEYLOT iter108 deploy failure (run f968b4e7-d474-40ef-afd2-06a9af1f3c7e)

## Outcome
Diagnosed — **source fix required in the frontend**. NOT applied to your source by me (the deployer only edits a throwaway sandbox copy). Apply the fix below in the preview/source environment, then re-trigger the deploy.

## Failure
- Failed step: `build_image` (Cloud Build step #8 `frontend-build-push`).
- Terminating error: `craco build` → `Failed to compile. [eslint] src/pages/Kanban.jsx — Syntax error: Unexpected token, expected "," (231:24)`.

## Root cause
In `frontend/src/pages/Kanban.jsx`, the per-card action ternary
`{filter === "__deleted" ? ( <button>↺ Restaurer</button> ) : ( ... )}` had its **else branch open with `) : (`** and then place **two bare JSX expression containers** directly inside those parentheses:
- `{columns.map((c) => { ... })}` (the "→ move" buttons), and
- `{canEdit && p.status === "termine" && ( ...✓ Terminé... )}` (the new iter108 button).

A parenthesized JSX expression must evaluate to a **single** node. Two sibling `{...}` containers with no wrapping element/fragment is invalid — the Babel/ESLint parser hits the second-line brace and reports `Unexpected token, expected ","` at 231:24. The regression was introduced when the iter108 "✓ Terminé" button block was inserted into the else branch without a fragment wrapper.

## Fix (wrap the else-branch content in a fragment)
In `frontend/src/pages/Kanban.jsx`, else branch of the `filter === "__deleted"` ternary:

Change:
```jsx
) : (
  {columns.map((c) => {
    ...
  })}
  {canEdit && p.status === "termine" && (
    <button ...>✓ Terminé</button>
  )}
)}
```
to:
```jsx
) : (
  <>
    {columns.map((c) => {
      ...
    })}
    {canEdit && p.status === "termine" && (
      <button ...>✓ Terminé</button>
    )}
  </>
)}
```
i.e. add `<>` immediately after `) : (` (before `{columns.map`) and `</>` immediately before the ternary's closing `)}`. No other logic changes.

## Verification
- Applied the two-line wrapper edit to the sandbox copy and re-inspected the region: the else branch now returns a single `<>...</>` fragment whose children are the two `{...}` containers — the exact construct the parser rejected is resolved, and the enclosing `<div className="flex gap-1 mt-3 flex-wrap">` remains balanced (`</>` closes at 258, ternary `)}` at 259, `</div>` at 270).
- NOTE: this eph sandbox image ships only python3 (no node/yarn), so I could not execute `craco build` here. Verification is static/structural, not a runtime compile. It's a textbook JSX fragment correction and directly removes the reported parse error, but please rely on the normal build to confirm.

## Next step for E1
Apply the fragment wrapper in the source `frontend/src/pages/Kanban.jsx`, then re-trigger the deploy. The rest of iter108 (status `encaisse`, `visible` filter, `dashboard_activity` recalibration) is unaffected by this fix.
