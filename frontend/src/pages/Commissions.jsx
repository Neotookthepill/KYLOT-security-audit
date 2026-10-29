import React, { useEffect, useMemo, useState } from "react";
import api, { downloadApiFile, formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, TrendingUp, Euro, CheckCircle2, Plus, Minus, Pencil, X, FileDown, ListChecks, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { STATUS_MAP, COMMISSION_RATES as DEFAULT_RATES, formatRate, formatPayment, currentMonth, shiftMonth, monthLabel, PAYMENT_OPTIONS, SOURCES, orderStatuses, resolveStatusesFromPayload, buildStatusMap } from "@/lib/saleConstants";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import useTeam from "@/lib/useTeam";
import { useSettings } from "@/contexts/SettingsContext";
import { invalidateCommissionRatesCache } from "@/lib/useCommissionRates";
import InlineCell from "@/components/InlineCell";
import BonusesProgress from "@/components/BonusesProgress";
import StatusManagerDialog from "@/components/StatusManagerDialog";
import CommissionHistory from "@/components/CommissionHistory";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

// iter179 : recherche accent-insensible pour les filtres commercial (fix bug msg 267 :
// « Théo »/« theo »/« THEO » doivent matcher indifféremment).
const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

function StatCard({ label, value, icon: Icon, testId }) {
  return (
    <Card className="p-5 border-slate-200 shadow-sm" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div>
          <p className="overline">{label}</p>
          <p className="font-display text-3xl font-semibold tracking-tight mt-2">{value}</p>
        </div>
        <div className="h-10 w-10 rounded-lg bg-slate-100 text-slate-700 grid place-items-center">
          <Icon size={18} />
        </div>
      </div>
    </Card>
  );
}

export default function Commissions() {
  const { user, can, loading: authLoading } = useAuth();
  const { commerciaux } = useTeam();
  const { settings } = useSettings();
  // iter160 : mêmes statuts que dans Ventes — récupère /api/sale-statuses et
  // applique l'ordre `sale_status_order`. Fournit un `statusMap` dynamique qui
  // couvre les statuts personnalisés (attente_prog "PROG", non_financable, etc.).
  const [saleStatusesPayload, setSaleStatusesPayload] = useState(null);
  const [statusManagerOpen, setStatusManagerOpen] = useState(false);
  const statuses = useMemo(() => {
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
  const statusMap = useMemo(() => buildStatusMap(statuses), [statuses]);
  const statusOptions = useMemo(() => statuses.map((s) => ({ value: s.value, label: s.label })), [statuses]);
  useEffect(() => {
    let cancelled = false;
    const load = () => api.get("/sale-statuses").then((r) => { if (!cancelled) setSaleStatusesPayload(r.data); }).catch(() => {});
    load();
    const onUpdate = () => load();
    window.addEventListener("kylot:settings-updated", onUpdate);
    return () => { cancelled = true; window.removeEventListener("kylot:settings-updated", onUpdate); };
  }, []);
  const commercialOptions = useMemo(() => (commerciaux || []).map((c) => ({ value: c.name, label: c.name })), [commerciaux]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [commercialFilter, setCommercialFilter] = useState("__all");
  const [activeMonth, setActiveMonth] = useState(currentMonth());
  const [rates, setRates] = useState(DEFAULT_RATES);
  const [ratesOpen, setRatesOpen] = useState(false);
  const [newRateInput, setNewRateInput] = useState("");
  // iter179 : vue « mois courant » vs « historique cumulé »
  const [view, setView] = useState("month");
  const [extraMonths, setExtraMonths] = useState(() => {
    const saved = parseInt(localStorage.getItem("pylot_extra_months") || "2", 10);
    return isNaN(saved) ? 2 : Math.max(2, saved);
  });
  // iter205 : fenêtre glissante sur les mois passés (vue et sélecteur "Payé au mois de…").
  // Permet de rouvrir un mois précédent OU d'affecter une vente ancienne à un mois passé.
  const [pastMonths, setPastMonths] = useState(() => {
    const saved = parseInt(localStorage.getItem("pylot_past_months") || "6", 10);
    return isNaN(saved) ? 6 : Math.max(2, Math.min(24, saved));
  });
  // iter210 : mois masqués (mode fantôme) — persistés par user. Le mois courant
  // n'est jamais masquable. Un toggle « Afficher masqués » permet de tout révéler
  // (badge semi-transparent + bouton « restaurer »).
  const [hiddenMonths, setHiddenMonths] = useState(() => {
    try {
      const raw = localStorage.getItem("pylot_hidden_months");
      const arr = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : []);
    } catch (_) { return new Set(); }
  });
  const [showHidden, setShowHidden] = useState(false);
  const persistHidden = (setLike) => {
    try { localStorage.setItem("pylot_hidden_months", JSON.stringify(Array.from(setLike))); } catch (_) {}
  };
  const hideMonth = (key) => {
    if (key === currentMonth()) return; // jamais masquer le mois courant
    setHiddenMonths((prev) => {
      const next = new Set(prev); next.add(key); persistHidden(next);
      return next;
    });
    // Si on masque le mois actif, on retombe sur le mois courant
    if (activeMonth === key) setActiveMonth(currentMonth());
  };
  const unhideMonth = (key) => {
    setHiddenMonths((prev) => {
      const next = new Set(prev); next.delete(key); persistHidden(next);
      return next;
    });
  };
  const unhideAll = () => {
    setHiddenMonths(new Set());
    persistHidden(new Set());
  };

  const bumpMonths = (delta) => {
    setExtraMonths((prev) => {
      const next = Math.max(2, Math.min(12, prev + delta));
      localStorage.setItem("pylot_extra_months", String(next));
      return next;
    });
  };
  const bumpPastMonths = (delta) => {
    setPastMonths((prev) => {
      const next = Math.max(2, Math.min(24, prev + delta));
      localStorage.setItem("pylot_past_months", String(next));
      return next;
    });
  };

  const load = async () => {
    setLoading(true);
    try { setRows((await api.get("/commissions")).data); }
    catch (_) { /* keep previous rows */ }
    finally { setLoading(false); }
  };
  const loadRates = async () => {
    try {
      const s = (await api.get("/settings")).data;
      if (Array.isArray(s?.commission_rates) && s.commission_rates.length) setRates(s.commission_rates);
    } catch (_) {}
  };
  // Wait for auth to be resolved so axios has the Bearer token in place.
  useEffect(() => {
    if (authLoading || !user?.id) return;
    load(); loadRates();
    const onFocus = () => load();
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    // iter58 : sync live avec les modifications de vente (annulation, création, statut…)
    const onSalesUpdated = () => load();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kylot:sales-updated", onSalesUpdated);
    };
  }, [authLoading, user?.id]);

    const isAdmin = user?.role === "admin" || can("settings", "modify");
    const canEditCommissions = can("commissions", "edit");
    const saveRates = async (newList) => {
    const clean = Array.from(new Set(newList.filter((r) => !isNaN(r) && r >= 0 && r <= 1))).sort((a, b) => a - b);
    try {
      await api.put("/settings", { commission_rates: clean });
      setRates(clean);
      invalidateCommissionRatesCache();
      toast.success("Taux mis à jour");
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const addRate = () => {
    const v = parseFloat((newRateInput || "").replace(",", ".")) / (newRateInput?.includes("%") ? 100 : 1);
    if (isNaN(v) || v < 0 || v > 1) { toast.error("Valeur invalide (0 à 100 %)"); return; }
    saveRates([...rates, v]);
    setNewRateInput("");
  };
  const removeRate = (r) => saveRates(rates.filter((x) => x !== r));

  const patchSale = async (sale_id, patch, {confirm} = {}) => {
    if (confirm && !window.confirm(confirm)) return;
    try {
      await api.put(`/sales/${sale_id}`, patch);
      toast.success("Modifié");
      load();
    } catch (err) { toast.error(formatApiError(err)); throw err; }
  };

  const monthTabs = useMemo(() => {
    const now = currentMonth();
    const arr = [];
    // iter205 : mois passés d'abord (plus ancien → plus récent), puis courant, puis futurs
    for (let i = pastMonths; i >= 1; i--) {
      const k = shiftMonth(now, -i);
      const prefix = i === 1 ? "Mois préc." : `-${i} mois`;
      arr.push({ key: k, label: `${prefix} — ${monthLabel(k)}` });
    }
    arr.push({ key: now, label: `Ce mois — ${monthLabel(now)}` });
    for (let i = 1; i <= extraMonths; i++) {
      const k = shiftMonth(now, i);
      const prefix = i === 1 ? "Mois prochain" : `+${i} mois`;
      arr.push({ key: k, label: `${prefix} — ${monthLabel(k)}` });
    }
    return arr;
  }, [extraMonths, pastMonths]);

  const paymentMonthOptions = useMemo(() => {
    const now = currentMonth();
    const arr = [];
    // iter205 : mois passés d'abord pour permettre d'affecter une vente ancienne à un mois passé
    for (let i = pastMonths; i >= 1; i--) {
      const v = shiftMonth(now, -i);
      const prefix = i === 1 ? "Mois précédent" : `Il y a ${i} mois`;
      arr.push({ value: v, label: `${prefix} (${monthLabel(v)})` });
    }
    arr.push({ value: now, label: `Ce mois-ci (${monthLabel(now)})` });
    for (let i = 1; i <= extraMonths; i++) {
      const v = shiftMonth(now, i);
      const prefix = i === 1 ? "Mois prochain" : `Dans ${i} mois`;
      arr.push({ value: v, label: `${prefix} (${monthLabel(v)})` });
    }
    return arr;
  }, [extraMonths, pastMonths]);

  const filtered = useMemo(() => rows.filter((r) => {
    // iter179 : match accent-insensible sur le champ texte ET sur le filtre commercial.
    // iter180 : le dropdown liste les noms d'équipe (ex : « Theo ») tandis que les rows
    // portent le nom complet du user (ex : « Théo Fresh ») — on fait donc un match
    // par substring dans les deux sens pour éviter les zéro-résultat.
    const hay = norm(`${r.client_name} ${r.bdc} ${r.service} ${r.commercial || ""}`);
    const matchesText = !q.trim() || hay.includes(norm(q));
    const rc = norm(r.commercial);
    const cf = norm(commercialFilter);
    const matchesCommercial = commercialFilter === "__all" || !cf || rc === cf || rc.includes(cf) || cf.includes(rc);
    // iter105 : la page Commissions filtre par `commission_month` (mois de paiement de la commission,
    // paramétrable indépendamment de la date de vente pour permettre de reporter au mois suivant).
    // Les autres pages (Dashboard, Rapport, Ventes) restent sur `sale_date`.
    const rowMonth = r.commission_month || (r.sale_date || "").slice(0, 7) || currentMonth();
    const matchesMonth = rowMonth === activeMonth;
    // iter205 : « non finançable » = pas de paiement possible → exclu des commissions
    // (au même titre que annulé et litige).
    const commissionable = r.status !== "annule" && r.status !== "litige" && r.status !== "non_financable";
    return matchesText && matchesCommercial && matchesMonth && commissionable;
  }), [rows, q, commercialFilter, activeMonth]);

  const totals = useMemo(() => {
    const toPay = filtered.filter((r) => !r.commission_paid);
    const paid = filtered.filter((r) => r.commission_paid);
    return {
      total: filtered.reduce((a, r) => a + r.commission_amount, 0),
      toPay: toPay.reduce((a, r) => a + r.commission_amount, 0),
      paid: paid.reduce((a, r) => a + r.commission_amount, 0),
      count: filtered.length,
    };
  }, [filtered]);

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="mb-6 flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="overline">Rémunération commerciale</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight">Commissions</h1>
          <p className="text-sm text-slate-500 mt-2">Choisissez le mois de paiement pour chaque commission puis cochez « Payé » quand c'est fait. Les ventes <b>annulées</b>, <b>en litige</b> et <b>non finançables</b> ne sont pas affichées.</p>
          <p className="text-xs text-slate-500 mt-2">
            {isAdmin ? (<>Taux disponibles : <span className="font-medium text-slate-700">{rates.map((r) => formatRate(r)).join(" · ")}</span></>) : (<>Seul ton taux personnel apparaît sur chaque vente ci-dessous.</>)}
          </p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline" size="sm"
              onClick={async () => {
                try {
                  await downloadApiFile(`/commissions.pdf?month=${encodeURIComponent(activeMonth)}`, `commissions-${activeMonth}.pdf`);
                } catch (err) {
                  toast.error(formatApiError(err));
                }
              }}
              data-testid="commissions-pdf-btn"
            >
              <FileDown size={13} className="mr-1.5" /> Récap PDF
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRatesOpen(true)} data-testid="rates-edit-btn">
              <Pencil size={13} className="mr-1.5" /> Modifier les taux
            </Button>
            {can("settings", "modify") && (
              <Button variant="outline" size="sm" onClick={() => setStatusManagerOpen(true)} data-testid="commissions-manage-statuses-btn" title="Gérer les statuts">
                <ListChecks size={13} className="mr-1.5" /> Gérer les statuts
              </Button>
            )}
          </div>
        )}
      </div>

      {/* iter179 — Toggle vue Mois / Historique */}
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
        <button
          onClick={() => setView("month")}
          data-testid="view-month-btn"
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${view === "month" ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
        >
          Vue mensuelle
        </button>
        <button
          onClick={() => setView("history")}
          data-testid="view-history-btn"
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${view === "history" ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
        >
          Historique
        </button>
      </div>

      {view === "history" ? <CommissionHistory /> : (<>

      {/* Month tabs — iter205/210 : mois passés + courant + futurs, avec masquage individuel (mode fantôme) */}
      <div className="mb-2 flex items-center gap-2 flex-wrap">
        {isAdmin && (
          <button
            type="button"
            onClick={() => setShowHidden((v) => !v)}
            data-testid="month-tab-toggle-hidden"
            className={`text-[11px] px-2.5 py-1 rounded-full border transition ${showHidden ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"}`}
            title={showHidden ? "Cacher les mois masqués" : "Afficher les mois masqués"}
          >
            {showHidden ? "Masquer les mois cachés" : `Afficher les mois masqués${hiddenMonths.size ? ` (${hiddenMonths.size})` : ""}`}
          </button>
        )}
        {isAdmin && hiddenMonths.size > 0 && (
          <button
            type="button"
            onClick={unhideAll}
            data-testid="month-tab-unhide-all"
            className="text-[11px] px-2.5 py-1 rounded-full border border-slate-200 text-slate-500 hover:border-slate-400 hover:text-slate-800 transition"
            title="Restaurer tous les mois masqués"
          >
            Tout restaurer
          </button>
        )}
      </div>
      <div className="flex items-center gap-2 mb-6 border-b border-slate-200 overflow-x-auto">
        {isAdmin && (
          <button
            onClick={() => bumpPastMonths(1)}
            data-testid="month-tab-past-add"
            className="h-7 w-7 shrink-0 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors self-center mb-1"
            aria-label="Voir un mois précédent supplémentaire"
            title="Voir un mois précédent supplémentaire"
          >
            <Minus size={13} />
          </button>
        )}
        {monthTabs.filter((t) => showHidden || !hiddenMonths.has(t.key)).map((t) => {
          const isHidden = hiddenMonths.has(t.key);
          const isCurrent = t.key === currentMonth();
          const isActive = activeMonth === t.key;
          return (
            <div key={t.key} className="relative group inline-flex items-center">
              <button
                onClick={() => setActiveMonth(t.key)}
                data-testid={`month-tab-${t.key}`}
                className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${isActive ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"} ${isHidden ? "opacity-40 italic" : ""}`}
                title={isHidden ? "Masqué (cliquer pour consulter tout de même)" : undefined}
              >
                {t.label}{isHidden ? " · masqué" : ""}
              </button>
              {isAdmin && !isCurrent && (
                isHidden ? (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); unhideMonth(t.key); }}
                    data-testid={`month-tab-unhide-${t.key}`}
                    className="ml-0.5 h-5 w-5 grid place-items-center rounded-full text-slate-400 hover:text-emerald-700 hover:bg-emerald-50 transition"
                    aria-label="Restaurer ce mois"
                    title="Restaurer ce mois"
                  ><RotateCcw size={11} /></button>
                ) : (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); hideMonth(t.key); }}
                    data-testid={`month-tab-hide-${t.key}`}
                    className="ml-0.5 h-5 w-5 grid place-items-center rounded-full text-slate-300 hover:text-red-600 hover:bg-red-50 opacity-0 group-hover:opacity-100 focus:opacity-100 transition"
                    aria-label="Masquer ce mois"
                    title="Masquer ce mois (données conservées)"
                  ><X size={11} /></button>
                )
              )}
            </div>
          );
        })}
        {isAdmin && (
          <div className="ml-auto flex items-center gap-1 pb-1">
            {extraMonths > 2 && (
              <button
                onClick={() => bumpMonths(-1)}
                data-testid="month-tab-remove"
                className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors"
                aria-label="Retirer le dernier mois futur"
                title="Retirer le dernier mois futur"
              >
                <Minus size={13} />
              </button>
            )}
            <button
              onClick={() => bumpMonths(1)}
              data-testid="month-tab-add"
              className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors"
              aria-label="Ajouter un mois suivant"
              title="Ajouter un mois suivant"
            >
              <Plus size={13} />
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard testId="stat-commissions-total" label={`Commissions ${monthLabel(activeMonth)}`} value={fmtEur(totals.total)} icon={Euro} />
        <StatCard testId="stat-commissions-topay" label="Reste à payer" value={fmtEur(totals.toPay)} icon={TrendingUp} />
        <StatCard testId="stat-commissions-paid" label="Déjà payé" value={fmtEur(totals.paid)} icon={CheckCircle2} />
      </div>

      <div className="mb-6">
        <BonusesProgress />
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-[240px]">
            <Search size={16} className="text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher par client, BDC, produit, commercial…" className="border-0 shadow-none focus-visible:ring-0 h-9 px-0" data-testid="commissions-search" />
          </div>
          {isAdmin && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Commercial :</span>
              <Select value={commercialFilter} onValueChange={setCommercialFilter}>
                <SelectTrigger className="h-9 w-44" data-testid="commissions-commercial-filter"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Tous</SelectItem>
                  {commerciaux.map((c) => (<SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-3 py-3 overline whitespace-nowrap">Date</th>
                <th className="px-3 py-3 overline whitespace-nowrap">BDC</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Client</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Commercial</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Source</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Règlement</th>
                <th className="px-3 py-3 overline whitespace-nowrap text-right">Montant HT</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Taux</th>
                <th className="px-3 py-3 overline whitespace-nowrap text-right">Commission €</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Payer en</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Statut</th>
                <th className="px-3 py-3 overline whitespace-nowrap">Payé</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (<tr><td colSpan={12} className="p-8 text-center text-slate-500">Aucune commission pour {monthLabel(activeMonth)}.</td></tr>)}
              {filtered.map((r) => {
                const st = statusMap[r.status] || STATUS_MAP[r.status];
                return (
                  <tr key={`${r.sale_id}-${r.commercial_slot || 1}`} className={`border-b border-slate-100 ${r.commission_paid ? "bg-emerald-50/30" : ""}`} data-testid={`commission-row-${r.sale_id}${r.commercial_slot === 2 ? '-2' : ''}`}>
                    <td className="px-3 py-3 whitespace-nowrap text-slate-600">
                      <InlineCell type="date" value={r.sale_date || ""} disabled={!canEditCommissions}
                        display={r.sale_date || <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(r.sale_id, { sale_date: v })}
                        testId={`commission-date-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap font-mono text-xs">
                      <InlineCell type="text" value={r.bdc || ""} disabled={!canEditCommissions}
                        display={r.bdc || <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(r.sale_id, { bdc: v })}
                        testId={`commission-bdc-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 font-semibold text-slate-900 whitespace-nowrap">{r.client_name || <span className="text-slate-400 italic">—</span>}</td>
                    <td className="px-3 py-3 whitespace-nowrap font-medium">
                      <InlineCell type="select" value={r.commercial || ""} options={commercialOptions} disabled={!canEditCommissions}
                        display={r.commercial || <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(r.sale_id, r.commercial_slot === 2 ? { commercial_2: v } : { commercial: v }, { confirm: v && r.commercial ? `Remplacer ${r.commercial} par ${v} ?` : undefined })}
                        testId={`commission-commercial-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      <InlineCell type="select" value={r.source || ""} options={SOURCES.map((s) => ({ value: s.value, label: s.label }))} disabled={!canEditCommissions}
                        display={r.source ? <span className="text-xs">{r.source}</span> : <span className="text-slate-400 italic">—</span>}
                        onSave={(v) => patchSale(r.sale_id, { source: v })}
                        testId={`commission-source-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-slate-600">
                      <InlineCell type="select" value={r.payment_method || ""} options={PAYMENT_OPTIONS} disabled={!canEditCommissions}
                        display={formatPayment(r.payment_method, r.payment_installments)}
                        onSave={(v) => patchSale(r.sale_id, { payment_method: v })}
                        testId={`commission-payment-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 text-right font-semibold whitespace-nowrap">
                      <InlineCell type="number" value={r.amount ?? 0} disabled={!canEditCommissions}
                        display={fmtEur(r.amount)}
                        onSave={(v) => patchSale(r.sale_id, { amount: parseFloat(v || 0) }, { confirm: `Modifier le montant HT de ${fmtEur(r.amount)} à ${fmtEur(parseFloat(v || 0))} ?` })}
                        testId={`commission-amount-input-${r.sale_id}`} inputWidth={100} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      {canEditCommissions ? (
                        <Select value={String(r.commission_rate)} onValueChange={(v) => patchSale(r.sale_id, r.commercial_slot === 2 ? { commission_rate_2: parseFloat(v) } : { commission_rate: parseFloat(v) })}>
                          <SelectTrigger className="h-8 w-24" data-testid={`commission-rate-${r.sale_id}${r.commercial_slot === 2 ? '-2' : ''}`}><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {rates.map((rate) => (<SelectItem key={rate} value={String(rate)}>{formatRate(rate)}</SelectItem>))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="text-slate-700 font-medium" data-testid={`commission-rate-${r.sale_id}${r.commercial_slot === 2 ? '-2' : ''}`}>{formatRate(r.commission_rate)}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 font-semibold whitespace-nowrap text-emerald-700 text-right" data-testid={`commission-amount-${r.sale_id}`}>{fmtEur(r.commission_amount)}</td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      {canEditCommissions ? (
                        <Select value={r.commission_month || currentMonth()} onValueChange={(v) => patchSale(r.sale_id, { commission_month: v })}>
                          <SelectTrigger className="h-8 w-40" data-testid={`commission-month-${r.sale_id}`}><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {paymentMonthOptions.map((o) => (<SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="text-slate-600 text-xs" data-testid={`commission-month-${r.sale_id}`}>{monthLabel(r.commission_month || currentMonth())}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      <InlineCell type="select" value={r.status || ""} options={statusOptions} disabled={!canEditCommissions}
                        display={<Badge className={`${st?.cls || "bg-slate-200 text-slate-700"} border-0`} data-testid={`commission-status-${r.sale_id}`}>{st?.label || r.status}</Badge>}
                        onSave={(v) => patchSale(r.sale_id, { status: v })}
                        testId={`commission-status-edit-${r.sale_id}`} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      {canEditCommissions ? (
                        <button
                          onClick={() => patchSale(r.sale_id, { commission_paid: !r.commission_paid })}
                          data-testid={`commission-paid-${r.sale_id}`}
                          className={`px-2.5 py-1 rounded-full text-xs font-semibold transition-colors ${r.commission_paid ? "bg-emerald-600 text-white hover:bg-emerald-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                        >
                          {r.commission_paid ? "✓ Payé" : "À payer"}
                        </button>
                      ) : (
                        <span
                          data-testid={`commission-paid-${r.sale_id}`}
                          className={`px-2.5 py-1 rounded-full text-xs font-semibold ${r.commission_paid ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}
                        >
                          {r.commission_paid ? "✓ Payé" : "En attente"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Rates editor dialog */}
      <Dialog open={ratesOpen} onOpenChange={setRatesOpen}>
        <DialogContent className="sm:max-w-md" data-testid="rates-dialog">
          <DialogHeader><DialogTitle className="font-display text-2xl flex items-center gap-2"><Pencil size={18} /> Taux de commission disponibles</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mt-1">Ces taux sont utilisés lors du choix d'une commission dans les ventes futures. Les commissions déjà enregistrées ne sont pas recalculées.</p>
          <div className="space-y-2 mt-3">
            {rates.length === 0 && <p className="text-sm text-slate-500">Aucun taux configuré.</p>}
            {rates.map((r) => (
              <div key={r} className="flex items-center justify-between border border-slate-200 rounded-md px-3 py-2" data-testid={`rate-row-${r}`}>
                <span className="font-medium">{formatRate(r)}</span>
                <button onClick={() => removeRate(r)} className="text-red-500 hover:text-red-700" aria-label="Supprimer" data-testid={`rate-del-${r}`}><X size={14} /></button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-4">
            <Input placeholder="Nouveau taux (ex : 15% ou 0.18)" value={newRateInput} onChange={(e) => setNewRateInput(e.target.value)} data-testid="rate-new-input" />
            <Button onClick={addRate} size="sm" data-testid="rate-add-btn"><Plus size={14} className="mr-1" /> Ajouter</Button>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setRatesOpen(false)}>Fermer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <StatusManagerDialog
        open={statusManagerOpen}
        onOpenChange={setStatusManagerOpen}
        onSaved={() => {
          api.get("/sale-statuses").then((r) => setSaleStatusesPayload(r.data)).catch(() => {});
          window.dispatchEvent(new Event("kylot:settings-updated"));
        }}
      />
      </>)}
    </div>
  );
}
