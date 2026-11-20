import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Wallet, Banknote } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import useTeam from "@/lib/useTeam";
import { SOURCES } from "@/lib/saleConstants";
import { CommercialRow } from "@/pages/Sales";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

export default function SalesTable() {
  const { user } = useAuth();
  const { commerciaux, reload } = useTeam();
  const [summary, setSummary] = useState({ by_commercial: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/sales/summary");
      setSummary(data || { by_commercial: [] });
      setError(false);
    } catch (_) { setError(true); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

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

      <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="commercials-summary">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2 flex-wrap">
          <p className="font-display text-lg font-semibold">CA par commercial</p>
          <span className="text-xs text-slate-500">(hors annulé & litige)</span>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1"><Wallet size={12} /> Comptant</span>
            <span className="flex items-center gap-1"><Banknote size={12} /> Financement</span>
          </div>
        </div>
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Tableau défilant">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline">Commercial</th>
                <th className="px-4 py-3 overline text-right">Chiffre d’affaires</th>
                <th className="px-3 py-3 overline text-right">Ventes</th>
                {SOURCES.map((s) => <th key={s.value} className="px-2.5 py-3 overline text-right">{s.label}</th>)}
                <th className="px-3 py-3 overline text-right">Objectif</th>
                <th className="px-4 py-3 overline">Progression</th>
                <th className="px-3 py-3 overline text-right">Comptant</th>
                <th className="px-3 py-3 overline text-right">Fin.</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={12} className="p-8 text-center text-sm text-slate-500">Chargement…</td></tr>}
              {!loading && rows.length === 0 && <tr><td colSpan={12} className="p-8 text-center text-sm text-slate-500">Aucune vente sur la période.</td></tr>}
              {!loading && rows.map((c) => (
                <CommercialRow key={c.name} c={c} isAdmin={user?.role === "admin"} onObjectifSaved={async () => { await reload(); await load(); }} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="mt-3 text-xs text-slate-500">Total affiché : {fmtEur(rows.reduce((a, c) => a + (c.ca || 0), 0))} · {rows.reduce((a, c) => a + (c.count || 0), 0)} vente(s)</p>
    </div>
  );
}
