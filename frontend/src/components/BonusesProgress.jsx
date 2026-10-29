import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { TrendingUp, Trophy, Loader2 } from "lucide-react";
import { toast } from "sonner";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

export default function BonusesProgress({ compact = false, onEmpty }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get("/bonuses/progress");
        if (!cancelled) setRows(data || []);
      } catch (err) {
        if (!cancelled) toast.error(formatApiError(err));
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [refreshTick]);

  useEffect(() => {
    const handler = () => setRefreshTick((t) => t + 1);
    window.addEventListener("kylot:sales-updated", handler);
    return () => window.removeEventListener("kylot:sales-updated", handler);
  }, []);

  if (loading && rows.length === 0) {
    return <p className="text-xs text-slate-500 inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Chargement des primes…</p>;
  }
  if (!loading && rows.length === 0) {
    if (onEmpty === "hide") return null;
    return null;
  }

  return (
    <Card className={`border-slate-200 shadow-sm ${compact ? "p-4" : "p-5"}`} data-testid="bonuses-progress">
      <div className="flex items-center gap-2 mb-3">
        <Trophy size={16} className="text-amber-500" />
        <p className="font-display text-lg font-semibold">Primes en cours</p>
        {loading && <Loader2 size={12} className="animate-spin text-slate-400" />}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {rows.map((r, idx) => {
          const pct = Math.min(r.progress_pct || 0, 100);
          const color = r.reached ? "bg-emerald-500" : r.near ? "bg-amber-500" : "bg-slate-400";
          return (
            <div key={`${r.bonus_id}-${r.commercial}-${idx}`} className={`rounded-lg border p-3 ${r.reached ? "border-emerald-300 bg-emerald-50/40" : "border-slate-200 bg-white"}`} data-testid={`bonus-progress-${r.bonus_id}-${r.commercial}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] uppercase tracking-widest text-slate-500 truncate">{r.commercial}</p>
                  <p className="font-semibold text-slate-900 truncate mt-0.5">{r.bonus_name}</p>
                </div>
                <div className={`shrink-0 text-right ${r.reached ? "text-emerald-700" : "text-slate-700"}`}>
                  <p className="font-display text-xl font-semibold leading-none">{fmtEur(r.amount)}</p>
                  <p className="text-[10px] uppercase tracking-widest mt-0.5">{r.reached ? "Atteinte" : r.near ? "Proche" : "En cours"}</p>
                </div>
              </div>
              <div className="mt-2">
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                  <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {fmtEur(r.ca_current)} / {fmtEur(r.ca_threshold)}
                  {!r.reached && r.remaining > 0 && <> · reste {fmtEur(r.remaining)}</>}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
