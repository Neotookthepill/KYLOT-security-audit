import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UserSearch, Users as UsersIcon, Euro, Search, Check, Calendar as CalIcon } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { mgrBonusesFor, cleanMgrBonuses } from "@/components/ProspectMgrBonuses";
import { resolveStatusesFromPayload, buildStatusMap } from "@/lib/saleConstants";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const fmtEur2 = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n || 0);
const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const INACTIVE = ["annule", "litige"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const PERIODS = [
  { k: "today", l: "Aujourd'hui" }, { k: "week", l: "Cette semaine" }, { k: "month", l: "Ce mois" },
  { k: "prev", l: "Mois préc." }, { k: "year", l: "Année" }, { k: "custom", l: "Personnalisé" },
];
const boundsFor = (period, customFrom, customTo) => {
  const today = new Date();
  if (period === "today") return { from: iso(today), to: iso(today), label: "Aujourd'hui" };
  if (period === "week") {
    const d = new Date(today);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const end = new Date(d); end.setDate(d.getDate() + 6);
    return { from: iso(d), to: iso(end), label: "Cette semaine" };
  }
  if (period === "prev") return { from: iso(new Date(today.getFullYear(), today.getMonth() - 1, 1)), to: iso(new Date(today.getFullYear(), today.getMonth(), 0)), label: "Mois précédent" };
  if (period === "year") return { from: `${today.getFullYear()}-01-01`, to: `${today.getFullYear()}-12-31`, label: `Année ${today.getFullYear()}` };
  if (period === "custom") return { from: customFrom || "1970-01-01", to: customTo || "2999-12-31", label: "Personnalisé" };
  return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(new Date(today.getFullYear(), today.getMonth() + 1, 0)), label: "Ce mois" };
};

function PeriodFilter({ period, setPeriod, customFrom, setCustomFrom, customTo, setCustomTo, label, count }) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="prospect-period-filter">
      <CalIcon size={14} className="text-slate-500" />
      {PERIODS.map((p) => (
        <button key={p.k} type="button" onClick={() => setPeriod(p.k)} data-testid={`prospect-period-${p.k}`}
          className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${period === p.k ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"}`}>
          {p.l}
        </button>
      ))}
      {period === "custom" && (
        <div className="flex items-center gap-1 ml-1">
          <Input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} className="h-8 w-36" data-testid="prospect-period-from" />
          <span className="text-xs text-slate-400">au</span>
          <Input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} className="h-8 w-36" data-testid="prospect-period-to" />
        </div>
      )}
      <span className="text-xs text-slate-500 ml-1" data-testid="prospect-period-count">{label} — {count} client{count > 1 ? "s" : ""}</span>
    </div>
  );
}

const comMonth = (r) => r.prospect_commission_month || (r.sale_date || "").slice(0, 7);
const MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const monthLabel = (ym) => (ym ? `${MONTHS_FR[parseInt(ym.slice(5, 7), 10) - 1]} ${ym.slice(0, 4)}` : "—");
const monthOptions = (saleYm) => {
  const set = new Set();
  const now = new Date();
  for (let i = -3; i <= 3; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    set.add(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  if (saleYm) {
    const [y, m] = saleYm.split("-").map(Number);
    for (let i = 0; i <= 3; i++) {
      const d = new Date(y, m - 1 + i, 1);
      set.add(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    }
  }
  return Array.from(set).sort();
};

// Base acquise dès la 1re vente du mois de commission ; commissions à partir de la (seuil+1)e vente
const payByMonth = (rows, threshold, base, mgrIds = new Set(), mgrBase = 0) => {
  const g = {};
  for (const r of [...rows].sort((a, b) => (a.sale_date || "").localeCompare(b.sale_date || ""))) {
    const k = `${r.prospecteur_id}|${comMonth(r)}`;
    g[k] = g[k] || { pid: r.prospecteur_id, count: 0, comm: 0 };
    g[k].count += 1;
    if (g[k].count > threshold) g[k].comm += r.prospecteur_commission || 0;
  }
  return Object.values(g).map((x) => ({ ...x, base: x.count >= 1 ? (mgrIds.has(x.pid) ? mgrBase : base) : 0 }));
};

function ByProspecteur({ caRows, payRows, threshold, base, mgrIds, mgrBase }) {
  const months = payByMonth(payRows, threshold, base, mgrIds, mgrBase);
  const names = {};
  [...caRows, ...payRows].forEach((r) => { names[r.prospecteur_id] = r.prospecteur_name || "—"; });
  const list = Object.keys(names).map((pid) => {
    const mine = caRows.filter((r) => r.prospecteur_id === pid);
    const pm = months.filter((mm) => mm.pid === pid);
    return { pid, name: names[pid], count: mine.length, ca: mine.reduce((a, r) => a + (parseFloat(r.amount) || 0), 0),
      base: pm.reduce((a, mm) => a + mm.base, 0), comm: pm.reduce((a, mm) => a + mm.comm, 0) };
  }).sort((a, b) => b.count - a.count || b.ca - a.ca);
  const totalCount = Math.max(1, list.reduce((a, x) => a + x.count, 0));
  if (!list.length) return null;
  return (
    <Card className="p-5 border-slate-200 shadow-sm" data-testid="prospect-by-prospecteur">
      <p className="overline mb-3">CA et rémunération par prospecteur</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {list.map((x, i) => (
          <div key={x.name} className={`rounded-xl border p-4 flex flex-col gap-3 transition-transform hover:-translate-y-0.5 ${i === 0 ? "border-amber-200 bg-amber-50/40" : "border-slate-200 bg-white"}`} data-testid={`prospect-ca-row-${x.name}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-900 truncate">{x.name}</span>
              <span className={`text-[11px] font-semibold rounded-full px-2 py-0.5 ${i === 0 ? "bg-amber-400 text-white" : "bg-slate-100 text-slate-600"}`}>#{i + 1}</span>
            </div>
            <div className="flex items-end justify-between gap-2">
              <div data-testid={`prospect-count-${x.name}`}>
                <span className="font-display text-4xl font-semibold leading-none text-slate-900">{x.count}</span>
                <span className="text-sm text-slate-500 ml-1">vente{x.count > 1 ? "s" : ""}</span>
              </div>
              <span className="text-xs text-slate-500">{Math.round((x.count / totalCount) * 100)} % de l'équipe</span>
            </div>
            <div className="flex items-baseline justify-between border-t border-slate-100 pt-3">
              <span className="text-xs uppercase tracking-wide text-slate-500">CA</span>
              <span className="font-display text-xl font-semibold text-slate-900" data-testid={`prospect-ca-${x.name}`}>{fmtEur(x.ca)}</span>
            </div>
            <div className="text-xs text-slate-500">Rémunération <b className="text-emerald-700 text-sm">{fmtEur2(x.base + x.comm)}</b><br />base {fmtEur2(x.base)} + com. {fmtEur(x.comm)}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ManagerCommission({ rows, goal, rateBelow, rateAbove, singleMonth, mgrBase, monthsCount, bonuses }) {
  const byMonth = {};
  rows.forEach((r) => {
    const m = (r.sale_date || "").slice(0, 7);
    byMonth[m] = byMonth[m] || { count: 0, ca: 0 };
    byMonth[m].count += 1; byMonth[m].ca += parseFloat(r.amount) || 0;
  });
  const months = Object.values(byMonth).map((x) => ({ ...x, reached: x.count >= goal, rate: x.count >= goal ? rateAbove : rateBelow }));
  const ca = months.reduce((a, x) => a + x.ca, 0);
  const comm = months.reduce((a, x) => a + (x.ca * x.rate) / 100, 0);
  const reachedBonuses = Object.values(byMonth).flatMap((x) => mgrBonusesFor(bonuses, x.count, x.ca));
  const primes = reachedBonuses.reduce((a, b) => a + b.amount, 0);
  const count = rows.length;
  const cur = months[0];
  const reached = singleMonth ? count >= goal : null;
  const rate = singleMonth ? (reached ? rateAbove : rateBelow) : null;
  return (
    <Card className="p-5 border-slate-200 shadow-sm" data-testid="prospect-manager-commission">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="overline">Commission responsable prospection</p>
          {singleMonth ? (
            <p className="text-sm text-slate-600 mt-2">
              <b className="font-display text-2xl text-slate-900" data-testid="prospect-mgr-progress">{count} / {goal}</b> ventes ·{" "}
              <span className={reached ? "text-emerald-700 font-semibold" : "text-amber-700 font-semibold"} data-testid="prospect-mgr-rate">{String(rate).replace(".", ",")} %</span>{" "}
              {reached ? "(objectif atteint)" : `(objectif à ${goal} ventes → ${String(rateAbove).replace(".", ",")} %)`}
            </p>
          ) : (
            <p className="text-sm text-slate-600 mt-2">{months.length} mois · {months.filter((m) => m.reached).length} objectif{months.filter((m) => m.reached).length > 1 ? "s" : ""} atteint{months.filter((m) => m.reached).length > 1 ? "s" : ""} · calculé mois par mois</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">{singleMonth && cur ? `${String(rate).replace(".", ",")} % de ${fmtEur(ca)}` : `sur ${fmtEur(ca)} de CA`}</p>
          <p className="font-display text-3xl font-semibold text-emerald-700" data-testid="prospect-mgr-commission">{fmtEur(comm)}</p>
          <p className="text-xs text-slate-500 mt-1" data-testid="prospect-mgr-total">Base {fmtEur2(mgrBase * monthsCount)} brut + commission{primes > 0 ? ` + primes ${fmtEur2(primes)}` : ""} = <b className="text-slate-900">{fmtEur2(mgrBase * monthsCount + comm + primes)}</b></p>
        </div>
      </div>
      {cleanMgrBonuses(bonuses).length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3" data-testid="prospect-mgr-bonuses-status">
          {cleanMgrBonuses(bonuses).map((b) => {
            const n = reachedBonuses.filter((r) => r.id === b.id).length;
            return (
              <span key={b.id} className={`text-[11px] px-2 py-0.5 rounded-full border ${n ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-slate-50 border-slate-200 text-slate-500"}`}>
                {b.name} · dès {b.metric === "sales" ? `${b.threshold} ventes` : fmtEur(b.threshold)} → {fmtEur(b.amount)}{n ? ` ✓${n > 1 ? ` ×${n}` : ""}` : ""}
              </span>
            );
          })}
        </div>
      )}
      {singleMonth && <div className="h-1.5 rounded-full bg-slate-100 mt-3 overflow-hidden"><div className={`h-full rounded-full transition-[width] duration-500 ${reached ? "bg-emerald-600" : "bg-amber-500"}`} style={{ width: `${Math.min(100, (count / goal) * 100)}%` }} /></div>}
    </Card>
  );
}

function Stat({ label, value, icon: Icon, testId }) {
  return (
    <Card className="p-5 border-slate-200 shadow-sm" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div>
          <p className="overline">{label}</p>
          <p className="font-display text-3xl font-semibold tracking-tight mt-2">{value}</p>
        </div>
        <div className="h-10 w-10 rounded-lg bg-slate-100 text-slate-700 grid place-items-center"><Icon size={18} /></div>
      </div>
    </Card>
  );
}

function ComMonthCell({ row, editable, onSaved }) {
  const cm = comMonth(row);
  const moved = cm !== (row.sale_date || "").slice(0, 7);
  if (!editable) return <span className={`text-xs whitespace-nowrap ${moved ? "text-amber-700 font-semibold" : "text-slate-600"}`} data-testid={`prospect-com-month-${row.id}`}>{monthLabel(cm)}</span>;
  const change = async (v) => {
    try {
      await api.put(`/prospection/${row.id}`, { prospect_commission_month: v });
      toast.success(`Commission affectée à ${monthLabel(v)}`);
      onSaved(row.id, { prospect_commission_month: v });
    } catch (e) { toast.error(formatApiError(e)); }
  };
  return (
    <Select value={cm} onValueChange={change}>
      <SelectTrigger className={`h-8 w-36 text-xs ${moved ? "border-amber-300 text-amber-800" : ""}`} data-testid={`prospect-com-month-${row.id}`}><SelectValue /></SelectTrigger>
      <SelectContent>
        {monthOptions((row.sale_date || "").slice(0, 7)).map((m) => (<SelectItem key={m} value={m}>{monthLabel(m)}</SelectItem>))}
      </SelectContent>
    </Select>
  );
}

function CommissionCell({ row, editable, onSaved }) {
  const [val, setVal] = useState(String(row.prospecteur_commission ?? 0));
  useEffect(() => { setVal(String(row.prospecteur_commission ?? 0)); }, [row.prospecteur_commission]);
  if (!editable) return <span className="font-display font-semibold text-emerald-700" data-testid={`prospect-commission-${row.id}`}>{fmtEur(row.prospecteur_commission)}</span>;
  const dirty = parseFloat(val || 0) !== (row.prospecteur_commission || 0);
  const save = async () => {
    try {
      await api.put(`/prospection/${row.id}`, { prospecteur_commission: parseFloat(val || 0) });
      toast.success("Commission enregistrée");
      onSaved(row.id, { prospecteur_commission: parseFloat(val || 0) });
    } catch (e) { toast.error(formatApiError(e)); }
  };
  return (
    <div className="flex items-center justify-end gap-1.5">
      <Input type="number" min={0} step="10" value={val} onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && dirty) save(); }}
        className="h-8 w-24 text-right" data-testid={`prospect-commission-input-${row.id}`} />
      <span className="text-xs text-slate-400">€</span>
      {dirty && (
        <button type="button" onClick={save} className="h-8 w-8 grid place-items-center rounded-md bg-slate-900 text-white hover:bg-slate-700 transition-colors" data-testid={`prospect-commission-save-${row.id}`}><Check size={14} /></button>
      )}
    </div>
  );
}

export default function Prospecteur() {
  const { user } = useAuth();
  const { settings } = useSettings();
  const isManager = ["admin", "responsable", "responsable_prospecteur"].includes(user?.role);
  const canEdit = ["admin", "responsable"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [prospecteurs, setProspecteurs] = useState([]);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [statusMap, setStatusMap] = useState(buildStatusMap());
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const bounds = useMemo(() => boundsFor(period, customFrom, customTo), [period, customFrom, customTo]);

  useEffect(() => {
    api.get("/sale-statuses").then((r) => setStatusMap(buildStatusMap(resolveStatusesFromPayload(r.data)))).catch(() => {});
    if (isManager) api.get("/prospecteurs").then((r) => setProspecteurs(r.data || [])).catch(() => {});
  }, [isManager]);

  useEffect(() => {
    setLoading(true);
    const params = isManager && filter !== "all" ? { prospecteur_id: filter } : {};
    api.get("/prospection", { params }).then((r) => setRows(r.data || [])).catch((e) => toast.error(formatApiError(e))).finally(() => setLoading(false));
  }, [filter, isManager]);

  const inSale = (r) => r.sale_date && r.sale_date.slice(0, 10) >= bounds.from && r.sale_date.slice(0, 10) <= bounds.to;
  const inCom = (r) => comMonth(r) >= bounds.from.slice(0, 7) && comMonth(r) <= bounds.to.slice(0, 7);
  const visible = useMemo(() => rows.filter((r) => inSale(r) || inCom(r))
    .filter((r) => !q || norm(`${r.client_name} ${r.client_city} ${r.service} ${r.prospecteur_name}`).includes(norm(q))), [rows, q, bounds]); // eslint-disable-line react-hooks/exhaustive-deps
  const caRows = visible.filter((r) => inSale(r) && !INACTIVE.includes(r.status));
  const payRows = visible.filter((r) => inCom(r) && !INACTIVE.includes(r.status));
  const totalCA = caRows.reduce((a, r) => a + (parseFloat(r.amount) || 0), 0);
  const threshold = parseInt(settings?.prospect_smic_threshold ?? 3, 10) || 3;
  const baseAmt = parseFloat(settings?.prospect_smic_amount ?? 1867) || 0;
  const singleMonth = bounds.from.slice(0, 7) === bounds.to.slice(0, 7);
  const teamRows = rows.filter((r) => inSale(r) && !INACTIVE.includes(r.status));
  const mgrGoal = parseInt(settings?.prospect_mgr_goal_sales ?? 12, 10) || 12;
  const mgrBelow = parseFloat(settings?.prospect_mgr_rate_below ?? 1) || 0;
  const mgrAbove = parseFloat(settings?.prospect_mgr_rate_above ?? 2) || 0;
  const mgrBase = parseFloat(settings?.prospect_mgr_base_amount ?? 2329.97) || 0;
  const mgrIds = new Set(prospecteurs.filter((p) => p.role === "responsable_prospecteur").map((p) => p.id));
  const monthsCount = (() => {
    const [y1, m1] = bounds.from.slice(0, 7).split("-").map(Number);
    const [y2, m2] = bounds.to.slice(0, 7).split("-").map(Number);
    if (period === "custom" && (!customFrom || !customTo)) return 1;
    return Math.max(1, (y2 - y1) * 12 + (m2 - m1) + 1);
  })();
  const pay = payByMonth(payRows, threshold, baseAmt, mgrIds, mgrBase);
  const totalPay = pay.reduce((a, x) => a + x.base + x.comm, 0);
  const onSaved = (id, patch) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  return (
    <div className="space-y-6 p-4 md:p-8" data-testid="prospecteur-page">
      <div>
        <p className="overline">Suivi prospection</p>
        <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight flex items-center gap-3"><UserSearch size={28} /> Prospecteur</h1>
        {!isManager && <p className="text-sm text-slate-500 mt-1">Vos clients prospectés — consultation uniquement.</p>}
      </div>

      <PeriodFilter period={period} setPeriod={setPeriod} customFrom={customFrom} setCustomFrom={setCustomFrom}
        customTo={customTo} setCustomTo={setCustomTo} label={bounds.label} count={visible.length} />

      <div className={`grid grid-cols-1 gap-4 ${isManager ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-3"}`}>
        {isManager && <Stat label="CA généré" value={fmtEur(totalCA)} icon={Euro} testId="prospect-stat-ca" />}
        <Stat label="Clients" value={caRows.length} icon={UsersIcon} testId="prospect-stat-clients" />
        <Stat label="Ventes en commission" value={payRows.length} icon={UserSearch} testId="prospect-stat-active" />
        <Stat label="Rémunération" value={fmtEur(totalPay)} icon={Euro} testId="prospect-stat-commission" />
      </div>

      {!isManager && singleMonth && (
        <Card className="p-4 border-slate-200 shadow-sm text-sm" data-testid="prospect-smic-progress">
          {payRows.length === 0
            ? <p>Aucune vente en commission ce mois-ci — le salaire de base de <b>{fmtEur(baseAmt)}</b> est acquis dès la 1re vente.</p>
            : payRows.length <= threshold
              ? <p><b className="text-emerald-700">Salaire de base acquis</b> ({fmtEur(baseAmt)}) — {payRows.length} / {threshold} ventes. Les commissions s'ajoutent à partir de la {threshold + 1}e vente.</p>
              : <p><b className="text-emerald-700">Salaire de base + commissions</b> — {payRows.length} ventes, dont {payRows.length - threshold} commissionnée{payRows.length - threshold > 1 ? "s" : ""}.</p>}
          <div className="h-1.5 rounded-full bg-slate-100 mt-2 overflow-hidden"><div className="h-full bg-emerald-600 rounded-full transition-[width] duration-500" style={{ width: `${Math.min(100, (payRows.length / threshold) * 100)}%` }} /></div>
        </Card>
      )}

      {isManager && <ManagerCommission rows={teamRows} goal={mgrGoal} rateBelow={mgrBelow} rateAbove={mgrAbove} singleMonth={singleMonth} mgrBase={mgrBase} monthsCount={monthsCount} bonuses={settings?.prospect_mgr_bonuses} />}

      {isManager && <ByProspecteur caRows={caRows} payRows={payRows} threshold={threshold} base={baseAmt} mgrIds={mgrIds} mgrBase={mgrBase} />}

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un client, une ville…" className="pl-9" data-testid="prospect-search" />
        </div>
        {isManager && (
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="sm:w-64" data-testid="prospect-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les prospecteurs</SelectItem>
              {prospecteurs.map((p) => (<SelectItem key={p.id} value={p.id}>{p.name}{p.role === "responsable_prospecteur" ? " (Responsable)" : ""}</SelectItem>))}
            </SelectContent>
          </Select>
        )}
      </div>

      <Card className="border-slate-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm" data-testid="prospect-table">
          <thead>
            <tr className="text-left border-b border-slate-200 bg-slate-50/60">
              <th className="px-4 py-3 overline">Date</th>
              <th className="px-4 py-3 overline">Client</th>
              <th className="px-4 py-3 overline">Ville</th>
              {isManager && <th className="px-4 py-3 overline">Prestation</th>}
              {isManager && <th className="px-4 py-3 overline text-right">Montant</th>}
              {isManager && <th className="px-4 py-3 overline">Prospecteur</th>}
              <th className="px-4 py-3 overline">Statut</th>
              <th className="px-4 py-3 overline">Mois com.</th>
              <th className="px-4 py-3 overline text-right">Commission</th>
            </tr>
          </thead>
          <tbody>
            {!loading && visible.length === 0 && (
              <tr><td colSpan={9} className="p-8 text-center text-slate-500" data-testid="prospect-empty">Aucun client pour le moment.</td></tr>
            )}
            {visible.map((r) => {
              const st = statusMap[r.status];
              return (
                <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/40" data-testid={`prospect-row-${r.id}`}>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-500">{r.sale_date ? new Date(r.sale_date).toLocaleDateString("fr-FR") : "—"}</td>
                  <td className="px-4 py-3">
                    <p className="font-semibold">{r.client_name || "—"}</p>
                    {r.client_phone && <p className="text-xs text-slate-500">{r.client_phone}</p>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{[r.client_postal_code, r.client_city].filter(Boolean).join(" ") || "—"}</td>
                  {isManager && <td className="px-4 py-3 text-slate-600 max-w-[220px] truncate" title={r.service}>{r.service || "—"}</td>}
                  {isManager && <td className="px-4 py-3 text-right whitespace-nowrap font-medium" data-testid={`prospect-amount-${r.id}`}>{fmtEur(r.amount)}</td>}
                  {isManager && <td className="px-4 py-3 whitespace-nowrap">{r.prospecteur_name}</td>}
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${st?.cls || "bg-slate-100 text-slate-700"}`} data-testid={`prospect-status-${r.id}`}>{st?.label || r.status}</span>
                  </td>
                  <td className="px-4 py-3"><ComMonthCell row={r} editable={canEdit} onSaved={onSaved} /></td>
                  <td className="px-4 py-3 text-right"><CommissionCell row={r} editable={canEdit} onSaved={onSaved} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
