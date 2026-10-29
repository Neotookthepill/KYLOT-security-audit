import { createStore, get, set, del, keys } from "idb-keyval";

// Mode hors ligne : cache des GET + file d'attente des modifications rejouée au retour du réseau
const cacheStore = createStore("qylot-offline", "cache");
const queueStore = createStore("qylot-outbox", "queue");
const QUEUE_KEY = "ops";
const MAP_KEY = "idmap";

const SKIP = [/\/auth\//, /\/kiks\//, /\/ai\//, /\/export\//, /\/check-attente-14j/];
const ID_RE = /^([0-9a-f]{8}-[0-9a-f-]{27,}|offline-[\w-]+)$/i;

const listeners = new Set();
let state = { online: typeof navigator === "undefined" ? true : navigator.onLine, pending: 0, syncing: false, conflict: null, lastError: null };
// No cached business data or queued write may be read/replayed before /auth/me
// has established the current server-side identity.
let identity = null;
const emit = (patch) => { state = { ...state, ...patch }; listeners.forEach((l) => l(state)); };
export const subscribeOffline = (fn) => { listeners.add(fn); fn(state); return () => listeners.delete(fn); };

export const isSkipped = (url) => SKIP.some((r) => r.test(url || ""));
export const setOfflineIdentity = (userId) => { identity = userId ? String(userId) : null; };
const pathOf = (url) => (url || "").split("?")[0].replace(/\/+$/, "");
const collectionOf = (path, method) => {
  const segs = path.split("/");
  if (method !== "post" && ID_RE.test(segs[segs.length - 1] || "")) segs.pop();
  return segs.join("/");
};
const idOf = (path) => { const last = path.split("/").pop(); return ID_RE.test(last || "") ? last : null; };
export const cacheKey = (config) => {
  const params = config.params ? JSON.stringify(config.params) : "";
  return `${identity || "unauthenticated"} GET ${pathOf(config.url)}${params ? `?${params}` : ""}`;
};

export const clearOfflineData = async () => {
  for (const key of await keys(cacheStore)) await del(key, cacheStore);
  for (const key of await keys(queueStore)) await del(key, queueStore);
  emit({ pending: 0, conflict: null, lastError: null });
};

export const clearSensitiveSessionStorage = () => {
  if (typeof window === "undefined") return;
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i -= 1) {
      const key = sessionStorage.key(i) || "";
      if (key === "kylot_prefill_sale" || key === "kylot_ai_draft_v1" || key.startsWith("kylot_ai_draft_v1:")) {
        sessionStorage.removeItem(key);
      }
    }
  } catch (_) {}
};

export const clearSensitiveClientState = async () => {
  await clearOfflineData();
  clearSensitiveSessionStorage();
  setOfflineIdentity(null);
};

// L'adaptateur reçoit le corps brut (chaîne JSON) avant transformResponse : on stocke toujours l'objet parsé
const asJson = (d) => { if (typeof d !== "string") return d; try { return JSON.parse(d); } catch { return d; } };
export const readCache = async (k) => asJson(await get(k, cacheStore));
export const writeCache = (k, data) => set(k, asJson(data), cacheStore).catch(() => {});

const getQueue = async () => (await get(QUEUE_KEY, queueStore)) || [];
const saveQueue = async (q) => { await set(QUEUE_KEY, q, queueStore); emit({ pending: q.length }); };
export const refreshPending = async () => emit({ pending: (await getQueue()).length });

// Parcourt les tableaux d'une réponse (racine ou 1 niveau) pour y appliquer fn
const mapArrays = (data, fn) => {
  if (Array.isArray(data)) return fn(data);
  if (data && typeof data === "object") {
    const out = { ...data };
    let touched = false;
    for (const [k, v] of Object.entries(out)) if (Array.isArray(v)) { out[k] = fn(v); touched = true; }
    return touched ? out : data;
  }
  return data;
};

const findBase = async (coll, id) => {
  for (const k of await keys(cacheStore)) {
    if (typeof k !== "string") continue;
    if (!k.startsWith(`${identity} GET `)) continue;
    const p = k.slice(`${identity} GET `.length).split("?")[0];
    if (p !== coll && p !== `${coll}/${id}`) continue;
    const data = await readCache(k);
    if (data && !Array.isArray(data) && data.id === id) return data;
    let hit = null;
    mapArrays(data, (arr) => { hit = hit || arr.find((x) => x && x.id === id); return arr; });
    if (hit) return hit;
  }
  return null;
};

// Applique la modification aux réponses en cache pour que l'écran reflète le travail hors ligne
const patchCaches = async (method, coll, id, item) => {
  for (const k of await keys(cacheStore)) {
    if (typeof k !== "string") continue;
    if (!k.startsWith(`${identity} GET `)) continue;
    const p = k.slice(`${identity} GET `.length).split("?")[0];
    const data = await readCache(k);
    if (p === `${coll}/${id}` && data && !Array.isArray(data)) {
      if (method === "delete") await del(k, cacheStore); else await writeCache(k, { ...data, ...item });
      continue;
    }
    if (p !== coll) continue;
    const next = mapArrays(data, (arr) => {
      if (method === "post") return [item, ...arr];
      if (method === "delete") return arr.filter((x) => !x || x.id !== id);
      return arr.map((x) => (x && x.id === id ? { ...x, ...item } : x));
    });
    if (next !== data) await writeCache(k, next);
  }
};

const parseBody = (data) => { if (typeof data !== "string") return data; try { return JSON.parse(data); } catch { return data; } };

export const enqueue = async (config) => {
  const method = (config.method || "get").toLowerCase();
  const path = pathOf(config.url);
  const coll = collectionOf(path, method);
  const body = parseBody(config.data) || {};
  const tempId = method === "post" ? `offline-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}` : null;
  const id = tempId || idOf(path);
  const baseItem = method === "post" || !id ? null : await findBase(coll, id);
  const base = baseItem && body && typeof body === "object" ? Object.fromEntries(Object.keys(body).map((k) => [k, baseItem[k]])) : null;
  const op = { qid: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, method, url: config.url, params: config.params || null, data: body, tempId, coll, id, base, at: new Date().toISOString() };
  const q = await getQueue();
  q.push(op);
  await saveQueue(q);
  const item = method === "post" ? { ...body, id: tempId, _offline: true, created_at: op.at } : { ...(baseItem || {}), ...body, id };
  if (id) await patchCaches(method, coll, id, item);
  return method === "delete" ? { ok: true, offline: true } : item;
};

const swapIds = (value, map) => {
  if (!Object.keys(map).length) return value;
  let s = typeof value === "string" ? value : JSON.stringify(value);
  for (const [t, r] of Object.entries(map)) s = s.split(t).join(r);
  return typeof value === "string" ? s : JSON.parse(s);
};

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

const serverItem = async (send, coll, id) => {
  try { return (await send({ method: "get", url: `${coll}/${id}` })).data; } catch (e) {
    if (!e.response) throw e;
  }
  try {
    const data = (await send({ method: "get", url: coll })).data;
    let hit = null;
    mapArrays(data, (arr) => { hit = hit || arr.find((x) => x && x.id === id); return arr; });
    return hit;
  } catch (e) { if (!e.response) throw e; return null; }
};

let resolver = null;
export const resolveConflict = (choice) => { if (resolver) { resolver(choice); resolver = null; } };

let running = false;
export const syncNow = async (send) => {
  if (running || !identity || !navigator.onLine) return;
  running = true;
  emit({ syncing: true, lastError: null });
  let done = 0;
  try {
    let q = await getQueue();
    const map = (await get(MAP_KEY, queueStore)) || {};
    while (q.length) {
      const op = q[0];
      const url = swapIds(op.url, map);
      const data = swapIds(op.data, map);
      let skip = false;
      let sendData = data;
      // Un enregistrement créé hors ligne ne peut pas avoir été modifié par quelqu'un d'autre : pas de contrôle de conflit
      if (op.base && !String(op.id || "").startsWith("offline-") && (op.method === "put" || op.method === "patch")) {
        const id = swapIds(op.id, map);
        const srv = await serverItem(send, swapIds(op.coll, map), id);
        if (srv) {
          const fields = Object.keys(data || {}).filter((k) => !same(srv[k], op.base[k]) && !same(srv[k], data[k]))
            .map((k) => ({ key: k, mine: data[k], server: srv[k] }));
          if (fields.length) {
            emit({ conflict: { op, fields, label: srv.client_name || srv.name || srv.bdc || srv.title || id } });
            const choice = await new Promise((res) => { resolver = res; });
            emit({ conflict: null });
            if (choice === "server") {
              const drop = new Set(fields.map((f) => f.key));
              sendData = Object.fromEntries(Object.entries(data).filter(([k]) => !drop.has(k)));
              skip = Object.keys(sendData).length === 0;
            }
          }
        }
      }
      if (!skip) {
        try {
          const r = await send({ method: op.method, url, data: sendData, params: op.params });
          if (op.tempId && r?.data?.id) { map[op.tempId] = r.data.id; await set(MAP_KEY, map, queueStore); }
        } catch (e) {
          if (!e.response || e.response.status === 401) break;
          emit({ lastError: `${op.method.toUpperCase()} ${op.url} : ${e.response?.data?.detail || e.response.status}` });
        }
      }
      q = q.slice(1);
      await saveQueue(q);
      done += 1;
    }
    if (!q.length) await del(MAP_KEY, queueStore);
  } finally {
    running = false;
    emit({ syncing: false });
    if (done) window.dispatchEvent(new CustomEvent("qylot:synced", { detail: { count: done } }));
  }
};

export const setOnline = (online) => emit({ online });
