import React, { useEffect, useMemo, useState } from "react";
import api, { downloadApiFile, formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, TrendingUp, XCircle, Trophy, FileDown } from "lucide-react";
import { currentMonth, shiftMonth, monthLabel } from "@/lib/saleConstants";
import { toast } from "sonner";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

function StatCard({ icon: Icon, label, value, sub, testId, accent }) {
  return (
    <Card className="p-5 border-slate-200 shadow-sm" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div>
          <p className="overline">{label}</p>
          <p className="font-display text-3xl font-semibold tracking-tight mt-2">{value}</p>
          {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
        </div>
        <div className={`h-10 w-10 rounded-lg grid place-items-center ${accent || "bg-slate-100 text-slate-700"}`}>
          <Icon size={18} />
        </div>
      </div>
    </Card>
  );
}

export default function MonthlyReport() {
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/reports/monthly?month=${month}`);
      setData(r.data);
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [month]);
  // iter58 : sync live avec les modifications de vente + refetch au focus
  useEffect(() => {
    const onFocus = () => load();
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    const onSalesUpdated = () => load();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kylot:sales-updated", onSalesUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const rows = useMemo(() => data?.rows || [], [data]);
  const totals = data?.totals || { sales_count: 0, active_count: 0, cancelled_count: 0, ca_total: 0, commission_total: 0, sources: { R1: 0, Assist: 0, CQ: 0, CA: 0 } };

  const topCommercial = useMemo(() => rows.filter((r) => r.sales_count > 0)[0], [rows]);

  return (
    <div className="p-4 md:p-8 max-w-[1500px]">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <p className="overline">Bilan mensuel</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight">Rapport mensuel</h1>
          <p className="text-sm text-slate-500 mt-2">Statistiques par vendeur pour un mois donné : ventes par source, annulations, CA et commissions.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              try {
                await downloadApiFile(`/reports/monthly.pdf?month=${encodeURIComponent(month)}`, `rapport-${month}.pdf`);
              } catch (err) {
                toast.error(formatApiError(err));
              }
            }}
            data-testid="report-pdf-btn"
          >
            <FileDown size={14} className="mr-1.5" /> Export PDF
          </Button>
          <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setMonth(shiftMonth(month, -1))} data-testid="report-prev" aria-label="Mois précédent"><ChevronLeft size={16} /></Button>
          <div className="font-display text-lg font-semibold w-40 sm:w-52 text-center capitalize flex items-center justify-center gap-2" data-testid="report-month-label">
            <CalendarIcon size={16} className="text-slate-400" />
            {monthLabel(month)}
          </div>
          <Button variant="outline" size="icon" onClick={() => setMonth(shiftMonth(month, 1))} data-testid="report-next" aria-label="Mois suivant"><ChevronRight size={16} /></Button>
          </div>
          {month !== currentMonth() && (
            <Button variant="ghost" size="sm" onClick={() => setMonth(currentMonth())} data-testid="report-today">Ce mois</Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard testId="report-stat-active" icon={TrendingUp} label="Ventes actives" value={totals.active_count} sub={`sur ${totals.sales_count} ventes du mois`} accent="bg-emerald-50 text-emerald-700" />
        <StatCard testId="report-stat-cancelled" icon={XCircle} label="Annulations" value={totals.cancelled_count} sub={totals.litige_count ? `+ ${totals.litige_count} en litige` : "sur le mois"} accent="bg-red-50 text-red-700" />
        <StatCard testId="report-stat-ca" icon={TrendingUp} label="CA du mois" value={fmtEur(totals.ca_total)} sub="hors annulé & litige" />
        <StatCard testId="report-stat-comm" icon={Trophy} label="Commissions dues" value={fmtEur(totals.commission_total)} sub={topCommercial ? `Top : ${topCommercial.commercial}` : ""} accent="bg-amber-50 text-amber-700" />
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <p className="font-display text-lg font-semibold">Détail par commercial</p>
            <p className="text-xs text-slate-500 mt-0.5">Format d'exemple : <span className="font-mono">Theo — 8 R1 · 1 Assist · 3 Annulations</span></p>
          </div>
          {loading && <span className="text-xs text-slate-400">Chargement…</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline">Commercial</th>
                <th className="px-3 py-3 overline text-right">Ventes</th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px]">R1</span></th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 text-[10px]">Assist</span></th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px]">CQ</span></th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 text-[10px]">CA</span></th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px]">TAP</span></th>
                <th className="px-3 py-3 overline text-right"><span className="inline-block px-1.5 py-0.5 rounded bg-slate-200 text-slate-800 text-[10px]">Sous-trait.</span></th>
                <th className="px-3 py-3 overline text-right text-red-700">Annulé</th>
                <th className="px-4 py-3 overline text-right">CA €</th>
                <th className="px-4 py-3 overline text-right">Commission €</th>
                <th className="px-4 py-3 overline">Résumé</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={12} className="p-8 text-center text-slate-500">Aucune vente enregistrée pour {monthLabel(month)}.</td></tr>
              )}
              {rows.map((r, idx) => {
                const isTop = idx === 0 && r.sales_count > 0;
                const summary = [
                  r.sources.R1 > 0 && `${r.sources.R1} R1`,
                  r.sources.Assist > 0 && `${r.sources.Assist} Assist`,
                  r.sources.CQ > 0 && `${r.sources.CQ} CQ`,
                  r.sources.CA > 0 && `${r.sources.CA} CA`,
                  (r.sources.TAP || 0) > 0 && `${r.sources.TAP} TAP`,
                  (r.sources["Sous-traitance"] || 0) > 0 && `${r.sources["Sous-traitance"]} Sous-traitance`,
                  r.cancelled_count > 0 && `${r.cancelled_count} annulation${r.cancelled_count > 1 ? "s" : ""}`,
                ].filter(Boolean).join(" · ") || "—";
                return (
                  <tr key={r.commercial} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/40" data-testid={`report-row-${r.commercial}`}>
                    <td className="px-4 py-3 font-semibold whitespace-nowrap flex items-center gap-2">
                      {isTop && <Trophy size={14} className="text-amber-500" />}
                      {r.commercial}
                    </td>
                    <td className="px-3 py-3 text-right">{r.sales_count}</td>
                    <td className="px-3 py-3 text-right">{r.sources.R1 || "—"}</td>
                    <td className="px-3 py-3 text-right">{r.sources.Assist || "—"}</td>
                    <td className="px-3 py-3 text-right">{r.sources.CQ || "—"}</td>
                    <td className="px-3 py-3 text-right">{r.sources.CA || "—"}</td>
                    <td className="px-3 py-3 text-right">{r.sources.TAP || "—"}</td>
                    <td className="px-3 py-3 text-right">{r.sources["Sous-traitance"] || "—"}</td>
                    <td className={`px-3 py-3 text-right ${r.cancelled_count > 0 ? "text-red-600 font-medium" : "text-slate-400"}`}>{r.cancelled_count || "—"}</td>
                    <td className="px-4 py-3 text-right font-display font-semibold">{fmtEur(r.ca_total)}</td>
                    <td className="px-4 py-3 text-right font-display font-semibold text-emerald-700">{fmtEur(r.commission_total)}</td>
                    <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{summary}</td>
                  </tr>
                );
              })}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-slate-200 bg-slate-50/40 font-semibold">
                  <td className="px-4 py-3">TOTAL</td>
                  <td className="px-3 py-3 text-right">{totals.sales_count}</td>
                  <td className="px-3 py-3 text-right">{totals.sources.R1}</td>
                  <td className="px-3 py-3 text-right">{totals.sources.Assist}</td>
                  <td className="px-3 py-3 text-right">{totals.sources.CQ}</td>
                  <td className="px-3 py-3 text-right">{totals.sources.CA}</td>
                  <td className="px-3 py-3 text-right">{totals.sources.TAP || 0}</td>
                  <td className="px-3 py-3 text-right">{totals.sources["Sous-traitance"] || 0}</td>
                  <td className="px-3 py-3 text-right text-red-600">{totals.cancelled_count}</td>
                  <td className="px-4 py-3 text-right font-display">{fmtEur(totals.ca_total)}</td>
                  <td className="px-4 py-3 text-right font-display text-emerald-700">{fmtEur(totals.commission_total)}</td>
                  <td className="px-4 py-3"></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Card>
    </div>
  );
}
