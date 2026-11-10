import axios from "axios";
import { toast } from "sonner";
import { cacheKey, readCache, writeCache, enqueue, isSkipped, syncNow, setOnline, refreshPending, clearExpiredSessionState } from "@/lib/offline";

// An empty value deliberately uses the current origin. This is the safest
// production topology: the public reverse proxy serves the SPA and forwards
// /api to the private backend, so no API hostname is baked into the bundle.
const backendOrigin = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");

const api = axios.create({
  baseURL: `${backendOrigin}/api`,
  withCredentials: true,
});

// Adaptateur hors ligne : GET servis depuis le cache sans réseau, modifications mises en file d'attente.
// En ligne, les GET de configuration sont dédupliqués et mémorisés quelques secondes :
// sans cela, Layout + pages + dialogues relançaient /settings, /team et /sale-statuses
// 3 à 4 fois au même moment (5–7 s perçues sur une connexion Render froide).
const baseAdapter = axios.getAdapter(axios.defaults.adapter);
const ok = (config, data, statusText) => ({ data, status: 200, statusText, headers: {}, config, request: {} });
const GET_CACHE_TTL = 15000;
const DYNAMIC_GET_CACHE_TTL = 5000;
const staticGet = (url) => /^\/(settings|team|sale-statuses|users|client-categories|dashboard\/executive)(\?|$)/.test(url || "");
// Les listes métier changent peu pendant une navigation. Un cache mémoire très
// court rend les retours arrière instantanés sans servir des données périmées
// après une mutation (clearApiGetCache est appelé sur toute écriture).
const dynamicGet = (url) => /^\/(sales|clients|projects|stock|audit|commissions|prospects|prospection|events|absences|off-duty|overtime|challenges|notifications|dashboard|reinterventions)(\?|$)/.test(url || "");
const cacheableGet = (url) => staticGet(url) || dynamicGet(url);
const memoryGet = new Map();
const pendingGet = new Map();
export const clearApiGetCache = () => { memoryGet.clear(); pendingGet.clear(); };
api.defaults.adapter = async (config) => {
  const method = (config.method || "get").toLowerCase();
  if (config._direct || isSkipped(config.url) || (typeof FormData !== "undefined" && config.data instanceof FormData)) return baseAdapter(config);
  if (method !== "get") { clearApiGetCache(); }
  if (method === "get") {
    const k = cacheKey(config);
    const memo = memoryGet.get(k);
    const ttl = staticGet(config.url) ? GET_CACHE_TTL : DYNAMIC_GET_CACHE_TTL;
    if (cacheableGet(config.url) && memo && Date.now() - memo.ts < ttl && (!config.responseType || config.responseType === "json")) {
      return ok(config, memo.data, "OK (cache mémoire)");
    }
    if (cacheableGet(config.url) && pendingGet.has(k)) return pendingGet.get(k);
    const request = (async () => {
      try {
        const r = await baseAdapter(config);
        if (r.status === 200 && (!config.responseType || config.responseType === "json")) {
          writeCache(k, r.data);
          if (cacheableGet(config.url)) memoryGet.set(k, { data: r.data, ts: Date.now() });
        }
        return r;
      } catch (e) {
        if (e.response) throw e;
        const cached = await readCache(k);
        if (cached !== undefined) return ok(config, cached, "OK (hors ligne)");
        throw e;
      } finally {
        pendingGet.delete(k);
      }
    })();
    if (cacheableGet(config.url)) pendingGet.set(k, request);
    return request;
  }
  if (navigator.onLine) {
    return baseAdapter(config);
  }
  // Les photos utilisent des POST atomiques : ils doivent aussi pouvoir être
  // mis en file hors ligne, comme les anciens PUT.
  const offlinePhotoWrite = method === "post" && /\/projects\/[^/]+\/photos(?:\/remove)?$/.test(config.url || "");
  if (!["put", "patch"].includes(method) && !offlinePhotoWrite) {
    const error = new Error("Cette action nécessite une connexion internet.");
    error.code = "OFFLINE_UNSAFE_MUTATION";
    throw error;
  }
  const queued = await enqueue(config);
  toast.info("Enregistré sur l'appareil — sera synchronisé au retour du réseau", { id: "offline-saved" });
  return ok(config, queued, "Queued (hors ligne)");
};

const directSend = (cfg) => api.request({ ...cfg, _direct: true });
export const syncOffline = () => syncNow(directSend);
if (typeof window !== "undefined") {
  window.addEventListener("online", () => { setOnline(true); syncOffline(); });
  window.addEventListener("offline", () => setOnline(false));
  // Initial replay is deliberately deferred until AuthContext confirms /auth/me.
  refreshPending();
  setInterval(() => { if (navigator.onLine) syncOffline(); }, 20_000);
}

export async function downloadApiFile(path, fallbackFilename) {
  const response = await api.get(path, { responseType: "blob" });
  const disposition = response.headers?.["content-disposition"] || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  const filename = encoded ? decodeURIComponent(encoded[1]) : (plain?.[1] || fallbackFilename || "export.pdf");
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

// Global response handler: the HttpOnly session is cleared server-side.
// Skip the login/register endpoints so the login screen can display its own error.
api.interceptors.response.use(
  (resp) => resp,
  async (err) => {
    const status = err?.response?.status;
    const url = err?.config?.url || "";
    const publicAuthPage = typeof window !== "undefined"
      && ["/login", "/forgot-password", "/reset-password"].some((p) => window.location.pathname.startsWith(p));
    const publicAuthCall = /\/auth\/(login|register|forgot-password|reset-password)/.test(url);
    const isAuthMe = /\/auth\/me/.test(url);
    if (status === 401 && isAuthMe) {
      // AuthContext décide lui-même du retry/redirect. Un 401 transitoire sur
      // /auth/me au refresh ne doit pas expulser l'utilisateur avant la 2e tentative.
      await clearExpiredSessionState();
    } else if (status === 401 && !publicAuthCall && !publicAuthPage) {
      await clearExpiredSessionState();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        // Preserve the current route to redirect after re-login (optional)
        try { sessionStorage.setItem("post_login_redirect", window.location.pathname); } catch (_) {}
        window.location.replace("/login?expired=1");
      }
    }
    return Promise.reject(err);
  }
);

export function formatApiError(err) {
  const status = err?.response?.status;
  if ([502, 503, 504].includes(status)) {
    return "Le serveur est momentanément indisponible. Réessayez dans quelques instants.";
  }
  if (!err?.response && /network|failed to fetch|load failed/i.test(String(err?.message || ""))) {
    return "Connexion impossible. Vérifiez votre réseau puis réessayez.";
  }
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Une erreur est survenue";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // iter214 — traduction FR conviviale des erreurs de validation Pydantic (422)
    // qu'on voyait apparaître crûment dans les toasts (« String should match pattern... »).
    const friendlyField = (loc) => {
      if (!Array.isArray(loc)) return null;
      const last = loc[loc.length - 1];
      if (typeof last !== "string") return null;
      const map = {
        sale_date: "Date de vente", desired_intervention_date: "Date d'intervention",
        scheduled_date: "Date de début", date_from: "Date de début", date_to: "Date de fin",
        commission_month: "Mois de paiement", month: "Mois", date: "Date",
        amount: "Montant", commercial: "Commercial", client_name: "Nom client",
        email: "Email", phone: "Téléphone", product_name: "Nom du produit",
        duration_days: "Durée", quantity: "Quantité",
      };
      return map[last] || last.replace(/_/g, " ");
    };
    const humanize = (e) => {
      const field = friendlyField(e?.loc);
      const type = e?.type || "";
      const msg = e?.msg || "";
      if (type === "string_pattern_mismatch" || /match pattern/i.test(msg)) {
        return field ? `« ${field} » : format invalide (attendu AAAA-MM-JJ).` : "Format de date invalide (attendu AAAA-MM-JJ).";
      }
      if (type.startsWith("email") || /email address/i.test(msg)) {
        return field ? `« ${field} » : adresse email invalide.` : "Adresse email invalide.";
      }
      if (type === "missing" || /field required/i.test(msg)) {
        return field ? `« ${field} » est obligatoire.` : "Champ obligatoire manquant.";
      }
      if (/greater than or equal/i.test(msg) || /less than or equal/i.test(msg)) {
        return field ? `« ${field} » : valeur hors bornes.` : msg;
      }
      return field ? `« ${field} » : ${msg}` : msg;
    };
    return detail.map(humanize).filter(Boolean).join(" · ");
  }
  // iter192 — Cas `detail` = objet (ex : {code, message, existing_users}). On extrait
  // le champ `message` ou `msg` pour éviter d'afficher `[object Object]` à l'utilisateur.
  if (typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    if (typeof detail.msg === "string") return detail.msg;
    try { return JSON.stringify(detail); } catch (_) { return "Erreur inconnue"; }
  }
  return String(detail);
}

export default api;
