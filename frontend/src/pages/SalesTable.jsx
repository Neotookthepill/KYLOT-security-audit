import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Wallet, Banknote, CalendarDays } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import useTeam from "@/lib/useTeam";
import { SOURCES } from "@/lib/saleConstants";
import { formatDateFR } from "@/lib/dateFormat";
import { CommercialRow } from "@/pages/Sales";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

export default function SalesTable() {
  const { user } = useAuth();
  const { commerciaux, reload } = useTeam();
  const [summary, setSummary] = useState({ by_commercial: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [period, setPeriod] = useState("month");

  const bounds = React.useMemo(() => {
    const today = new Date();
    const iso = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}-${m}-${day}`;
    };
    if (period === "day") return { from: iso(today), to: iso(today) };
    if (period === "week") {
      const d = new Date(today);
      const wd = (d.getDay() + 6) % 7;
      d.setDate(d.getDate() - wd);
      const end = new Date(d); end.setDate(d.getDate() + 6);
      return { from: iso(d), to: iso(end) };
    }
    if (period === "year") return { from: `${today.getFullYear()}-01-01`, to: `${today.getFullYear()}-12-31` };
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return { from: iso(first), to: iso(last) };
  }, [period]);

  const objectiveRatio = React.useMemo(() => {
    const start = new Date(`${bounds.from}T00:00:00`);
    const end = new Date(`${bounds.to}T00:00:00`);
    const days = Math.max(1, Math.round((end - start) / 86400000) + 1);
    const year = start.getFullYear();
    const yearDays = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 366 : 365;
    return days / yearDays;
  }, [bounds.from, bounds.to]);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/sales/summary?from_date=${bounds.from}&to_date=${bounds.to}`);
      setSummary(data || { by_commercial: [] });
      setError(false);
    } catch (_) { setError(true); }
    finally { setLoading(false); }
  }, [bounds.from, bounds.to]);

  useEffect(() => { load(); }, [load]);

  const rows = React.useMemo(() => {
    const norm = (v) => (v || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    const firstOf = (v) => norm(v).split(/\s+/)[0] || "";
    const list = Array.isArray(commerciaux) ? commerciaux : [];
    const grouped = {};
    const ensure = (c) => {
      const key = c.id || c.name;
      if (!grouped[key]) grouped[key] = { id: c.id, name: c.name, count: 0, ca: 0, sources: {}, comptant: 0, financement: 0 };
      return grouped[key];
    };
    for (const row of summary.by_commercial || []) {
      const exact = list.find((c) => norm(c.name) === norm(row.name));
      const matches = list.filter((c) => firstOf(c.name) === firstOf(row.name));
      const target = exact || (matches.length === 1 ? matches[0] : null);
      if (!target) continue;
      const b = ensure(target);
      b.count += Number(row.count || 0); b.ca += Number(row.ca || 0);
      for (const [k, v] of Object.entries(row.sources || {})) b.sources[k] = (b.sources[k] || 0) + Number(v || 0);
      b.comptant += Number(row.comptant || 0); b.financement += Number(row.financement || 0);
    }
    return list.map((c) => ({ ...(grouped[c.id || c.name] || ensure(c)), objectif: c.objectif || 0 })).sort((a, b) => b.ca - a.ca);
  }, [summary, commerciaux]);
  return (
    <div className="p-4 md:p-8 max-w-[1700px]" data-testid="sales-table-page">
      <div className="mb-6">
        <p className="overline">Pilotage commercial</p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Tableau de vente</h1>
        <p className="page-subtitle">Classement, chiffre d’affaires et objectifs par commercial.</p>
      </div>

      {error && <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">Impossible de charger le classement.</p>}

      <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="sales-table-period-filter">
        <CalendarDays size={14} className="text-slate-500" />
        {[{ k: "month", l: "Mois" }, { k: "week", l: "Semaine" }, { k: "day", l: "Jour" }, { k: "year", l: "Année" }].map((p) => (
          <button key={p.k} type="button" onClick={() => setPeriod(p.k)}
            className={`min-h-[36px] text-xs px-3 py-1.5 rounded-[10px] border transition-colors ${period === p.k ? "bg-primary text-primary-foreground border-primary" : "bg-white text-[#344054] border-[#DDE3EC] hover:border-primary/40 dark:bg-card dark:text-foreground dark:border-border dark:hover:border-primary/60"}`}
            data-testid={`sales-table-period-${p.k}`}>
            {p.l}
          </button>
        ))}
        <span className="text-xs text-slate-500">{bounds.from === bounds.to ? formatDateFR(bounds.from) : `${formatDateFR(bounds.from)} → ${formatDateFR(bounds.to)}`}</span>
      </div>
      <p className="mb-4 text-[11px] text-slate-500">
        Objectif période = objectif annuel × jours de la période / 365. L’objectif annuel enregistré n’est pas modifié.
      </p>

      <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="commercials-summary">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2 flex-wrap">
          <p className="font-display text-lg font-semibold">CA par commercial</p>
          <span className="text-xs text-slate-500">(hors annulé & litige)</span>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1"><Wallet size={12} /> Comptant</span>
            <span className="flex items-center gap-1"><Banknote size={12} /> Financement</span>
          </div>
        </div>
        <div className="hidden overflow-x-auto md:block" tabIndex={0} role="region" aria-label="Tableau défilant">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline">Commercial</th>
                <th className="px-4 py-3 overline text-right">Chiffre d’affaires</th>
                <th className="px-3 py-3 overline text-right">Ventes</th>
                <th className="px-3 py-3 overline text-right" title="Objectif annuel proratisé sur la période sélectionnée">Objectif période</th>
                <th className="px-4 py-3 overline">Progression</th>
                <th className="px-3 py-3 overline text-right">Comptant</th>
                <th className="px-3 py-3 overline text-right">Fin.</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="p-8 text-center text-sm text-slate-500">Chargement…</td></tr>}
              {!loading && rows.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-sm text-slate-500">Aucune vente sur la période.</td></tr>}
              {!loading && rows.map((c) => (
                <CommercialRow key={c.name} c={c} isAdmin={user?.role === "admin"} targetObjectif={Math.round((c.objectif || 0) * objectiveRatio)} objectiveRatio={objectiveRatio} onObjectifSaved={async () => { await reload(); await load(); }} />
              ))}
            </tbody>
          </table>
        </div>

        <div className="divide-y divide-slate-100 md:hidden" data-testid="commercials-mobile-list">
          {loading && <p className="p-6 text-center text-sm text-slate-500">Chargement…</p>}
          {!loading && rows.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aucune vente sur la période.</p>}
          {!loading && rows.map((c) => {
            const target = Math.round((c.objectif || 0) * objectiveRatio);
            const pct = target > 0 ? Math.min(100, Math.round((c.ca / target) * 100)) : 0;
            const reached = target > 0 && c.ca >= target;
            return (
              <div key={`mobile-${c.name}`} className="p-4 space-y-3" data-testid={`commercial-mobile-${c.name}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{c.name}</p>
                    <p className="text-[11px] text-slate-500">{c.count} vente{c.count > 1 ? "s" : ""}</p>
                  </div>
                  <p className="font-display text-xl font-semibold whitespace-nowrap">{fmtEur(c.ca)}</p>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-lg bg-slate-50 px-2.5 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Objectif période</p>
                    <p className="mt-0.5 font-semibold">{target > 0 ? fmtEur(target) : "Non défini"}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-2.5 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Progression</p>
                    <p className={`mt-0.5 font-semibold ${reached ? "text-emerald-700" : "text-slate-900"}`}>{target > 0 ? `${Math.round((c.ca / target) * 100)} %` : "—"}</p>
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${reached ? "bg-gradient-to-r from-emerald-500 to-teal-400" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`} style={{ width: `${pct}%` }} />
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>{fmtEur(c.comptant)} comptant</span>
                  <span>{fmtEur(c.financement)} financement</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
      <p className="mt-3 text-xs text-slate-500">Total affiché : {fmtEur(rows.reduce((a, c) => a + (c.ca || 0), 0))} · {rows.reduce((a, c) => a + (c.count || 0), 0)} vente(s)</p>
    </div>
  );
}
