import React, { useEffect, useMemo, useState } from "react";
import api, { downloadApiFile, formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { Download, Search, Target, Check, Pencil, Wallet, Banknote, Loader2, X, ChevronDown, Calendar as CalIcon, Trash2, ListChecks, AlertTriangle, Sparkles } from "lucide-react";
import NewSaleSheet from "@/components/NewSaleSheet";
import EditSaleSheet from "@/components/EditSaleSheet";
import StatusManagerDialog from "@/components/StatusManagerDialog";
import ImportClientPdfDialog from "@/components/ImportClientPdfDialog";
import UnmatchedCommercialsDialog from "@/components/UnmatchedCommercialsDialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { SALE_STATUSES, STATUS_MAP, SOURCE_MAP, SOURCES, PAYMENT_OPTIONS, formatRate, formatPayment, orderStatuses, resolveStatusesFromPayload, buildStatusMap } from "@/lib/saleConstants";
import { useSettings } from "@/contexts/SettingsContext";
import useTeam from "@/lib/useTeam";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const fmtEur2 = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n || 0);

/* ---------- Inline editable cell (Date / Text / Select) ---------- */
function InlineCell({ value, type = "text", options, onSave, display, disabled, placeholder = "—", testId, wrapperClass = "" }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(value ?? "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (!editing) setVal(value ?? ""); }, [value, editing]);

  const commit = async (nv) => {
    const finalVal = nv === undefined ? val : nv;
    if ((finalVal ?? "") === (value ?? "")) { setEditing(false); return; }
    setSaving(true);
    try {
      await onSave(finalVal);
      setEditing(false);
    } catch (_) {
      setVal(value ?? "");
      setEditing(false);
    } finally { setSaving(false); }
  };
  const cancel = () => { setVal(value ?? ""); setEditing(false); };

  if (disabled) {
    return <span className={wrapperClass}>{display ?? (value || <span className="text-slate-400">{placeholder}</span>)}</span>;
  }

  if (editing) {
    const stop = (e) => e.stopPropagation();
    if (type === "date") {
      return (
        <input type="date" autoFocus value={val || ""}
          onClick={stop} onMouseDown={stop}
          onChange={(e) => setVal(e.target.value)}
          onBlur={() => commit()}
          onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") cancel(); }}
          className="h-8 px-2 text-xs border border-slate-400 rounded focus:outline-none focus:ring-1 focus:ring-slate-900 w-[140px]"
          data-testid={testId ? `${testId}-input` : undefined} />
      );
    }
    if (type === "select") {
      return (
        <select autoFocus value={val || ""}
          onClick={stop} onMouseDown={stop}
          onChange={(e) => { setVal(e.target.value); commit(e.target.value); }}
          onBlur={cancel}
          onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          className="h-8 px-2 text-xs border border-slate-400 rounded bg-white focus:outline-none focus:ring-1 focus:ring-slate-900 max-w-[180px]"
          data-testid={testId ? `${testId}-select` : undefined}>
          <option value="">—</option>
          {(options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    // text
    return (
      <input type="text" autoFocus value={val ?? ""}
        onClick={stop} onMouseDown={stop}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => commit()}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") cancel(); }}
        className="h-8 px-2 text-xs border border-slate-400 rounded focus:outline-none focus:ring-1 focus:ring-slate-900 w-[120px]"
        data-testid={testId ? `${testId}-input` : undefined} />
    );
  }

  return (
    <button type="button"
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
      className={`text-left rounded px-1.5 py-0.5 hover:bg-slate-100 hover:ring-1 hover:ring-slate-300 cursor-pointer transition inline-flex items-center gap-1 ${wrapperClass}`}
      title="Cliquer pour modifier"
      data-testid={testId}
    >
      {saving ? <Loader2 size={11} className="animate-spin text-slate-400" /> : (display ?? (value ? value : <span className="text-slate-400 italic">{placeholder}</span>))}
    </button>
  );
}

/* ---------- Semi-circular objectif gauge ---------- */
function ObjectifGauge({ ca, objectif }) {
  const pct = objectif > 0 ? Math.min(100, (ca / objectif) * 100) : 0;
  const size = 260;
  const stroke = 22;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const halfC = circ / 2;
  const dash = (pct / 100) * halfC;
  const strokeColor = pct >= 100 ? "#059669" : pct >= 60 ? "#0f172a" : "#6366f1";

  return (
    <div className="relative w-full max-w-[300px] mx-auto" data-testid="objectif-gauge">
      <svg viewBox={`0 0 ${size} ${size / 2 + stroke + 8}`} className="w-full">
        <g transform={`translate(${size / 2} ${size / 2 + stroke / 2}) scale(-1 -1)`}>
          {/* Background half-circle */}
          <circle cx="0" cy="0" r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke}
                  strokeDasharray={`${halfC} ${circ}`} strokeLinecap="round" />
          {/* Progress half-arc */}
          <circle cx="0" cy="0" r={r} fill="none" stroke={strokeColor} strokeWidth={stroke}
                  strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
                  style={{ transition: "stroke-dasharray 0.6s ease" }} />
        </g>
      </svg>
      <div className="absolute inset-x-0 bottom-2 flex flex-col items-center pointer-events-none">
        <div className="font-display text-5xl font-semibold leading-none" style={{ color: strokeColor }}>{pct.toFixed(0)}%</div>
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mt-1.5">de l&apos;objectif</div>
      </div>
    </div>
  );
}

/* ---------- Row with progress bar per commercial ---------- */
function CommercialRow({ c, isAdmin, onObjectifSaved }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(String(c.objectif || 0));
  const [saving, setSaving] = useState(false);
  const pct = c.objectif > 0 ? Math.min(100, (c.ca / c.objectif) * 100) : 0;
  const pctClass = pct >= 100 ? "text-emerald-700 font-semibold" : pct >= 60 ? "text-slate-900 font-medium" : "text-slate-500";
  const barClass = pct >= 100 ? "bg-emerald-500" : pct >= 60 ? "bg-slate-900" : "bg-indigo-400";

  const startEdit = () => {
    if (!isAdmin || !c.id) return;
    setVal(String(c.objectif || 0));
    setEditing(true);
  };
  const cancel = () => setEditing(false);
  const save = async () => {
    const num = parseFloat(val);
    if (isNaN(num) || num < 0) { toast.error("Montant invalide"); return; }
    setSaving(true);
    try {
      await api.put(`/team/${c.id}`, { objectif: num });
      toast.success(`Objectif de ${c.name} mis à jour`);
      setEditing(false);
      await onObjectifSaved?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  return (
    <tr className="border-b border-slate-100 last:border-0 hover:bg-slate-50/50 transition-colors" data-testid={`commercial-row-${c.name}`}>
      <td className="px-4 py-3 font-medium whitespace-nowrap">{c.name}</td>
      <td className="px-4 py-3 text-right font-display text-base font-semibold whitespace-nowrap">{fmtEur(c.ca)}</td>
      <td className="px-3 py-3 text-right text-slate-600">{c.count}</td>
      {SOURCES.map((s) => (
        <td key={s.value} className="px-2.5 py-3 text-right text-slate-600">{c.sources[s.value] || 0}</td>
      ))}
      <td className="px-3 py-3 text-right text-slate-500 whitespace-nowrap">
        {editing ? (
          <div className="flex items-center gap-1 justify-end">
            <input
              type="number"
              autoFocus
              value={val}
              onChange={(e) => setVal(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
              className="w-24 h-7 px-2 text-xs text-right border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-slate-900"
              data-testid={`objectif-input-${c.name}`}
            />
            <button onClick={save} disabled={saving} className="h-7 w-7 grid place-items-center rounded bg-slate-900 text-white disabled:opacity-50" data-testid={`objectif-save-${c.name}`} aria-label="Enregistrer">
              {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
            </button>
            <button onClick={cancel} className="h-7 w-7 grid place-items-center rounded hover:bg-slate-100" aria-label="Annuler"><X size={11} /></button>
          </div>
        ) : (
          <button
            onClick={startEdit}
            disabled={!isAdmin || !c.id}
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${isAdmin && c.id ? "hover:bg-slate-100 cursor-pointer" : "cursor-default"}`}
            title={isAdmin && c.id ? "Cliquer pour définir un objectif" : ""}
            data-testid={`objectif-cell-${c.name}`}
          >
            {c.objectif > 0
              ? fmtEur(c.objectif)
              : (isAdmin && c.id ? <span className="text-slate-400 italic">définir</span> : <span className="text-slate-400">—</span>)}
            {isAdmin && c.id && <Pencil size={9} className="text-slate-400" />}
          </button>
        )}
      </td>
      <td className="px-4 py-3 min-w-[140px]">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full ${barClass} transition-all`} style={{ width: `${pct}%` }} />
          </div>
          <span className={`text-xs ${pctClass} min-w-[36px] text-right`}>{c.objectif > 0 ? `${pct.toFixed(0)}%` : "—"}</span>
        </div>
      </td>
      <td className="px-3 py-3 text-right text-slate-600" title="Ventes payées comptant (chèque, virement, CB, acompte)">{c.comptant}</td>
      <td className="px-3 py-3 text-right text-slate-600" title="Ventes en financement">{c.financement}</td>
    </tr>
  );
}

export default function Sales() {
  const { user, can, loading: authLoading } = useAuth();
  const { commerciaux, reload: reloadTeam } = useTeam();
  const { settings } = useSettings();
  // iter124 : fetch le payload complet des statuts (inclut CUSTOM) — la source de vérité
  // pour le dropdown "Changer le statut" et le rendu du badge sur chaque ligne.
  const [saleStatusesPayload, setSaleStatusesPayload] = useState(null);
  const statuses = React.useMemo(() => {
    if (saleStatusesPayload && Array.isArray(saleStatusesPayload) && saleStatusesPayload.length) {
      const list = resolveStatusesFromPayload(saleStatusesPayload).filter((s) => s.active);
      const order = settings?.sale_status_order;
      if (!Array.isArray(order) || !order.length) return list;
      const map = new Map(list.map((s) => [s.value, s]));
      const seen = new Set();
      const out = [];
      for (const v of order) { const it = map.get(v); if (it && !seen.has(v)) { out.push(it); seen.add(v); } }
      for (const s of list) if (!seen.has(s.value)) out.push(s);
      return out;
    }
    return orderStatuses(settings?.sale_status_order);
  }, [saleStatusesPayload, settings?.sale_status_order]);
  const statusMap = React.useMemo(() => buildStatusMap(statuses), [statuses]);
  useEffect(() => {
    let cancelled = false;
    const load = () => api.get("/sale-statuses").then((r) => { if (!cancelled) setSaleStatusesPayload(r.data); }).catch(() => {});
    load();
    const onUpdate = () => load();
    window.addEventListener("kylot:settings-updated", onUpdate);
    return () => { cancelled = true; window.removeEventListener("kylot:settings-updated", onUpdate); };
  }, []);
  const [sales, setSales] = useState([]);
  const [q, setQ] = useState("");
  // iter141 : tokens de recherche multi-tags (OR entre les tags).
  const [queries, setQueries] = useState([]); // ex: ["Lyon", "69003", "Dupont"]
  const [openNew, setOpenNew] = useState(false);
  const [editingSale, setEditingSale] = useState(null);
  const [objectif, setObjectif] = useState(0);
  const [objectifYear, setObjectifYear] = useState(null); // iter132 : override annuel (null => ×12)
  const [editingObjectif, setEditingObjectif] = useState(false);
  const [objectifInput, setObjectifInput] = useState("");
  const [period, setPeriod] = useState("month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  // Compute period bounds [from, to] inclusive as YYYY-MM-DD strings
  const bounds = useMemo(() => {
    const today = new Date();
    // iter104 : formatage local (pas UTC) sinon les ventes du dernier jour du mois
    // étaient exclues en zone UTC+2 (toISOString() retournait la veille).
    const iso = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}-${m}-${day}`;
    };
    if (period === "today") return { from: iso(today), to: iso(today), label: "Aujourd'hui" };
    if (period === "week") {
      const d = new Date(today);
      const wd = (d.getDay() + 6) % 7; // Monday-first
      d.setDate(d.getDate() - wd);
      const end = new Date(d); end.setDate(d.getDate() + 6);
      return { from: iso(d), to: iso(end), label: "Cette semaine" };
    }
    if (period === "prev") {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const last = new Date(today.getFullYear(), today.getMonth(), 0);
      return { from: iso(first), to: iso(last), label: "Mois précédent" };
    }
    if (period === "year") {
      return { from: `${today.getFullYear()}-01-01`, to: `${today.getFullYear()}-12-31`, label: `Année ${today.getFullYear()}` };
    }
    if (period === "custom") {
      return { from: customFrom || "1970-01-01", to: customTo || "2999-12-31", label: "Personnalisé" };
    }
    // default: this month
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return { from: iso(first), to: iso(last), label: "Ce mois" };
  }, [period, customFrom, customTo]);

  const salesInPeriod = useMemo(() => sales.filter((s) => {
    if (!s.sale_date) return false;
    return s.sale_date >= bounds.from && s.sale_date <= bounds.to;
  }), [sales, bounds]);

  const load = async () => {
    try { setSales((await api.get("/sales")).data); }
    catch (_) { /* keep previous */ }
  };
  // Optimistic PATCH helper for inline edits. Rolls back on error.
  const patchSale = async (id, patch) => {
    const prev = sales;
    setSales((cur) => cur.map((x) => (x.id === id ? { ...x, ...patch } : x)));
    try {
      const { data } = await api.put(`/sales/${id}`, patch);
      // Merge server response so downstream fields (e.g. client_name renames) stay in sync
      setSales((cur) => cur.map((x) => (x.id === id ? { ...x, ...(data || patch) } : x)));
      toast.success("Modifié");
      // iter101 : broadcast à CHAQUE patch (montant, date, commercial, taux, statut…) — plus
      // seulement au changement de statut. Toutes les pages restent cohérentes en temps réel.
      window.dispatchEvent(new CustomEvent("kylot:sales-updated", { detail: { id, patch } }));
    } catch (err) {
      setSales(prev);
      toast.error(formatApiError(err));
      throw err;
    }
  };
  const changeStatus = async (id, status) => {
    // Optimistic UI
    setSales((prev) => prev.map((x) => (x.id === id ? { ...x, status } : x)));
    try {
      await api.put(`/sales/${id}`, { status });
      toast.success(`Statut mis à jour → ${statusMap[status]?.label || STATUS_MAP[status]?.label || status}`);
      // iter52: broadcast pour que Kanban / Planning / Stock rafraîchissent sans reconnexion
      window.dispatchEvent(new CustomEvent("kylot:sales-updated", { detail: { id, status } }));
    } catch (err) {
      toast.error(formatApiError(err));
      load();
    }
  };
  const loadObjectif = async () => {
    const r = await api.get("/settings");
    setObjectif(r.data.objectif_ca || 0);
    setObjectifYear(r.data.objectif_ca_year ?? null);
  };
  useEffect(() => {
    if (authLoading || !user?.id) return;
    load(); loadObjectif(); loadUnmatched();
    // iter162 : trigger idempotent server-side pour émettre les notifs "Jour J" (14 jours écoulés)
    try { api.post("/sales/check-attente-14j").catch(() => {}); } catch (_) {}
    const onFocus = () => { load(); loadUnmatched(); };
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    // iter101 : refresh live quand une vente est modifiée/supprimée/créée depuis n'importe où
    //   (Kanban, Dashboard, autre onglet) → tous les blocs (CA, objectif, %, reste, graphique,
    //   liste, rapport) se recalculent en même temps depuis la même source /sales.
    const onSalesUpdated = () => { load(); loadUnmatched(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kylot:sales-updated", onSalesUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user?.id]);

  const loadUnmatched = async () => {
    if (!can("sales", "view", "all")) { setUnmatchedCount(0); return; }
    try { setUnmatchedCount(((await api.get("/sales/unmatched-commercials")).data || []).length); }
    catch (_) { setUnmatchedCount(0); }
  };

  const saveObjectif = async () => {
    try {
      const v = parseFloat(objectifInput);
      if (isNaN(v) || v < 0) return toast.error("Montant invalide");
      // iter132 : sur la période "Année", on écrit dans objectif_ca_year (override).
      // Sinon on écrit dans objectif_ca (mensuel — comportement d'origine).
      if (period === "year") {
        await api.put("/settings", { objectif_ca_year: v });
        setObjectifYear(v);
      } else {
        await api.put("/settings", { objectif_ca: v });
        setObjectif(v);
      }
      setEditingObjectif(false);
      toast.success("Objectif mis à jour");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const filtered = useMemo(() => {
    // iter141 : recherche multi-tags. Chaque tag est OR ; le texte en cours de frappe (`q`)
    // agit comme tag additionnel. Recherche accent-insensible sur nom, tél, adresse, CP,
    // ville, BDC, produit, commercial et statut.
    const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    const tokens = [...queries, q].map((t) => norm(t).trim()).filter(Boolean);
    const srcKey = (t) => {
      const tt = t.replace(/[\s-]+/g, "");
      if (tt === "st" || (tt.length >= 4 && "soustraitance".startsWith(tt)) || tt.startsWith("soustrait")) return "sous-traitance";
      const hit = SOURCES.find((so) => norm(so.value).replace(/[\s-]+/g, "") === tt);
      return hit ? norm(hit.value) : null;
    };
    const arr = salesInPeriod.filter((s) => {
      if (tokens.length === 0) return true;
      const hay = norm(`${s.client_name} ${s.client_phone || ""} ${s.client_address || ""} ${s.client_postal_code || ""} ${s.client_city || ""} ${s.service} ${s.status} ${s.bdc || ""} ${s.commercial || ""} ${s.commercial_2 || ""}`);
      return tokens.some((t) => {
        const sk = srcKey(t);
        return sk ? norm(s.source) === sk : hay.includes(t);
      });
    });
    // Group order requested by user (top → bottom). Values must match SALE_STATUSES keys.
    // Any status not listed lands just before "annule" (kept at the very bottom).
    // (STATUS_ORDER historique conservé dans le fallback ci-dessous — iter160)
    const _UNUSED_ORDER = [
      "attente_prog",       // 1. En attente prog
      "attente_fi",         // 2. En attente FI
      "en_cours",           // 3. En cours
      "chantier_fini",      // 4. Chantier fini
      "commercial_cheque",  // 5. Commercial à chèque
      "argent_recupere",    // 6. Chèque récupéré
      "litige",             // 7. Litige
      "annule",             // 8. Annulée (always last)
    ];
    void _UNUSED_ORDER;
    // iter160 : l'ordre des ventes suit désormais l'ordre CONFIGURÉ par l'utilisateur
    // dans "Gérer les statuts de vente" (drag&drop du dialog). Fallback sur l'ordre
    // historique en dur si les statuts ne sont pas encore chargés.
    const STATUS_ORDER_FALLBACK = [
      "attente_prog", "attente_fi", "en_cours", "chantier_fini",
      "commercial_cheque", "argent_recupere", "litige", "annule",
    ];
    const configuredOrder = (statuses || []).map((s) => s.value);
    const STATUS_ORDER = configuredOrder.length ? configuredOrder : STATUS_ORDER_FALLBACK;
    const rank = (st) => {
      const i = STATUS_ORDER.indexOf(st);
      if (i >= 0) return i;
      return STATUS_ORDER.length; // inconnus tout en bas
    };
    // iter160 : critère secondaire = date de la vente (sale_date desc), au lieu de created_at.
    const dateKey = (s) => s.sale_date || (s.created_at || "").slice(0, 10) || "";
    return arr.slice().sort((a, b) => {
      const ra = rank(a.status);
      const rb = rank(b.status);
      if (ra !== rb) return ra - rb;
      return dateKey(b).localeCompare(dateKey(a));
    });
  }, [salesInPeriod, q, queries, statuses]);

  const stats = useMemo(() => {
    const active = salesInPeriod.filter((s) => s.status !== "annule" && s.status !== "litige");
    const total = active.reduce((a, s) => a + (parseFloat(s.amount) || 0), 0);
    const ownScope = user?.permissions?.sales?.view === "own";
    // iter199 — match accent-insensible + fallback prénom (aligné avec le Classement du dashboard)
    const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    const firstOf = (s) => norm(s).split(/\s+/)[0] || "";
    // Dédup par user_id (quand un team_member est lié à un compte) : évite les doublons Théo/Théo Dudal
    const seenUid = new Set();
    const commercialsUnique = commerciaux.filter((c) => {
      if (!c.user_id) return true;
      if (seenUid.has(c.user_id)) return false;
      seenUid.add(c.user_id);
      return true;
    });
    const commercialsToShow = ownScope
      ? commercialsUnique.filter((c) => norm(c.name) === norm(user?.name || ""))
      : commercialsUnique;
    const byCommercial = commercialsToShow.map((c) => {
      const cKey = norm(c.name);
      const cFirst = firstOf(c.name);
      // iter219 : matche sur les 2 slots (commercial + commercial_2). Une vente DE
      // apparaît donc pour chacun des 2 commerciaux liés, mais son CA est divisé
      // par 2 (comme les commissions). Fix demandé : « quand une vente est à deux,
      // il faut que dans le CA du commercial, la vente soit sur quoi il est
      // commissionné » — plus jamais le montant total attribué à chaque vendeur.
      const matchesSlot = (rawName) => {
        const sKey = norm(rawName || "");
        if (!sKey) return false;
        if (sKey === cKey) return true;
        // Fallback prénom unique (« Théo » ↔ « Théo Dudal »)
        const sFirst = firstOf(rawName || "");
        const others = commercialsUnique.filter((x) => firstOf(x.name) === sFirst);
        return others.length === 1 && others[0].id === c.id && cFirst === sFirst;
      };
      const rows = active.filter((s) => {
        const de = !!s.is_de && !!(s.commercial_2 || "").trim();
        return matchesSlot(s.commercial) || (de && matchesSlot(s.commercial_2));
      });
      const ca = rows.reduce((a, s) => {
        const amt = parseFloat(s.amount) || 0;
        const de = !!s.is_de && !!(s.commercial_2 || "").trim();
        if (de) {
          // Compte 0.5×amount par slot correspondant (1 ou 2 selon si le commercial est présent sur les 2 slots)
          const s1 = matchesSlot(s.commercial) ? 1 : 0;
          const s2 = matchesSlot(s.commercial_2) ? 1 : 0;
          return a + amt * 0.5 * (s1 + s2);
        }
        return a + (matchesSlot(s.commercial) ? amt : 0);
      }, 0);
      const sources = SOURCES.reduce((acc, src) => { acc[src.value] = rows.filter((r) => r.source === src.value).length; return acc; }, {});
      const financement = rows.filter((r) => r.payment_method === "financement").length;
      const comptant = rows.filter((r) => r.payment_method && r.payment_method !== "financement").length;
      return { id: c.id, name: c.name, count: rows.length, ca, objectif: c.objectif || 0, sources, comptant, financement };
    }).sort((a, b) => b.ca - a.ca);
    return { total, byCommercial };
  }, [salesInPeriod, commerciaux, user]);

  const exportCsv = async () => {
    await downloadApiFile("/export/sales.csv", "ventes.csv");
  };

  const canEditObjectif = user?.role === "admin";
  const canDeleteSale = can("sales", "delete");
  const canEditSaleAny = can("sales", "edit");
  const canInlineEdit = (s) => canEditSaleAny;
  const isCommercial = user?.role === "commercial";
  // iter53 : comparaison société (secondaire) pour un commercial
  const [companyCmp, setCompanyCmp] = useState(null);
  // iter84/101 : objectif personnel du commercial connecté (via /dashboard/executive → ca.objectif).
  // iter101 : appel synchronisé avec la période courante, sinon objectif restait sur "month" pendant
  // que stats.total variait → % de réalisation faussé quand on passait à "year"/"prev"/"next".
  const [personalObjectif, setPersonalObjectif] = useState(null);
  useEffect(() => {
    if (!isCommercial) { setCompanyCmp(null); setPersonalObjectif(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const p = ["prev", "next", "year", "month"].includes(period) ? period : "month";
        const [r1, r2] = await Promise.all([
          api.get(`/dashboard/company-comparison?period=${p}`),
          api.get(`/dashboard/executive?period=${p}`),
        ]);
        if (!cancelled) {
          setCompanyCmp(r1.data);
          setPersonalObjectif(Number(r2.data?.ca?.objectif ?? 0) || 0);
        }
      } catch (_) { if (!cancelled) { setCompanyCmp(null); setPersonalObjectif(0); } }
    })();
    return () => { cancelled = true; };
  }, [isCommercial, period]);
  const commercialOptions = useMemo(() => (commerciaux || []).map((c) => ({ value: c.name, label: c.name })), [commerciaux]);
  const [confirmDelete, setConfirmDelete] = useState(null); // sale to delete
  const [deleting, setDeleting] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [statusManagerOpen, setStatusManagerOpen] = useState(false);
  const [unmatchedOpen, setUnmatchedOpen] = useState(false);
  const [pdfImportOpen, setPdfImportOpen] = useState(false);
  const [unmatchedCount, setUnmatchedCount] = useState(0);

  // Pick up an AI-prepared sale draft (from AI Helper "Voir et valider la vente")
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("kylot_prefill_sale");
      if (raw) {
        setPrefill(JSON.parse(raw));
        setOpenNew(true);
        sessionStorage.removeItem("kylot_prefill_sale");
      }
    } catch (_) {}
    const onEvent = (e) => {
      try { setPrefill(e.detail || null); setOpenNew(true); } catch (_) {}
    };
    window.addEventListener("kylot:open-new-sale", onEvent);
    return () => window.removeEventListener("kylot:open-new-sale", onEvent);
  }, []);

  const deleteSale = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/sales/${confirmDelete.id}`);
      setSales((prev) => prev.filter((x) => x.id !== confirmDelete.id));
      toast.success("Vente supprimée");
      setConfirmDelete(null);
      // iter99 : notifier toutes les pages (Dashboard, Commissions, Rapport, Progression) pour refresh sans reload
      window.dispatchEvent(new CustomEvent("kylot:sales-updated", { detail: { id: confirmDelete.id, deleted: true } }));
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setDeleting(false);
    }
  };
  // iter84 : objectif effectif utilisé pour les cartes du haut ("Mon objectif" / % atteint / écart).
  // Commercial → objectif personnel (team_members.objectif via /dashboard/executive). Autres → objectif société global.
  // iter131/132/136 : proratisation selon la période active.
  //   - year   → objectif annuel (override manuel ou monthly × 12)
  //   - month  → objectif mensuel (référence)
  //   - week   → objectif mensuel / 4.345 (semaines moyennes par mois)
  //   - day (today) → objectif mensuel / nb de jours du mois courant
  //   - lastMonth / custom → objectif mensuel (référence par défaut)
  const _rawObjectif = isCommercial ? (personalObjectif ?? 0) : objectif;
  const effectiveObjectif = (() => {
    if (period === "year") {
      return (!isCommercial && objectifYear != null && objectifYear > 0) ? objectifYear : _rawObjectif * 12;
    }
    if (period === "week") {
      return _rawObjectif / 4.345;
    }
    if (period === "today") {
      const now = new Date();
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      return _rawObjectif / daysInMonth;
    }
    return _rawObjectif;
  })();
  const remaining = Math.max(0, effectiveObjectif - stats.total);
  const objectifPct = effectiveObjectif > 0 ? (stats.total / effectiveObjectif) * 100 : 0;
  const objectifReached = stats.total >= effectiveObjectif && effectiveObjectif > 0;

  return (
    <div className="p-4 md:p-8 max-w-[1700px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div>
          <p className="overline">Ventes à domicile</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Ventes</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {can("sales", "view", "all") && unmatchedCount > 0 && (
            <Button variant="outline" size="sm" onClick={() => setUnmatchedOpen(true)} data-testid="sales-unmatched-btn" className="border-amber-300 text-amber-800 bg-amber-50 hover:bg-amber-100">
              <AlertTriangle size={14} className="mr-1.5" /> {unmatchedCount} vente{unmatchedCount > 1 ? "s" : ""} à attribuer
            </Button>
          )}
          {can("sales", "view", "all") && can("settings", "modify") && (
            <Button variant="outline" size="sm" onClick={() => setStatusManagerOpen(true)} data-testid="sales-manage-statuses-btn" title="Gérer les statuts">
              <ListChecks size={14} className="mr-1.5" /> Gérer les statuts
            </Button>
          )}
          {user?.role === "admin" && (
            <Button variant="outline" onClick={exportCsv} data-testid="export-sales-btn">
              <Download size={16} className="mr-2" /> Exporter CSV
            </Button>
          )}
          {can("sales", "create") && (
            <Button variant="outline" onClick={() => setPdfImportOpen(true)} data-testid="sales-pdf-import-btn" className="border-violet-200 text-violet-700 hover:bg-violet-50">
              <Sparkles size={14} className="mr-1.5" /> Importer un devis PDF
            </Button>
          )}
          {can("sales", "create") && (
            <Button onClick={() => setOpenNew(true)} data-testid="new-sale-btn">+ Nouvelle vente</Button>
          )}
        </div>
      </div>

      {/* iter63 : sélecteur de période remonté en TOP (juste sous le titre)
          → pilote CA / Objectif / % atteint + tableau des ventes */}
      <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="sales-period-filter">
        <CalIcon size={14} className="text-slate-500" />
        {[
          { k: "today", l: "Aujourd'hui" },
          { k: "week", l: "Cette semaine" },
          { k: "month", l: "Ce mois" },
          { k: "prev", l: "Mois préc." },
          { k: "year", l: "Année" },
          { k: "custom", l: "Personnalisé" },
        ].map((p) => (
          <button
            key={p.k}
            onClick={() => setPeriod(p.k)}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${period === p.k ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"}`}
            data-testid={`sales-period-${p.k}`}
          >
            {p.l}
          </button>
        ))}
        {period === "custom" && (
          <div className="flex items-center gap-1 ml-1">
            <Input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} className="h-8 w-36" data-testid="sales-period-from" />
            <span className="text-xs text-slate-400">au</span>
            <Input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} className="h-8 w-36" data-testid="sales-period-to" />
          </div>
        )}
        <span className="text-xs text-slate-500 ml-1" data-testid="sales-period-count">{bounds.label} — {salesInPeriod.length} vente{salesInPeriod.length > 1 ? "s" : ""}</span>
      </div>

      {/* Synthèse en haut : CA total / Objectif / % atteint (suit le filtre période) */}
      <Card
        className="border-slate-200 shadow-sm overflow-hidden mb-4"
        data-testid="sales-top-summary"
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-200">
          <div className="p-4 sm:p-5">
            <p className="overline flex items-center gap-1.5">
              <Wallet size={12} className="text-slate-500" /> {isCommercial ? "Mon CA signé" : "CA total"}
            </p>
            <p className="font-display text-2xl md:text-3xl font-semibold mt-1.5 tabular-nums" data-testid="sales-top-summary-ca">
              {fmtEur2(stats.total)}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">{bounds.label} · hors annulé & litige</p>
          </div>
          <div className="p-4 sm:p-5">
            <p className="overline flex items-center gap-1.5">
              <Target size={12} className="text-slate-500" /> {isCommercial ? "Mon objectif" : "Objectif"}
            </p>
            <p className="font-display text-2xl md:text-3xl font-semibold mt-1.5 tabular-nums text-slate-700" data-testid="sales-top-summary-objectif">
              {effectiveObjectif > 0 ? fmtEur2(effectiveObjectif) : <span className="text-slate-400 italic text-lg">Non défini</span>}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              {objectifReached
                ? `Dépassé de ${fmtEur2(stats.total - effectiveObjectif)}`
                : effectiveObjectif > 0
                ? `Reste ${fmtEur2(remaining)}`
                : "Définir ci-dessous"}
            </p>
          </div>
          <div className="p-4 sm:p-5">
            <p className="overline">% atteint</p>
            <p
              className={`font-display text-2xl md:text-3xl font-semibold mt-1.5 tabular-nums ${objectifReached ? "text-emerald-700" : "text-slate-900"}`}
              data-testid="sales-top-summary-pct"
            >
              {effectiveObjectif > 0 ? `${objectifPct.toFixed(0)}%` : "—"}
            </p>
            {effectiveObjectif > 0 && (
              <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden" aria-hidden="true">
                <div
                  className={`h-full transition-all ${objectifReached ? "bg-emerald-500" : "bg-slate-900"}`}
                  style={{ width: `${Math.min(100, objectifPct)}%` }}
                />
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* iter63 : la barre de période a été remontée tout en haut de la page (au-dessus des KPIs).
          Cet emplacement d'origine est laissé vide pour ne pas dupliquer la barre. */}

      {/* 1. Sales table */}
      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex flex-wrap items-center gap-2" data-testid="sales-search-bar">
          <Search size={16} className="text-slate-400 shrink-0" />
          {queries.map((t, i) => (
            <span key={`${t}-${i}`} className="inline-flex items-center gap-1 h-7 pl-2.5 pr-1 rounded-full bg-slate-900 text-white text-xs font-medium" data-testid={`sales-search-chip-${i}`}>
              {t}
              <button
                type="button"
                onClick={() => setQueries((prev) => prev.filter((_, k) => k !== i))}
                className="ml-0.5 h-5 w-5 grid place-items-center rounded-full hover:bg-white/20"
                aria-label="Retirer"
                data-testid={`sales-search-chip-remove-${i}`}
              >
                <X size={11} />
              </button>
            </span>
          ))}
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              // Enter ou virgule → transforme la saisie en tag
              if ((e.key === "Enter" || e.key === ",") && q.trim()) {
                e.preventDefault();
                const val = q.trim().replace(/,+$/, "");
                if (val && !queries.some((x) => x.toLowerCase() === val.toLowerCase())) {
                  setQueries((prev) => [...prev, val]);
                }
                setQ("");
              } else if (e.key === "Backspace" && !q && queries.length > 0) {
                // Backspace sur champ vide → retire le dernier tag
                setQueries((prev) => prev.slice(0, -1));
              }
            }}
            placeholder={queries.length === 0 ? "Rechercher (nom, tél, adresse, CP, ville, BDC, produit, commercial, statut, source : R1, CQ, TAP, Sous-traitance…) — Entrée ou virgule pour ajouter" : "Ajouter un autre filtre…"}
            className="border-0 shadow-none focus-visible:ring-0 h-9 px-0 flex-1 min-w-[220px]"
            data-testid="sales-search-input"
          />
          {(queries.length > 0 || q) && (
            <button
              type="button"
              onClick={() => { setQ(""); setQueries([]); }}
              className="text-xs text-slate-500 hover:text-slate-900 px-2"
              data-testid="sales-search-clear"
            >
              Effacer
            </button>
          )}
        </div>
        {(queries.length > 0 || q.trim()) && (() => {
          const act = filtered.filter((s) => s.status !== "annule" && s.status !== "litige");
          return (
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex flex-wrap items-baseline gap-x-6 gap-y-1" data-testid="sales-search-summary">
              <span className="text-sm text-slate-600">Résultat de la recherche : <b className="text-slate-900" data-testid="sales-search-count">{filtered.length} vente{filtered.length > 1 ? "s" : ""}</b></span>
              <span className="text-sm text-slate-600">CA HT : <b className="font-display text-lg text-slate-900" data-testid="sales-search-ca">{fmtEur(act.reduce((a, s) => a + (parseFloat(s.amount) || 0), 0))}</b></span>
              <span className="text-[11px] text-slate-400">hors annulés / litiges · sur la période sélectionnée</span>
            </div>
          );
        })()}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline whitespace-nowrap">Statut</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Date</th>
                <th className="px-4 py-3 overline whitespace-nowrap">BDC</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Nom / Prénom</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Téléphone</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Adresse</th>
                <th className="px-4 py-3 overline whitespace-nowrap">CP</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Ville</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Produits</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Montant HT</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Règlement</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Comm.</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Commercial</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Source</th>
                {canDeleteSale && <th className="px-2 py-3 overline whitespace-nowrap text-right w-10"></th>}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (<tr><td colSpan={canDeleteSale ? 15 : 14} className="p-8 text-center text-slate-500">Aucune vente.</td></tr>)}
              {filtered.map((s) => {
                const st = statusMap[s.status] || STATUS_MAP[s.status];
                const src = SOURCE_MAP[s.source];
                return (
                  <tr key={s.id} className={`data-row border-b border-slate-100 ${canEditSaleAny ? "cursor-pointer" : "cursor-default"} ${s.status === "annule" ? "opacity-60" : ""}`} onClick={canEditSaleAny ? () => setEditingSale(s) : undefined} data-testid={`sale-row-${s.id}`}>
                    <td className="px-4 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      {canEditSaleAny ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold hover:ring-2 hover:ring-slate-300 transition ${st?.cls || "bg-slate-200 text-slate-700"}`}
                              data-testid={`sale-status-trigger-${s.id}`}
                              title="Cliquer pour changer le statut"
                            >
                              {st?.label || s.status}
                              <ChevronDown size={11} className="opacity-70" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start" className="w-52">
                            <div className="flex items-center justify-between pr-1">
                              <DropdownMenuLabel className="text-xs text-slate-500">Changer le statut</DropdownMenuLabel>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); e.preventDefault(); setStatusManagerOpen(true); }}
                                className="h-6 w-6 grid place-items-center rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition"
                                title="Modifier les statuts (renommer, couleur, ajouter, supprimer)"
                                data-testid={`sale-status-edit-${s.id}`}
                              >
                                <Pencil size={12} />
                              </button>
                            </div>
                            <DropdownMenuSeparator />
                            {statuses.map((opt) => (
                              <DropdownMenuItem
                                key={opt.value}
                                onSelect={() => changeStatus(s.id, opt.value)}
                                disabled={opt.value === s.status}
                                className="text-xs cursor-pointer"
                                data-testid={`sale-status-option-${s.id}-${opt.value}`}
                              >
                                <span className={`inline-block h-2 w-2 rounded-full mr-2 ${opt.cls.split(" ")[0]}`} />
                                <span className="flex-1">{opt.label}</span>
                                {opt.value === s.status && <Check size={12} className="text-slate-500" />}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : (
                        <span
                          className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${st?.cls || "bg-slate-200 text-slate-700"}`}
                          data-testid={`sale-status-trigger-${s.id}`}
                        >
                          {st?.label || s.status}
                        </span>
                      )}
                      {/* iter185 : le badge « Il reste Xj / Jour J / Délai dépassé » n'apparaît
                          QUE tant que le statut est encore « En attente prog » (attente_prog).
                          Dès que le statut bascule (En attente FI, Chèque récupéré, Annulé,
                          Non finançable, Virement reçu, etc.), le décompte est retiré — la
                          vente est sortie de la fenêtre 14 j côté programmation. */}
                      {s.desired_intervention_date === "attente_14j" && s.status === "attente_prog" && (() => {
                        // iter162 : décompte des 14 jours à partir de sale_date.
                        try {
                          const start = new Date(s.sale_date + "T00:00:00");
                          const now = new Date();
                          const days = 14 - Math.floor((now - start) / 86400000);
                          if (days > 0) {
                            const urgent = days <= 3;
                            return (
                              <span className={`ml-1.5 inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${urgent ? "bg-amber-200 text-amber-900 ring-1 ring-amber-400" : "bg-amber-100 text-amber-800"}`} data-testid={`sale-14j-countdown-${s.id}`}>
                                {days === 1 ? "Il reste 1 j" : `Il reste ${days} j`}
                              </span>
                            );
                          }
                          if (days === 0) {
                            return (
                              <span className="ml-1.5 inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-500 animate-pulse ring-1 ring-red-600" data-testid={`sale-14j-jourj-${s.id}`}>Jour J</span>
                            );
                          }
                          return (
                            <span className="ml-1.5 inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-600 animate-pulse ring-1 ring-red-700" data-testid={`sale-14j-overdue-${s.id}`}>
                              Délai dépassé +{Math.abs(days)} j
                            </span>
                          );
                        } catch (_) { return null; }
                      })()}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600" onClick={(e) => e.stopPropagation()}>
                      <InlineCell
                        type="date"
                        value={s.sale_date}
                        disabled={!canInlineEdit(s)}
                        display={s.sale_date || <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(s.id, { sale_date: v })}
                        testId={`sale-date-${s.id}`}
                      />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap font-mono text-xs" onClick={(e) => e.stopPropagation()}>
                      <InlineCell
                        type="text"
                        value={s.bdc || ""}
                        disabled={!canInlineEdit(s)}
                        display={s.bdc || <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(s.id, { bdc: v })}
                        testId={`sale-bdc-${s.id}`}
                      />
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-900 whitespace-nowrap">{s.client_name || "—"}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{s.client_phone}</td>
                    <td className="px-4 py-3 text-slate-600">{s.client_address}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{s.client_postal_code}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{s.client_city}</td>
                    <td className="px-4 py-3 max-w-[220px]"><div className="truncate" title={s.service}>{s.service}</div></td>
                    <td className="px-4 py-3 font-semibold whitespace-nowrap">{fmtEur(s.amount)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600" onClick={(e) => e.stopPropagation()}>
                      <InlineCell
                        type="select"
                        value={s.payment_method || ""}
                        options={PAYMENT_OPTIONS}
                        disabled={!canInlineEdit(s)}
                        display={formatPayment(s.payment_method, s.payment_installments)}
                        onSave={(v) => patchSale(s.id, { payment_method: v })}
                        testId={`sale-payment-${s.id}`}
                      />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600">
                      {s.is_de && s.commercial_2 ? (
                        <span className="text-xs">
                          {formatRate(s.commission_rate)}
                          <span className="text-slate-400 mx-1">/</span>
                          {formatRate(s.commission_rate_2 != null ? s.commission_rate_2 : s.commission_rate)}
                        </span>
                      ) : (
                        formatRate(s.commission_rate)
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap font-medium" onClick={(e) => e.stopPropagation()}>
                      <InlineCell
                        type="select"
                        value={s.commercial || ""}
                        options={commercialOptions}
                        disabled={!canInlineEdit(s)}
                        display={s.commercial || <span className="text-slate-400 italic">À compléter</span>}
                        placeholder="À compléter"
                        onSave={(v) => patchSale(s.id, { commercial: v })}
                        testId={`sale-commercial-${s.id}`}
                      />
                      {s.is_de && (
                        <div className="mt-1 text-[10px] text-indigo-700">
                          <InlineCell
                            type="select"
                            value={s.commercial_2 || ""}
                            options={commercialOptions.filter((o) => o.value !== s.commercial)}
                            disabled={!canInlineEdit(s)}
                            display={<span>DE · {s.commercial_2 || <span className="italic text-slate-400">2e commercial</span>}</span>}
                            onSave={(v) => patchSale(s.id, { commercial_2: v })}
                            testId={`sale-commercial2-${s.id}`}
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <InlineCell
                        type="select"
                        value={s.source || ""}
                        options={SOURCES.map((so) => ({ value: so.value, label: so.label }))}
                        disabled={!canInlineEdit(s)}
                        display={src ? <Badge className={`${src.cls} border-0`}>{src.label}</Badge> : <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(s.id, { source: v })}
                        testId={`sale-source-${s.id}`}
                      />
                    </td>
                    {canDeleteSale && (
                      <td className="px-2 py-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => setConfirmDelete(s)}
                          className="h-8 w-8 grid place-items-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition"
                          title="Supprimer cette vente"
                          aria-label="Supprimer cette vente"
                          data-testid={`sale-delete-btn-${s.id}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 2. CA total & Objectif — with gauge.
          iter81 : pour un commercial, le bloc affiche la performance SOCIÉTÉ (companyCmp) ;
          les 3 KPI du haut affichent déjà sa performance PERSO. */}
      <Card className="border-slate-200 shadow-sm overflow-hidden mt-6" data-testid="objectif-summary">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2">
          <Target size={16} className="text-slate-500" />
          <p className="font-display text-lg font-semibold">CA total & objectif</p>
          {isCommercial && <span className="text-[10px] text-slate-400 uppercase tracking-wider">Périmètre société</span>}
        </div>
        {(() => {
          // iter81 : bascule sur les données société pour un commercial.
          const gaugeCa = isCommercial ? (companyCmp?.ca_total ?? 0) : stats.total;
          const gaugeObj = isCommercial ? (companyCmp?.objectif ?? 0) : objectif;
          const gaugeRem = Math.max(0, (gaugeObj || 0) - (gaugeCa || 0));
          const gaugeReached = gaugeObj > 0 && gaugeCa >= gaugeObj;
          const canSeeCompanyCa = !isCommercial || (companyCmp?.can_view_ca !== false);
          const canSeeCompanyObj = !isCommercial || (companyCmp?.can_view_objectif !== false);
          return (
            <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 p-6 items-center">
              <ObjectifGauge ca={gaugeCa} objectif={gaugeObj} />
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-5">
                  <p className="overline">CA réalisé</p>
                  <p className="font-display text-3xl font-semibold mt-2" data-testid="total-ca">
                    {canSeeCompanyCa ? fmtEur2(gaugeCa) : <span className="text-slate-400 italic text-lg">Masqué</span>}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{isCommercial ? "société · hors annulé & litige" : "hors annulé & litige"}</p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-5">
                  <div className="flex items-center justify-between">
                    <p className="overline">Objectif</p>
                    {canEditObjectif && !editingObjectif && !isCommercial && (
                      <button onClick={() => { setObjectifInput(String(objectif)); setEditingObjectif(true); }} data-testid="objectif-edit-btn" className="text-slate-400 hover:text-slate-900">
                        <Pencil size={13} />
                      </button>
                    )}
                  </div>
                  {editingObjectif && !isCommercial ? (
                    <div className="flex items-center gap-2 mt-2">
                      <Input type="number" value={objectifInput} onChange={(e) => setObjectifInput(e.target.value)} className="h-9" data-testid="objectif-input" />
                      <Button size="sm" onClick={saveObjectif} data-testid="objectif-save-btn"><Check size={14} /></Button>
                    </div>
                  ) : (
                    <p className="font-display text-3xl font-semibold mt-2" data-testid="objectif-value">
                      {canSeeCompanyObj ? fmtEur2(gaugeObj) : <span className="text-slate-400 italic text-lg">Masqué</span>}
                    </p>
                  )}
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-5">
                  <p className="overline">{gaugeReached ? "Dépassement" : "Reste à faire"}</p>
                  <p className={`font-display text-3xl font-semibold mt-2 ${gaugeReached ? "text-emerald-700" : ""}`}>
                    {gaugeReached ? `+ ${fmtEur2(gaugeCa - gaugeObj)}` : fmtEur2(gaugeRem)}
                  </p>
                  {gaugeReached && <p className="text-xs text-emerald-700 mt-1 font-medium">🎯 Objectif atteint !</p>}
                </div>
              </div>
            </div>
          );
        })()}
      </Card>

      {/* 3. CA par commercial — with progress bars (masqué pour le rôle commercial — iter80) */}
      {!isCommercial && (
      <Card className="border-slate-200 shadow-sm overflow-hidden mt-6" data-testid="commercials-summary">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2 flex-wrap">
          <p className="font-display text-lg font-semibold">CA par commercial</p>
          <span className="text-xs text-slate-500">(hors annulé & litige)</span>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1"><Wallet size={12} /> Comptant</span>
            <span className="flex items-center gap-1"><Banknote size={12} /> Financement</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline">Commercial</th>
                <th className="px-4 py-3 overline text-right">Chiffre d’affaires</th>
                <th className="px-3 py-3 overline text-right">Ventes</th>
                {SOURCES.map((s) => (
                  <th key={s.value} className="px-2.5 py-3 overline text-right">{s.label}</th>
                ))}
                <th className="px-3 py-3 overline text-right">Objectif</th>
                <th className="px-4 py-3 overline">Progression</th>
                <th className="px-3 py-3 overline text-right">Comptant</th>
                <th className="px-3 py-3 overline text-right">Fin.</th>
              </tr>
            </thead>
            <tbody>
              {stats.byCommercial.map((c) => (<CommercialRow key={c.name} c={c} isAdmin={user?.role === "admin"} onObjectifSaved={reloadTeam} />))}
            </tbody>
          </table>
        </div>
      </Card>
      )}

      <NewSaleSheet open={openNew} onOpenChange={(v) => { setOpenNew(v); if (!v) setPrefill(null); }} onCreated={() => { load(); window.dispatchEvent(new CustomEvent("kylot:sales-updated", { detail: { created: true } })); }} prefill={prefill} />
      <StatusManagerDialog open={statusManagerOpen} onOpenChange={setStatusManagerOpen} onSaved={() => { load(); window.dispatchEvent(new Event("kylot:settings-updated")); }} />
      <ImportClientPdfDialog open={pdfImportOpen} onOpenChange={setPdfImportOpen} onImported={() => { load(); }} />
      <UnmatchedCommercialsDialog open={unmatchedOpen} onOpenChange={setUnmatchedOpen} onBound={() => { load(); loadUnmatched(); }} />
      <EditSaleSheet sale={editingSale} open={!!editingSale} onOpenChange={(v) => !v && setEditingSale(null)} onSaved={() => { load(); window.dispatchEvent(new CustomEvent("kylot:sales-updated", { detail: { edited: true } })); }} />

      <AlertDialog open={!!confirmDelete} onOpenChange={(v) => !v && setConfirmDelete(null)}>
        <AlertDialogContent data-testid="sale-delete-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cette vente ?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete && (
                <>
                  Vous êtes sur le point de supprimer la vente de <span className="font-semibold text-slate-900">{confirmDelete.client_name || "—"}</span>
                  {confirmDelete.amount ? <> ({fmtEur(confirmDelete.amount)})</> : null}
                  {confirmDelete.bdc ? <> · BDC <span className="font-mono text-xs">{confirmDelete.bdc}</span></> : null}.
                  <br />
                  Cette action est <span className="font-semibold text-red-700">définitive</span> et supprimera aussi le chantier lié.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="sale-delete-cancel">Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); deleteSale(); }}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700"
              data-testid="sale-delete-confirm-btn"
            >
              {deleting ? "Suppression…" : "Supprimer"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
