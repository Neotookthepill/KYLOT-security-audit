import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  TrendingUp, Euro, Users, HardHat, CheckCircle2, Clock, Trophy,
  Bell, ArrowRight, ArrowUp, ArrowDown, Percent, Wallet, ListChecks, Sparkles,
  CalendarClock, GripVertical, EyeOff, Eye, RotateCcw, Settings2, Plus, Check,
  ChevronLeft, ChevronRight, CalendarDays, X, Phone, User as UserIcon, UserCheck, UserX,
  Maximize2,
} from "lucide-react";
import { toast } from "sonner";
import NewSaleSheet from "@/components/NewSaleSheet";
import EditSaleSheet from "@/components/EditSaleSheet";
import TodayTodos from "@/components/TodayTodos";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useSettings } from "@/contexts/SettingsContext";
import { useAuth } from "@/contexts/AuthContext";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

/** Robust local ISO date (YYYY-MM-DD) — no UTC conversion to avoid the +/-1 day offset. */
const toIsoLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseIsoLocal = (s) => {
  if (!s) return new Date();
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
};
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const startOfWeek = (d) => { const x = new Date(d); const wd = (x.getDay() + 6) % 7; x.setDate(x.getDate() - wd); return x; };
const FR_DAYS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const fmtDayLabel = (iso, today) => {
  const d = parseIsoLocal(iso);
  if (iso === today) return "Aujourd'hui";
  const yest = toIsoLocal(addDays(parseIsoLocal(today), -1));
  const tmrw = toIsoLocal(addDays(parseIsoLocal(today), 1));
  if (iso === yest) return "Hier";
  if (iso === tmrw) return "Demain";
  return `${FR_DAYS[d.getDay()]} ${d.getDate()} ${FR_MONTHS[d.getMonth()]}`;
};
const fmtShortDate = (iso) => {
  if (!iso) return "";
  const d = parseIsoLocal(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
};

const Delta = ({ pct }) => {
  if (pct == null) return null;
  const up = pct >= 0;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up ? "text-emerald-700" : "text-red-600"}`}>
      <Icon size={10} />{Math.abs(pct)}% <span className="text-slate-400 font-normal">vs mois préc.</span>
    </span>
  );
};

function Stat({ label, value, icon: Icon, hint, testId, delta, accent, onClick }) {
  const clickable = typeof onClick === "function";
  return (
    <Card
      className={`p-5 border-slate-200 shadow-sm fade-up ${clickable ? "cursor-pointer hover:shadow-md hover:border-slate-300 transition" : ""}`}
      data-testid={testId}
      onClick={clickable ? onClick : undefined}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } } : undefined}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="overline">{label}</p>
          <p className="font-display text-3xl font-semibold tracking-tight mt-2">{value}</p>
          {delta != null ? <div className="mt-1"><Delta pct={delta} /></div> : hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
        </div>
        <div className={`h-10 w-10 rounded-lg grid place-items-center ${accent || "bg-slate-100 text-slate-700"}`}>
          <Icon size={18} />
        </div>
      </div>
    </Card>
  );
}

const PERIODS = [
  { key: "prev", label: "Mois préc." },
  { key: "month", label: "Ce mois-ci" },
  { key: "next", label: "Mois suivant" },
  { key: "year", label: "Année" },
];

// Human labels for widget keys (used in "Add block" list).
const WIDGET_LABELS = {
  ca_hero: "CA & Objectif",
  sales_count: "Ventes (compteur)",
  today_todos: "À faire aujourd'hui",
  activity: "Activité chantiers",
  events: "Événements à venir",
  alerts: "À traiter",
  commissions: "Commissions du mois",
  overtime: "Heures sup à valider",
  ranking: "Classement commercial",
  recent_sales: "Ventes récentes",
};
// iter182 — Éclatement de `stats` en `sales_count` (Ventes) + `today_todos` (À faire),
// pour permettre à l'utilisateur de placer Ventes à côté de Heures sup et redimensionner
// chaque bloc librement (⅓ / ½ / ⅔ / plein).
const DEFAULT_ORDER = ["ca_hero", "activity", "sales_count", "overtime", "today_todos", "events", "alerts", "commissions", "ranking", "recent_sales"];
// Tailles par défaut (grille 12-col). 6 = ½, 12 = plein.
const DEFAULT_SIZES = {
  ca_hero: 12,
  activity: 12,
  sales_count: 6,
  today_todos: 6,
  overtime: 6,
  events: 6,
  alerts: 6,
  commissions: 6,
  ranking: 6,
  recent_sales: 6,
};
const ALLOWED_SIZES = [4, 6, 8, 12];
const SIZE_LABEL = { 4: "⅓", 6: "½", 8: "⅔", 12: "1" };
// Migration transparente : anciens ordres contenant `stats` → `sales_count + today_todos`
// iter200 — On DÉDUPLIQUE toujours pour éviter les doublons de blocs (bug Théo :
// plusieurs cartes « À faire aujourd'hui » à cause d'une migration re-jouée).
const migrateOrder = (arr) => {
  if (!Array.isArray(arr) || !arr.length) return DEFAULT_ORDER;
  const raw = [];
  for (const k of arr) {
    if (k === "stats") { raw.push("sales_count", "today_todos"); }
    else raw.push(k);
  }
  // Dédup en préservant l'ordre du 1er occurrence
  const seen = new Set();
  return raw.filter((k) => (seen.has(k) ? false : (seen.add(k), true)));
};
// Ancien ordre par défaut — utilisé pour migrer transparente-ment les configs sauvegardées.
const LEGACY_DEFAULT_ORDER = ["ca_hero", "stats", "activity", "events", "alerts", "commissions", "overtime", "ranking", "recent_sales"];
const isLegacyDefault = (arr) => Array.isArray(arr) && arr.length === LEGACY_DEFAULT_ORDER.length && arr.every((k, i) => k === LEGACY_DEFAULT_ORDER[i]);

/**
 * Wraps every widget block and injects: drag handle + hide button when in edit mode.
 * Uses native HTML5 DnD (works on desktop). Long-press touch fallback is deferred.
 */
function WidgetShell({ id, editing, dragging, size, onDragStart, onDragOver, onDrop, onHide, onResize, children }) {
  return (
    <div
      draggable={editing}
      onDragStart={(e) => onDragStart(id, e)}
      onDragOver={(e) => { if (editing) { e.preventDefault(); onDragOver(id); } }}
      onDrop={(e) => { if (editing) { e.preventDefault(); onDrop(id); } }}
      className={`relative ${editing ? "ring-2 ring-dashed ring-indigo-300/60 rounded-xl transition" : ""} ${dragging === id ? "opacity-40" : ""}`}
      data-testid={`widget-${id}`}
    >
      {editing && (
        <>
          <div className="absolute -top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 text-white text-[10px] font-semibold px-2 py-0.5 shadow pointer-events-auto cursor-grab active:cursor-grabbing" title="Glisser pour déplacer">
              <GripVertical size={10} /> Déplacer
            </span>
            <button
              type="button"
              onClick={() => onHide(id)}
              className="pointer-events-auto inline-flex items-center gap-1 rounded-full bg-white border border-slate-300 text-slate-700 text-[10px] font-semibold px-2 py-0.5 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition"
              title="Masquer ce bloc"
              data-testid={`widget-hide-${id}`}
            >
              <EyeOff size={10} /> Masquer
            </button>
          </div>
          {/* iter182 — Contrôles de redimensionnement (⅓ ½ ⅔ plein) */}
          <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 z-10 pointer-events-auto">
            <div className="inline-flex items-center gap-0.5 rounded-full bg-white border border-slate-300 shadow px-1 py-0.5" title="Redimensionner ce bloc">
              <Maximize2 size={10} className="text-slate-400 ml-1" />
              {ALLOWED_SIZES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onResize(id, s)}
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full transition ${size === s ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
                  data-testid={`widget-size-${id}-${s}`}
                  title={`Taille ${SIZE_LABEL[s]}`}
                >
                  {SIZE_LABEL[s]}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      {children}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState([]);
  const [period, setPeriod] = useState("month");
  const [openNew, setOpenNew] = useState(false);
  const [editingSale, setEditingSale] = useState(null);
  // iter47 : Activité chantiers navigable — jour + semaine indépendants
  const [activityData, setActivityData] = useState(null);
  const [dayIso, setDayIso] = useState(() => toIsoLocal(new Date()));
  const [weekIso, setWeekIso] = useState(() => toIsoLocal(startOfWeek(new Date())));
  const [activityDetail, setActivityDetail] = useState(null); // {label, projects}
  // iter53 : société en secondaire pour commerciaux
  const [companyCmp, setCompanyCmp] = useState(null);
  const nav = useNavigate();
  const { settings } = useSettings();
  const { can, user, loading: authLoading } = useAuth();
  const canCreateSale = can("sales", "create");
  const isCommercial = user?.role === "commercial";

  // --- Per-user dashboard layout (order + hidden + sizes) ---
  const [order, setOrder] = useState(DEFAULT_ORDER);
  const [hidden, setHidden] = useState([]);
  const [sizes, setSizes] = useState({}); // iter182 : { widget_key: 4|6|8|12 }
  const [editing, setEditing] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [dragging, setDragging] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const loadConfig = useCallback(async () => {
    try {
      const r = await api.get("/me/dashboard-config");
      const cfg = r.data || {};
      let ord = Array.isArray(cfg.order) && cfg.order.length ? cfg.order : DEFAULT_ORDER;
      // iter47 : migrer transparente-ment l'ancien default vers le nouveau (activity avant stats)
      if (isLegacyDefault(ord)) {
        ord = DEFAULT_ORDER;
        try { await api.put("/me/dashboard-config", { order: ord, hidden: cfg.hidden || [], sizes: cfg.sizes || {} }); } catch (_) {}
      }
      // iter182 → iter200 : migration `stats` → `sales_count + today_todos` + DÉDUP stricte
      // (le bug Théo affichait « À faire aujourd'hui » plusieurs fois car l'ordre stocké
      //  contenait des doublons — on les nettoie et on re-persiste immédiatement).
      const migrated = migrateOrder(ord);
      if (migrated.join(",") !== ord.join(",")) {
        ord = migrated;
        try { await api.put("/me/dashboard-config", { order: ord, hidden: cfg.hidden || [], sizes: cfg.sizes || {} }); } catch (_) {}
      }
      setOrder(ord);
      setHidden(Array.isArray(cfg.hidden) ? Array.from(new Set(cfg.hidden)) : []);
      setSizes(typeof cfg.sizes === "object" && cfg.sizes ? cfg.sizes : {});
    } catch (_) {
      setOrder(DEFAULT_ORDER); setHidden([]); setSizes({});
    }
  }, []);
  const saveConfig = useCallback(async (nextOrder, nextHidden, nextSizes) => {
    try { await api.put("/me/dashboard-config", { order: nextOrder, hidden: nextHidden, sizes: nextSizes }); }
    catch (err) { toast.error(formatApiError(err)); }
  }, []);

  const globalWidgets = settings?.dashboard_widgets || {};
  const showByAdmin = (k) => globalWidgets[k] !== false;
  const isVisible = (k) => showByAdmin(k) && !hidden.includes(k);

  const hideWidget = (id) => {
    const next = [...hidden, id];
    setHidden(next); saveConfig(order, next, sizes);
    toast.success("Bloc masqué");
  };
  const showWidget = (id) => {
    const next = hidden.filter((x) => x !== id);
    setHidden(next); saveConfig(order, next, sizes);
  };
  // iter182 — Redimensionne un bloc (4|6|8|12 colonnes sur 12).
  const resizeWidget = (id, size) => {
    if (!ALLOWED_SIZES.includes(size)) return;
    const next = { ...sizes, [id]: size };
    setSizes(next); saveConfig(order, hidden, next);
  };
  const sizeOf = (id) => sizes[id] || DEFAULT_SIZES[id] || 12;

  const resetLayout = async () => {
    try {
      await api.delete("/me/dashboard-config");
      setOrder(DEFAULT_ORDER); setHidden([]); setSizes({});
      toast.success("Tableau de bord réinitialisé");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const onDragStart = (id) => setDragging(id);
  const onDragOver = (id) => setDragOver(id);
  const onDrop = (targetId) => {
    if (!dragging || dragging === targetId) { setDragging(null); setDragOver(null); return; }
    const nextOrder = order.filter((k) => k !== dragging);
    const idx = nextOrder.indexOf(targetId);
    nextOrder.splice(idx < 0 ? nextOrder.length : idx, 0, dragging);
    setOrder(nextOrder); saveConfig(nextOrder, hidden, sizes);
    setDragging(null); setDragOver(null);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/dashboard/executive?period=${period}`);
      setData(r.data);
    } catch (_) { /* keep previous data */ }
    finally { setLoading(false); }
  }, [period]);
  // iter53 : totaux société (secondaire) pour un commercial
  const loadCompanyCmp = useCallback(async () => {
    if (!isCommercial) { setCompanyCmp(null); return; }
    try {
      const r = await api.get(`/dashboard/company-comparison?period=${period}`);
      setCompanyCmp(r.data);
    } catch (_) { setCompanyCmp(null); }
  }, [isCommercial, period]);
  useEffect(() => { if (!authLoading && user?.id) loadCompanyCmp(); }, [authLoading, user?.id, loadCompanyCmp]);
  const loadEvents = useCallback(async () => {
    try {
      const r = await api.get("/events?upcoming=true");
      setEvents((r.data || []).filter((e) => e.show_on_dashboard));
    } catch (_) { setEvents([]); }
  }, []);
  const loadActivity = useCallback(async (d, w) => {
    try {
      const r = await api.get(`/dashboard/activity?day=${d}&week=${w}`);
      setActivityData(r.data);
    } catch (_) { /* keep previous data */ }
  }, []);
  // Refetch quand jour/semaine change
  useEffect(() => {
    if (authLoading || !user?.id) return;
    loadActivity(dayIso, weekIso);
  }, [authLoading, user?.id, dayIso, weekIso, loadActivity]);
  // Ne déclenche PAS de fetch tant que l'authentification n'est pas résolue,
  // sinon le token n'est pas encore posé sur axios et l'appel /dashboard part sans header → 401 silencieux → data reste null → 0 affichés.
  useEffect(() => { if (!authLoading && user?.id) load(); }, [authLoading, user?.id, load]);
  useEffect(() => {
    if (authLoading || !user?.id) return;
    loadEvents(); loadConfig();
    // Refetch quand l'onglet revient au focus (ex: après une modif dans un autre onglet ou reprise d'une session)
    const onFocus = () => { load(); loadEvents(); loadActivity(dayIso, weekIso); loadCompanyCmp(); };
    const onVis = () => { if (document.visibilityState === "visible") onFocus(); };
    // iter58: sync live post-vente (annulation, création, modif, réactivation)
    const onSalesUpdated = () => { load(); loadActivity(dayIso, weekIso); loadCompanyCmp(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kylot:sales-updated", onSalesUpdated);
    };
  }, [authLoading, user?.id, loadConfig, load, loadEvents, loadActivity, dayIso, weekIso, loadCompanyCmp]);

  const ca = data?.ca || { total: 0, objectif: 100000, progress: 0, delta_pct: null };
  const barPct = Math.min(100, ca.progress);
  // iter66 : au-delà de 100% pour un commercial → barre violette célébration
  const isOverPerf = isCommercial && ca.progress > 100;
  const barColor = isOverPerf ? "bg-gradient-to-r from-violet-500 to-fuchsia-500" : ca.progress >= 100 ? "bg-emerald-500" : ca.progress >= 60 ? "bg-slate-900" : "bg-indigo-500";

  // Renderers keyed by widget id — each returns the widget's own <Card>
  const renderers = useMemo(() => ({
    ca_hero: () => {
      const remaining = Math.max(0, (ca.objectif || 0) - (ca.total || 0));
      return (
      <Card className="p-5 md:p-6 border-slate-200 shadow-sm" data-testid="dashboard-ca-hero">
        {/* Section 1 : Performance personnelle (ou société pour non-commercial) */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {isCommercial && <p className="overline text-indigo-600" data-testid="dashboard-personal-label">Ma performance personnelle</p>}
            <p className="overline">{isCommercial ? "Mon CA signé" : "Chiffre d'affaires signé"}</p>
            {loading && !data ? (
              <>
                {/* iter58: skeleton pendant le premier chargement pour éviter d'afficher 0 € */}
                <div className="h-10 md:h-12 w-40 mt-2 bg-slate-100 rounded-md animate-pulse" data-testid="dashboard-ca-loading" />
                <div className="h-3 w-56 mt-2 bg-slate-100 rounded animate-pulse" />
              </>
            ) : (
              <>
                <p className="font-display text-4xl md:text-5xl font-semibold tracking-tight mt-2" data-testid="dashboard-ca-value">{fmtEur(ca.total)}</p>
                <p className="text-sm text-slate-500 mt-1">
                  {isCommercial ? "Mon objectif personnel" : "Objectif"} : {ca.objectif > 0 ? (
                    <>
                      <span className="font-semibold text-slate-800" data-testid="dashboard-ca-objectif">{fmtEur(ca.objectif)}</span> · <span className="font-semibold text-slate-800" data-testid="dashboard-ca-progress">{ca.progress}% atteint</span>
                    </>
                  ) : (
                    <span className="italic text-slate-400" data-testid="dashboard-ca-objectif-undefined">Non défini {isCommercial && "(demandez à un administrateur)"}</span>
                  )}
                </p>
                {ca.objectif > 0 && remaining > 0 && (
                  <p className="text-xs text-slate-500 mt-1" data-testid="dashboard-ca-remaining">
                    Écart restant : <span className="font-semibold text-slate-800">{fmtEur(remaining)}</span> à réaliser
                  </p>
                )}
                {ca.objectif > 0 && ca.total > ca.objectif && (
                  <p className="text-xs text-emerald-700 mt-1 font-semibold" data-testid="dashboard-ca-exceeded">
                    Objectif dépassé de <span className="font-bold">{fmtEur(ca.total - ca.objectif)}</span>
                  </p>
                )}
                {isCommercial && ca.objectif > 0 && remaining === 0 && ca.progress <= 100 && (
                  <p className="text-xs text-emerald-700 mt-1 font-medium" data-testid="dashboard-ca-reached">🎯 Objectif atteint — bravo !</p>
                )}
                {isCommercial && ca.objectif > 0 && ca.progress > 100 && (
                  <p className="text-xs mt-1 font-semibold bg-gradient-to-r from-violet-600 to-fuchsia-600 bg-clip-text text-transparent" data-testid="dashboard-ca-overperf">
                    ✨ Objectif dépassé de {(ca.progress - 100).toFixed(1)}% — top perf !
                  </p>
                )}
              </>
            )}
          </div>
          <div className="h-10 w-10 rounded-lg bg-emerald-50 text-emerald-700 grid place-items-center shrink-0"><Euro size={18} /></div>
        </div>
        <div className="mt-4"><div className="h-2 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full ${barColor} transition-all`} style={{ width: `${barPct}%` }} /></div></div>

        {/* Section 2 : Périmètre société — visible uniquement pour un commercial, séparateur explicite */}
        {isCommercial && companyCmp && (companyCmp.can_view_ca || companyCmp.can_view_objectif || companyCmp.can_view_progress) && (
          <>
            <div className="relative my-5" data-testid="dashboard-ca-divider" aria-hidden="true">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t-2 border-dashed border-slate-200" />
              </div>
              <div className="relative flex justify-start">
                <span className="bg-white pr-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">Périmètre société</span>
              </div>
            </div>
            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-xs text-slate-500" data-testid="dashboard-ca-company">
              {companyCmp.can_view_ca && companyCmp.ca_total !== null && (
                <span className="inline-flex items-baseline gap-1.5">
                  <span className="text-slate-400">CA société :</span>
                  <span className="font-semibold text-slate-700 tabular-nums">{fmtEur(companyCmp.ca_total)}</span>
                </span>
              )}
              {companyCmp.can_view_objectif && companyCmp.objectif > 0 && (
                <span className="inline-flex items-baseline gap-1.5">
                  <span className="text-slate-400">Objectif société :</span>
                  <span className="font-semibold text-slate-700 tabular-nums">{fmtEur(companyCmp.objectif)}</span>
                </span>
              )}
              {companyCmp.can_view_progress && companyCmp.progress !== null && companyCmp.progress !== undefined && (
                <span className="inline-flex items-baseline gap-1.5">
                  <span className="text-slate-400">% société :</span>
                  <span className="font-semibold text-slate-700 tabular-nums">{companyCmp.progress.toFixed(0)}%</span>
                </span>
              )}
              <span className="inline-flex items-baseline gap-1.5">
                <span className="text-slate-400">Ventes société :</span>
                <span className="font-semibold text-slate-700 tabular-nums">{companyCmp.count}</span>
              </span>
            </div>
          </>
        )}
      </Card>
      );
    },
    stats: () => (
      // Legacy — conservé au cas où une config non migrée l'utilise encore. À terme retirable.
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 md:gap-4">
        <Stat testId="stat-sales" label="Ventes" value={data?.sales?.count ?? 0} icon={TrendingUp} delta={data?.sales?.delta_pct} accent="bg-indigo-50 text-indigo-700" onClick={() => nav("/ventes")} />
        <TodayTodos />
      </div>
    ),
    // iter182 — Widgets éclatés
    sales_count: () => (
      <Stat testId="stat-sales" label="Ventes" value={data?.sales?.count ?? 0} icon={TrendingUp} delta={data?.sales?.delta_pct} accent="bg-indigo-50 text-indigo-700" onClick={() => nav("/ventes")} />
    ),
    today_todos: () => (<TodayTodos />),
    activity: () => {
      const todayIso = activityData?.today || toIsoLocal(new Date());
      const dayD = activityData?.day || { count: 0, ca: 0, hours: 0, date: dayIso, projects: [] };
      const weekD = activityData?.week || { count: 0, ca: 0, hours: 0, start: weekIso, end: toIsoLocal(addDays(parseIsoLocal(weekIso), 6)), projects: [] };
      const isDayToday = dayIso === todayIso;
      const isWeekCurrent = weekIso === toIsoLocal(startOfWeek(new Date()));
      const shiftDay = (n) => setDayIso(toIsoLocal(addDays(parseIsoLocal(dayIso), n)));
      const shiftWeek = (n) => setWeekIso(toIsoLocal(addDays(parseIsoLocal(weekIso), 7 * n)));
      const openDetail = (kind) => {
        if (editing) return;
        if (kind === "day") setActivityDetail({ label: `Chantiers · ${fmtDayLabel(dayD.date, todayIso)}`, projects: dayD.projects || [], sub: `${dayD.count} chantier${dayD.count > 1 ? "s" : ""} · ${fmtEur(dayD.ca)}` });
        else setActivityDetail({ label: `Chantiers · Semaine du ${fmtShortDate(weekD.start)} au ${fmtShortDate(weekD.end)}`, projects: weekD.projects || [], sub: `${weekD.count} chantier${weekD.count > 1 ? "s" : ""} · ${fmtEur(weekD.ca)}` });
      };
      return (
        <Card className="p-5 md:p-6 border-slate-200 shadow-sm" data-testid="dashboard-activity">
          <div className="flex items-center gap-2 mb-4"><HardHat size={16} className="text-slate-500" /><p className="font-display text-base font-semibold">Activité chantiers</p></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* --- Jour --- */}
            <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4" data-testid="activity-day">
              <div className="flex items-center justify-between mb-2 gap-2">
                <div className="inline-flex items-center gap-1">
                  <button type="button" onClick={() => shiftDay(-1)} className="h-7 w-7 grid place-items-center rounded-md text-slate-600 hover:bg-slate-200/70 transition" title="Jour précédent" data-testid="activity-day-prev"><ChevronLeft size={14} /></button>
                  <p className="overline text-slate-700 min-w-[110px] text-center" data-testid="activity-day-label">{fmtDayLabel(dayD.date, todayIso)}</p>
                  <button type="button" onClick={() => shiftDay(1)} className="h-7 w-7 grid place-items-center rounded-md text-slate-600 hover:bg-slate-200/70 transition" title="Jour suivant" data-testid="activity-day-next"><ChevronRight size={14} /></button>
                </div>
                <div className="inline-flex items-center gap-1">
                  {!isDayToday && (
                    <button type="button" onClick={() => setDayIso(todayIso)} className="text-[10px] px-2 py-0.5 rounded-full bg-white border border-slate-300 hover:border-slate-500 text-slate-600" data-testid="activity-day-today">Aujourd'hui</button>
                  )}
                  <label className="h-7 w-7 grid place-items-center rounded-md text-slate-500 hover:bg-slate-200/70 cursor-pointer transition relative" title="Choisir une date">
                    <CalendarDays size={14} />
                    <input type="date" value={dayIso} onChange={(e) => setDayIso(e.target.value || todayIso)} className="absolute inset-0 opacity-0 cursor-pointer" data-testid="activity-day-picker" />
                  </label>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openDetail("day")}
                className="w-full text-left group"
                title="Voir le détail des chantiers"
                data-testid="activity-day-open"
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0">
                    <p className="font-display text-3xl font-semibold tracking-tight tabular-nums" data-testid="activity-day-count">{dayD.count}<span className="text-base text-slate-500 font-normal ml-1">prévu{(dayD.count || 0) > 1 ? "s" : ""}</span><span className="mx-1.5 text-slate-300">·</span><span className="text-emerald-700" data-testid="activity-day-done-count">{dayD.done_count || 0}</span><span className="text-base text-emerald-700 font-normal ml-1">fini{(dayD.done_count || 0) > 1 ? "s" : ""}</span></p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                      <span className="inline-flex items-center gap-1" data-testid="activity-day-hours"><Clock size={11} className="text-slate-400" />{dayD.hours || 0} h prévues</span>
                      <span className="inline-flex items-center gap-1 font-semibold text-slate-900 group-hover:underline underline-offset-2" data-testid="activity-day-ca"><Euro size={11} className="text-slate-400" />{fmtEur(dayD.ca)}</span>
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-700" data-testid="activity-day-done-ca" title="CA des chantiers finis">✓ {fmtEur(dayD.done_ca || 0)}</span>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1">{dayD.date}</p>
                  </div>
                  <div className="h-10 w-10 rounded-lg grid place-items-center shrink-0 bg-indigo-50 text-indigo-700"><HardHat size={18} /></div>
                </div>
              </button>
            </div>
            {/* --- Semaine --- */}
            <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4" data-testid="activity-week">
              <div className="flex items-center justify-between mb-2 gap-2">
                <div className="inline-flex items-center gap-1">
                  <button type="button" onClick={() => shiftWeek(-1)} className="h-7 w-7 grid place-items-center rounded-md text-slate-600 hover:bg-slate-200/70 transition" title="Semaine précédente" data-testid="activity-week-prev"><ChevronLeft size={14} /></button>
                  <p className="overline text-slate-700 min-w-[130px] text-center" data-testid="activity-week-label">{isWeekCurrent ? "Cette semaine" : `Sem. ${fmtShortDate(weekD.start)}`}</p>
                  <button type="button" onClick={() => shiftWeek(1)} className="h-7 w-7 grid place-items-center rounded-md text-slate-600 hover:bg-slate-200/70 transition" title="Semaine suivante" data-testid="activity-week-next"><ChevronRight size={14} /></button>
                </div>
                <div className="inline-flex items-center gap-1">
                  {!isWeekCurrent && (
                    <button type="button" onClick={() => setWeekIso(toIsoLocal(startOfWeek(new Date())))} className="text-[10px] px-2 py-0.5 rounded-full bg-white border border-slate-300 hover:border-slate-500 text-slate-600" data-testid="activity-week-today">Semaine actuelle</button>
                  )}
                  <label className="h-7 w-7 grid place-items-center rounded-md text-slate-500 hover:bg-slate-200/70 cursor-pointer transition relative" title="Choisir une semaine">
                    <CalendarDays size={14} />
                    <input
                      type="date"
                      value={weekIso}
                      onChange={(e) => {
                        const v = e.target.value; if (!v) return;
                        setWeekIso(toIsoLocal(startOfWeek(parseIsoLocal(v))));
                      }}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                      data-testid="activity-week-picker"
                    />
                  </label>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openDetail("week")}
                className="w-full text-left group"
                title="Voir le détail des chantiers"
                data-testid="activity-week-open"
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0">
                    <p className="font-display text-3xl font-semibold tracking-tight tabular-nums" data-testid="activity-week-count">{weekD.count}<span className="text-base text-slate-500 font-normal ml-1">prévu{(weekD.count || 0) > 1 ? "s" : ""}</span><span className="mx-1.5 text-slate-300">·</span><span className="text-emerald-700" data-testid="activity-week-done-count">{weekD.done_count || 0}</span><span className="text-base text-emerald-700 font-normal ml-1">fini{(weekD.done_count || 0) > 1 ? "s" : ""}</span></p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                      <span className="inline-flex items-center gap-1" data-testid="activity-week-hours"><Clock size={11} className="text-slate-400" />{weekD.hours || 0} h prévues</span>
                      <span className="inline-flex items-center gap-1 font-semibold text-slate-900 group-hover:underline underline-offset-2" data-testid="activity-week-ca"><Euro size={11} className="text-slate-400" />{fmtEur(weekD.ca)}</span>
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-700" data-testid="activity-week-done-ca" title="CA des chantiers finis">✓ {fmtEur(weekD.done_ca || 0)}</span>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1"><CalendarClock size={10} />du {weekD.start} au {weekD.end}</p>
                  </div>
                  <div className="h-10 w-10 rounded-lg grid place-items-center shrink-0 bg-emerald-50 text-emerald-700"><HardHat size={18} /></div>
                </div>
              </button>
            </div>
          </div>
        </Card>
      );
    },
    events: () => (events.length > 0 && (
      <Card className="p-5 border-slate-200 shadow-sm" data-testid="dashboard-events">
        <div className="flex items-center gap-2 mb-3"><Sparkles size={16} className="text-violet-500" /><p className="font-display text-base font-semibold">Événements à venir</p></div>
        <ul className="divide-y divide-slate-100">
          {events.slice(0, 5).map((ev) => (
            <li key={ev.id} className="py-2.5 flex items-start justify-between gap-3" data-testid={`dashboard-event-${ev.id}`}>
              <div className="min-w-0 flex-1"><p className="font-semibold text-slate-900 truncate">{ev.title}</p>{ev.description && <p className="text-xs text-slate-500 truncate mt-0.5">{ev.description}</p>}</div>
              <div className="text-right shrink-0"><p className="text-sm font-medium text-violet-800">{ev.date}</p>{ev.start_time && <p className="text-xs text-slate-500">{ev.start_time}{ev.end_time ? ` – ${ev.end_time}` : ""}</p>}</div>
            </li>
          ))}
        </ul>
        <button onClick={() => nav("/planning")} className="mt-3 text-xs text-violet-700 hover:text-violet-900 font-medium">Voir le planning →</button>
      </Card>
    )),
    alerts: () => (
      <Card className="p-5 border-slate-200 shadow-sm" data-testid="dashboard-alerts">
        <div className="flex items-center gap-2 mb-3"><Bell size={16} className="text-slate-500" /><p className="font-display text-base font-semibold">À traiter</p></div>
        {data?.alerts?.length ? (
          <ul className="space-y-2">{data.alerts.map((a) => (
            <li key={a.key}><button onClick={() => nav(a.href)} className="w-full text-left flex items-center justify-between rounded-lg border border-slate-200 hover:border-slate-900 hover:bg-slate-50 px-3 py-2 text-sm transition" data-testid={`alert-${a.key}`}><span>{a.label}</span><ArrowRight size={13} className="text-slate-400" /></button></li>
          ))}</ul>
        ) : (<p className="text-sm text-emerald-700 flex items-center gap-1.5"><CheckCircle2 size={14} /> Tout est à jour</p>)}
      </Card>
    ),
    commissions: () => (
      <Card className="p-5 border-slate-200 shadow-sm cursor-pointer hover:border-slate-400 transition" onClick={() => !editing && nav("/commissions")} data-testid="dashboard-commissions">
        <div className="flex items-start justify-between">
          <div>
            <p className="overline">Commissions du mois</p>
            <p className="font-display text-3xl font-semibold tracking-tight mt-2">{fmtEur(data?.commissions?.total)}</p>
            <p className="text-xs text-slate-500 mt-1"><span className={data?.commissions?.to_validate_count > 0 ? "text-amber-700 font-medium" : ""}>{data?.commissions?.to_validate_count || 0} à valider</span>{data?.commissions?.to_validate_count > 0 && <> · {fmtEur(data?.commissions?.to_validate_amount)}</>}</p>
          </div>
          <div className="h-10 w-10 rounded-lg bg-emerald-50 text-emerald-700 grid place-items-center"><Percent size={18} /></div>
        </div>
      </Card>
    ),
    overtime: () => (
      <Card className="p-5 border-slate-200 shadow-sm cursor-pointer hover:border-slate-400 transition" onClick={() => !editing && nav("/heures-sup")} data-testid="dashboard-overtime">
        <div className="flex items-start justify-between">
          <div>
            <p className="overline">Heures sup à valider</p>
            <p className="font-display text-3xl font-semibold tracking-tight mt-2">{data?.overtime?.pending_hours || 0}<span className="text-lg text-slate-500 font-normal ml-1">h</span></p>
            <p className="text-xs text-slate-500 mt-1">{data?.overtime?.pending_count || 0} saisie{(data?.overtime?.pending_count || 0) > 1 ? "s" : ""} en attente</p>
          </div>
          <div className="h-10 w-10 rounded-lg bg-amber-50 text-amber-700 grid place-items-center"><Clock size={18} /></div>
        </div>
      </Card>
    ),
    ranking: () => {
      const isAdmin = user?.role === "admin" || user?.role === "responsable";
      const toggleTeamFlag = async (tid, field, next) => {
        if (!tid) return;
        try {
          await api.put(`/team/${tid}`, { [field]: next });
          toast.success(next ? "Réglage activé" : "Réglage désactivé");
          load();
        } catch (err) { toast.error(formatApiError(err)); }
      };
      return (
      <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="dashboard-ranking">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2"><Trophy size={16} className="text-amber-500" /><p className="font-display text-base font-semibold">Classement commercial</p><span className="ml-auto text-xs text-slate-500">{PERIODS.find((p) => p.key === period)?.label}</span></div>
        <div className="divide-y divide-slate-100">
          {(!data?.ranking || data.ranking.length === 0) && <p className="p-5 text-sm text-slate-500">Aucune vente pour la période.</p>}
          {data?.ranking?.map((r, i) => (
            <div key={r.commercial} className={`p-3.5 flex items-center gap-3 transition ${r.hidden_from_ranking ? "opacity-60 bg-slate-50/60" : ""}`} title={r.hidden_from_ranking ? "Masqué aux autres commerciaux — visible uniquement pour vous (admin)" : undefined} data-testid={`ranking-row-${i}`}>
              <span className={`h-7 w-7 grid place-items-center rounded-full text-xs font-bold ${i === 0 ? "bg-amber-100 text-amber-800" : i === 1 ? "bg-slate-200 text-slate-700" : i === 2 ? "bg-orange-100 text-orange-800" : "bg-slate-50 text-slate-500"}`}>{i + 1}</span>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-900 truncate flex items-center gap-1.5">
                  {r.commercial}
                  {r.hidden_from_ranking && (
                    <EyeOff size={12} className="text-slate-400" aria-label="Masqué du classement public" />
                  )}
                </p>
                <div className="flex items-center gap-2 mt-0.5"><span className="text-xs text-slate-500">{r.count} vente{r.count > 1 ? "s" : ""}</span>{r.progress != null && (<span className={`text-[11px] font-medium ${r.progress >= 100 ? "text-emerald-700" : "text-slate-500"}`}>{r.progress}% obj.</span>)}</div>
                {r.objectif > 0 && (<div className="mt-1 h-1 bg-slate-100 rounded-full overflow-hidden max-w-[240px]"><div className={`h-full ${r.progress >= 100 ? "bg-emerald-500" : "bg-slate-900"}`} style={{ width: `${Math.min(100, r.progress || 0)}%` }} /></div>)}
              </div>
              <p className="font-display text-base font-semibold whitespace-nowrap">{fmtEur(r.ca)}</p>
              {isAdmin && r.team_member_id && (
                <div className="flex flex-col gap-1 ml-1" data-testid={`ranking-admin-toggles-${i}`} onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    onClick={() => toggleTeamFlag(r.team_member_id, "hidden_from_ranking", !r.hidden_from_ranking)}
                    className={`h-7 w-7 grid place-items-center rounded-md border transition ${r.hidden_from_ranking ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100" : "border-slate-200 text-slate-400 hover:text-slate-700 hover:bg-slate-50"}`}
                    title={r.hidden_from_ranking ? "Masqué aux autres — cliquez pour rendre visible" : "Visible dans le classement — cliquez pour masquer"}
                    aria-label={r.hidden_from_ranking ? "Rendre visible" : "Masquer du classement"}
                    data-testid={`ranking-toggle-hidden-${i}`}
                  >
                    {r.hidden_from_ranking ? <EyeOff size={12} /> : <Eye size={12} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleTeamFlag(r.team_member_id, "can_view_others_ranking", !r.can_view_others_ranking)}
                    className={`h-7 w-7 grid place-items-center rounded-md border transition ${r.can_view_others_ranking === false ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100" : "border-slate-200 text-slate-400 hover:text-slate-700 hover:bg-slate-50"}`}
                    title={r.can_view_others_ranking === false ? "Ne peut PAS voir le classement des autres — cliquez pour autoriser" : "Peut voir le classement des autres — cliquez pour bloquer"}
                    aria-label={r.can_view_others_ranking === false ? "Autoriser voir les autres" : "Bloquer voir les autres"}
                    data-testid={`ranking-toggle-can-view-${i}`}
                  >
                    {r.can_view_others_ranking === false ? <UserX size={12} /> : <UserCheck size={12} />}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>
      );
    },
    recent_sales: () => (
      <Card className="border-slate-200 shadow-sm">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between"><div className="flex items-center gap-2"><Wallet size={16} className="text-slate-500" /><p className="font-display text-base font-semibold">Ventes récentes</p></div><button onClick={() => !editing && nav("/ventes")} className="text-xs text-slate-500 hover:text-slate-900">Voir tout →</button></div>
        <div className="divide-y divide-slate-100">
          {(!data?.recent_sales || data.recent_sales.length === 0) && <p className="p-5 text-sm text-slate-500">Aucune vente pour l'instant.</p>}
          {data?.recent_sales?.map((s) => (
            <button key={s.id} onClick={() => !editing && setEditingSale(s)} className="w-full p-3.5 flex items-center justify-between hover:bg-slate-50 transition text-left" data-testid={`recent-sale-${s.id}`}><div className="min-w-0"><p className="font-semibold text-slate-900 truncate">{s.client_name || "—"}</p><p className="text-xs text-slate-500 truncate">{s.service} · {s.commercial || "—"}</p></div><div className="text-right"><p className="font-semibold text-slate-900">{fmtEur(s.amount)}</p><p className="text-[11px] text-slate-500">{s.sale_date}</p></div></button>
          ))}
        </div>
      </Card>
    ),
  }), [data, events, activityData, dayIso, weekIso, ca.total, ca.objectif, ca.progress, barColor, barPct, editing, nav, period, companyCmp, isCommercial, load, loading, user?.role]);

  const wideWidgets = new Set(["ranking", "recent_sales", "commissions", "overtime", "alerts", "sales_count", "today_todos", "events"]); // half-width on lg (legacy — non utilisé après iter182)
  // iter182 — Rendu sur une grille 12-col. Chaque widget occupe `col-span-{sizes[k]}`
  // (défaut : DEFAULT_SIZES[k]). L'utilisateur redimensionne chaque bloc via les boutons
  // ⅓ / ½ / ⅔ / plein en mode édition, ou glisse-déplace pour réorganiser.
  // iter182 : `events` ne s'affiche que s'il y a au moins un évènement — sinon il
  // laisserait un trou dans la grille 12-col.
  const visibleOrder = order.filter((k) => renderers[k] && isVisible(k) && !(k === "events" && (!events || events.length === 0)));
  const hiddenAvailable = order.filter((k) => renderers[k] && showByAdmin(k) && hidden.includes(k) && k !== "stats");
  // Mapping col-span statique (Tailwind purge les classes dynamiques — on doit les lister)
  const SPAN_CLASS = { 4: "lg:col-span-4", 6: "lg:col-span-6", 8: "lg:col-span-8", 12: "lg:col-span-12" };

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <p className="overline">Aperçu</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Tableau de bord</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg bg-slate-100 p-0.5" data-testid="dashboard-period-tabs">
            {PERIODS.map((p) => (
              <button key={p.key} onClick={() => setPeriod(p.key)} data-testid={`period-${p.key}`}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition ${period === p.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>{p.label}</button>
            ))}
          </div>
          <Button
            variant={editing ? "default" : "outline"}
            size="sm"
            onClick={() => setEditing((v) => !v)}
            data-testid="dashboard-customize-btn"
            className="h-9"
            title="Personnaliser le tableau de bord"
          >
            {editing ? (<><Check size={13} className="mr-1" /> Terminer</>) : (<><Settings2 size={13} className="mr-1" /> Personnaliser</>)}
          </Button>
          {canCreateSale && <Button onClick={() => setOpenNew(true)} data-testid="dashboard-new-sale-btn" className="h-9">+ Nouvelle vente</Button>}
        </div>
      </div>

      {editing && (
        <Card className="p-3 mb-4 border-indigo-200 bg-indigo-50/50 flex flex-wrap items-center gap-2" data-testid="dashboard-edit-toolbar">
          <span className="text-xs text-indigo-800 font-medium">Mode personnalisation actif — glissez les blocs pour les réorganiser.</span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setAddOpen((v) => !v)} data-testid="dashboard-add-block-btn" disabled={hiddenAvailable.length === 0}>
              <Plus size={13} className="mr-1" /> Ajouter un bloc {hiddenAvailable.length > 0 && `(${hiddenAvailable.length})`}
            </Button>
            <Button variant="outline" size="sm" onClick={resetLayout} data-testid="dashboard-reset-btn">
              <RotateCcw size={13} className="mr-1" /> Réinitialiser
            </Button>
          </div>
          {addOpen && (
            <div className="w-full mt-2 border-t border-indigo-200 pt-2 flex flex-wrap gap-2" data-testid="dashboard-add-list">
              {hiddenAvailable.length === 0 && <span className="text-xs text-slate-500 italic">Tous les blocs sont déjà visibles.</span>}
              {hiddenAvailable.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => { showWidget(k); setAddOpen(false); }}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs hover:border-slate-900 hover:bg-slate-50 transition"
                  data-testid={`dashboard-add-${k}`}
                >
                  <Eye size={11} className="text-slate-500" />{WIDGET_LABELS[k] || k}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {(loading && !data) && (
        <Card className="p-6 border-slate-200 shadow-sm mb-6 flex items-center gap-3" data-testid="dashboard-loading">
          <div className="h-4 w-4 rounded-full border-2 border-slate-300 border-t-slate-800 animate-spin"></div>
          <span className="text-sm text-slate-500">Chargement des données…</span>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6" data-testid="dashboard-grid">
        {visibleOrder.map((k) => (
          <div key={k} className={`col-span-1 ${SPAN_CLASS[sizeOf(k)] || SPAN_CLASS[12]}`}>
            <WidgetShell id={k} editing={editing} dragging={dragging} size={sizeOf(k)}
              onDragStart={onDragStart} onDragOver={onDragOver} onDrop={onDrop} onHide={hideWidget} onResize={resizeWidget}>
              {renderers[k]()}
            </WidgetShell>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-500 my-6">
        <ListChecks size={12} />
        <span>{data?.projects?.completed || 0} chantiers terminés · CA global visible dans Rapport mensuel</span>
      </div>

      <NewSaleSheet open={openNew} onOpenChange={setOpenNew} onCreated={load} />
      <EditSaleSheet sale={editingSale} open={!!editingSale} onOpenChange={(v) => !v && setEditingSale(null)} onSaved={load} />

      {/* Détail des chantiers d'un jour / d'une semaine — cliquer sur le montant */}
      <Dialog open={!!activityDetail} onOpenChange={(v) => !v && setActivityDetail(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="activity-detail-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-xl">{activityDetail?.label || "Chantiers"}</DialogTitle>
            {activityDetail?.sub && <p className="text-xs text-slate-500">{activityDetail.sub}</p>}
          </DialogHeader>
          <div className="overflow-y-auto -mx-6 px-6 pb-2">
            {(!activityDetail?.projects || activityDetail.projects.length === 0) && (
              <p className="text-sm text-slate-500 py-10 text-center" data-testid="activity-detail-empty">Aucun chantier prévu sur cette période.</p>
            )}
            <ul className="divide-y divide-slate-100">
              {activityDetail?.projects?.map((p) => (
                <li key={p.id} className="py-3 flex items-start justify-between gap-3" data-testid={`activity-detail-row-${p.id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-900 truncate">{p.client_name}</p>
                      <span className="text-[10px] text-slate-400 tabular-nums">{fmtShortDate(p.scheduled_date)}{p.duration_days > 1 ? ` · ${p.duration_days} j` : ""}</span>
                    </div>
                    {p.service && <p className="text-xs text-slate-600 truncate mt-0.5" title={p.service}>{p.service}</p>}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                      {p.commercial && (
                        <span className="inline-flex items-center gap-1">
                          <UserIcon size={10} className="text-indigo-500" />
                          {p.commercial}{p.commercial_2 ? ` + ${p.commercial_2}` : ""}
                        </span>
                      )}
                      {(p.techniciens || []).length > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <HardHat size={10} className="text-amber-600" />
                          {(p.techniciens || []).join(", ")}
                        </span>
                      )}
                      {p.client_phone && (
                        <a href={`tel:${p.client_phone}`} className="inline-flex items-center gap-1 hover:text-slate-900" onClick={(e) => e.stopPropagation()}>
                          <Phone size={10} />{p.client_phone}
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-display text-lg font-semibold tabular-nums">{fmtEur(p.amount)}</p>
                    {p.sale_id && (
                      <button
                        type="button"
                        onClick={() => { setActivityDetail(null); nav("/chantiers"); }}
                        className="text-[10px] text-slate-500 hover:text-slate-900 inline-flex items-center gap-0.5 mt-1"
                        data-testid={`activity-detail-goto-${p.id}`}
                      >
                        Ouvrir <ArrowRight size={10} />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
