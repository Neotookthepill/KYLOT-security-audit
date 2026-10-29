# RCA — run 5e6c0af2-52bb-486d-9a7d-bd597ba2da25 (KEYLOT / sales-dispatch-6)

## Outcome
Deploy failed at **deploy_k8s** (health check never passed). Diagnosed — **source fix required**, NOT applied by me (I do not mutate your source).

## Symptom
`resume_pipeline` reported: `deployment failed to become ready: timed out waiting for the condition`. Rollout logs show the backend crashing on startup and nginx then failing every `/health` probe with `connect() failed (111: Connection refused) ... upstream: http://127.0.0.1:8001/health`.

## Root cause
The build succeeded, but uvicorn crashes on **import** of `backend/server.py` — so the FastAPI backend never binds port 8001 and the container is never ready:

```
File "/app/backend/server.py", line 6998
    raise HTTPException(status_code=403, detail="Accès refusé")    name = data.product_name.strip()
                                                                   ^^^^
SyntaxError: invalid syntax
```

This is **NOT** in the new iter127 endpoint. It is in the pre-existing `@api_router.post("/stock")` handler `upsert_stock`. A newline + indentation was lost, collapsing two statements onto one line. A single Python syntax error anywhere in the module makes the whole app fail to import, which is why an unrelated-looking handler took the deploy down.

## Fix (verified in eph sandbox — `python3 -m py_compile server.py` now exits 0)
In `backend/server.py`, split the merged line back into two lines with correct indentation.

Before (line 6998):
```python
async def upsert_stock(data: StockUpsert, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")    name = data.product_name.strip()
```

After:
```python
async def upsert_stock(data: StockUpsert, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    name = data.product_name.strip()
```

I reproduced the exact `SyntaxError` on the pulled source, applied only this split, and re-ran `py_compile` → exit 0. No other change was needed for the module to compile.

## Recommended guard before re-triggering
Run `python3 -m py_compile backend/server.py` (or `python -m compileall backend`) in preview before republishing — it catches this class of error in <1s and would have blocked this run. Also worth a quick grep for any other lines where an iter112→iter127 edit may have merged statements.

## Next step
Apply the one-line fix in the source environment, then re-trigger the deploy. Do NOT redeploy the current source unchanged — it will fail identically at import.
