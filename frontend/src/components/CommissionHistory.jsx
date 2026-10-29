import React, { useCallback, useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, TrendingUp, Euro, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

// iter179 — Historique des primes gagnées : matrice commercial × mois sur 12 mois glissants.
// Consomme /api/commissions/history (agrégé côté back pour rester cohérent avec la vue mensuelle).

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const FR_MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const labelForMonth = (mk) => {
  if (!mk || mk.length < 7) return mk || "";
  const [y, m] = mk.split("-").map(Number);
  return `${FR_MONTHS_SHORT[(m || 1) - 1]} ${String(y).slice(2)}`;
};

export default function CommissionHistory() {
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState(12);
  const [data, setData] = useState({ months: [], commercials: [], matrix: {}, totals_by_month: {}, totals_by_commercial: {} });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/commissions/history?months=${months}`);
      setData(data);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, [months]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const onUpd = () => load();
    window.addEventListener("kylot:sales-updated", onUpd);
    return () => window.removeEventListener("kylot:sales-updated", onUpd);
  }, [load]);

  const grandTotal = useMemo(() => {
    return Object.values(data.totals_by_month || {}).reduce((a, m) => ({
      total: a.total + (m.total || 0), paid: a.paid + (m.paid || 0), to_pay: a.to_pay + (m.to_pay || 0), count: a.count + (m.count || 0),
    }), { total: 0, paid: 0, to_pay: 0, count: 0 });
  }, [data]);

  return (
    <div className="space-y-4" data-testid="commission-history">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="overline">Historique des primes gagnées</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight">Cumul mois par mois, par commercial</h2>
          <p className="text-xs text-slate-500 mt-1">Total = primes commissionnables (ventes annulées / en litige exclues). Payé = coché « Payé » sur la vue mensuelle.</p>
        </div>
        <div className="flex items-center gap-2">
          {[6, 12, 24].map((n) => (
            <Button key={n} size="sm" variant={months === n ? "default" : "outline"} onClick={() => setMonths(n)} data-testid={`history-months-${n}`}>
              {n} mois
            </Button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-4 border-slate-200 shadow-sm" data-testid="history-total-earned">
          <div className="flex items-start justify-between">
            <div>
              <p className="overline">Total gagné · {months} mois</p>
              <p className="font-display text-2xl font-semibold tracking-tight mt-1">{fmtEur(grandTotal.total)}</p>
              <p className="text-xs text-slate-500 mt-0.5">{grandTotal.count} ligne{grandTotal.count > 1 ? "s" : ""}</p>
            </div>
            <div className="h-9 w-9 rounded-lg bg-slate-100 text-slate-700 grid place-items-center"><Euro size={16} /></div>
          </div>
        </Card>
        <Card className="p-4 border-slate-200 shadow-sm" data-testid="history-total-paid">
          <div className="flex items-start justify-between">
            <div>
              <p className="overline">Déjà payé</p>
              <p className="font-display text-2xl font-semibold tracking-tight mt-1 text-emerald-700">{fmtEur(grandTotal.paid)}</p>
            </div>
            <div className="h-9 w-9 rounded-lg bg-emerald-50 text-emerald-700 grid place-items-center"><CheckCircle2 size={16} /></div>
          </div>
        </Card>
        <Card className="p-4 border-slate-200 shadow-sm" data-testid="history-total-topay">
          <div className="flex items-start justify-between">
            <div>
              <p className="overline">Reste à payer</p>
              <p className="font-display text-2xl font-semibold tracking-tight mt-1 text-amber-700">{fmtEur(grandTotal.to_pay)}</p>
            </div>
            <div className="h-9 w-9 rounded-lg bg-amber-50 text-amber-700 grid place-items-center"><TrendingUp size={16} /></div>
          </div>
        </Card>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-10 flex items-center justify-center text-slate-500 text-sm gap-2">
            <Loader2 size={16} className="animate-spin" /> Chargement…
          </div>
        ) : data.commercials.length === 0 ? (
          <div className="p-10 text-center text-slate-500 text-sm">Aucune prime sur la période sélectionnée.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                  <th className="px-3 py-3 overline whitespace-nowrap sticky left-0 bg-slate-50/95 z-10">Commercial</th>
                  {data.months.map((mk) => (
                    <th key={mk} className="px-3 py-3 overline whitespace-nowrap text-right">{labelForMonth(mk)}</th>
                  ))}
                  <th className="px-3 py-3 overline whitespace-nowrap text-right bg-slate-100/60">Total</th>
                </tr>
              </thead>
              <tbody>
                {data.commercials.map((name) => {
                  const t = data.totals_by_commercial[name] || {};
                  return (
                    <tr key={name} className="border-b border-slate-100 hover:bg-slate-50/50" data-testid={`history-row-${name}`}>
                      <td className="px-3 py-3 font-semibold text-slate-900 whitespace-nowrap sticky left-0 bg-white/95">{name}</td>
                      {data.months.map((mk) => {
                        const cell = (data.matrix[name] || {})[mk];
                        if (!cell || !cell.total) return <td key={mk} className="px-3 py-3 text-right text-slate-300">—</td>;
                        return (
                          <td key={mk} className="px-3 py-3 text-right whitespace-nowrap" data-testid={`history-cell-${name}-${mk}`}>
                            <div className="font-semibold text-slate-900">{fmtEur(cell.total)}</div>
                            <div className="text-[10px] text-slate-500">
                              <span className="text-emerald-700">{fmtEur(cell.paid)}</span>
                              {" · "}
                              <span className="text-amber-700">{fmtEur(cell.to_pay)}</span>
                            </div>
                          </td>
                        );
                      })}
                      <td className="px-3 py-3 text-right whitespace-nowrap bg-slate-50/60 font-semibold text-slate-900">
                        {fmtEur(t.total || 0)}
                        <div className="text-[10px] text-slate-500 font-normal">{t.count || 0} ligne{(t.count || 0) > 1 ? "s" : ""}</div>
                      </td>
                    </tr>
                  );
                })}
                {/* Ligne total mensuel */}
                <tr className="bg-slate-100/60 font-semibold">
                  <td className="px-3 py-3 whitespace-nowrap sticky left-0 bg-slate-100/95">Total</td>
                  {data.months.map((mk) => {
                    const tm = data.totals_by_month[mk] || {};
                    return (
                      <td key={mk} className="px-3 py-3 text-right whitespace-nowrap">
                        {tm.total ? fmtEur(tm.total) : <span className="text-slate-300">—</span>}
                      </td>
                    );
                  })}
                  <td className="px-3 py-3 text-right whitespace-nowrap bg-slate-200/60">{fmtEur(grandTotal.total)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="text-[11px] text-slate-400 mt-1">Sur chaque cellule : <span className="text-emerald-700">montant payé</span> · <span className="text-amber-700">reste à payer</span>.</p>
    </div>
  );
}
