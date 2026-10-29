import React, { useCallback, useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, TrendingUp, Trophy, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"];
const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

function AnnualChart({ monthly, objectifMonthly, height = 90 }) {
  const max = Math.max(...monthly, objectifMonthly || 0, 1);
  const barW = 22;
  const gap = 4;
  const w = (barW + gap) * 12;
  return (
    <div className="overflow-x-auto">
      <svg width={w} height={height + 22} className="block">
        {objectifMonthly > 0 && (
          <line
            x1={0} x2={w}
            y1={height - (objectifMonthly / max) * height}
            y2={height - (objectifMonthly / max) * height}
            stroke="#f43f5e" strokeDasharray="3 3" strokeWidth={1}
          />
        )}
        {monthly.map((v, i) => {
          const h = Math.max(2, (v / max) * height);
          const y = height - h;
          const x = i * (barW + gap);
          const reached = objectifMonthly > 0 && v >= objectifMonthly;
          const fill = reached ? "#10b981" : v > 0 ? "#6366f1" : "#e2e8f0";
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={h} fill={fill} rx={2} />
              <text x={x + barW / 2} y={height + 14} textAnchor="middle" fontSize="9" fill="#64748b">{MONTHS[i]}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function Progression() {
  const { user, can } = useAuth();
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/dashboard/annual?year=${year}`);
      setData(r.data);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, [year]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const h = () => load();
    window.addEventListener("kylot:sales-updated", h);
    return () => window.removeEventListener("kylot:sales-updated", h);
  }, [load]);

  const rows = useMemo(() => data?.rows || [], [data]);
  const companyMonthly = useMemo(() => data?.company_total_monthly || Array(12).fill(0), [data]);
  const companyObjAnnual = data?.company_objectif_annual || 0;
  const companyTotal = data?.company_total || 0;
  const companyProgress = companyObjAnnual > 0 ? Math.round((companyTotal / companyObjAnnual) * 100) : 0;
  const companyObjMonthly = companyObjAnnual > 0 ? companyObjAnnual / 12 : 0;

  const isCommercial = user?.role === "commercial";

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-3">
        <div>
          <p className="overline">Suivi annuel</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Progression {year}</h1>
          <p className="text-sm text-slate-500 mt-2">
            CA mensuel {isCommercial ? "personnel" : "par commercial"} — objectif matérialisé par la ligne rouge pointillée. Les barres passent au vert dès que l'objectif mensuel est atteint.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setYear(year - 1)} data-testid="progression-prev-year"><ChevronLeft size={16} /></Button>
          <div className="font-display text-lg font-semibold w-24 text-center flex items-center justify-center gap-2">
            <CalendarIcon size={16} className="text-slate-400" />{year}
          </div>
          <Button variant="outline" size="icon" onClick={() => setYear(year + 1)} data-testid="progression-next-year"><ChevronRight size={16} /></Button>
          {year !== new Date().getFullYear() && (
            <Button variant="ghost" size="sm" onClick={() => setYear(new Date().getFullYear())}>Cette année</Button>
          )}
        </div>
      </div>

      {!isCommercial && (
        <Card className="p-5 border-slate-200 shadow-sm mb-6" data-testid="progression-company">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="overline">Société · Total {year}</p>
              <p className="font-display text-4xl font-semibold tracking-tight mt-1">{fmtEur(companyTotal)}</p>
              <p className="text-sm text-slate-500 mt-1">
                Objectif annuel : <span className="font-semibold text-slate-800">{fmtEur(companyObjAnnual)}</span>
                {companyObjAnnual > 0 && (
                  <> · <span className={companyProgress >= 100 ? "text-emerald-700 font-semibold" : "text-slate-800 font-semibold"}>{companyProgress}%</span></>
                )}
              </p>
            </div>
            <div className="flex-1 min-w-[340px]">
              <AnnualChart monthly={companyMonthly} objectifMonthly={companyObjMonthly} height={70} />
            </div>
          </div>
        </Card>
      )}

      {loading && rows.length === 0 && (
        <div className="text-sm text-slate-500 flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Chargement…</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {rows.map((r) => {
          const reached = r.objectif_annual > 0 && r.total >= r.objectif_annual;
          return (
            <Card key={r.commercial} className={`p-5 border shadow-sm ${reached ? "border-emerald-300 bg-emerald-50/30" : "border-slate-200"}`} data-testid={`progression-row-${r.commercial}`}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] uppercase tracking-widest text-slate-500">{r.commercial}</p>
                  <p className="font-display text-2xl font-semibold mt-1">{fmtEur(r.total)}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Objectif annuel : <span className="font-semibold text-slate-700">{r.objectif_annual > 0 ? fmtEur(r.objectif_annual) : "—"}</span>
                    {r.objectif_annual > 0 && (
                      <> · <span className={reached ? "text-emerald-700 font-semibold" : "text-slate-700 font-semibold"}>{r.progress_pct}%</span></>
                    )}
                  </p>
                </div>
                {reached && (
                  <span className="inline-flex items-center gap-1 text-emerald-700 text-xs bg-emerald-100 border border-emerald-200 rounded-full px-2 py-1">
                    <Trophy size={12} /> Objectif atteint
                  </span>
                )}
              </div>
              <AnnualChart monthly={r.monthly} objectifMonthly={r.objectif_monthly} />
              <p className="text-[10px] text-slate-500 mt-2">
                <span className="inline-block w-2 h-2 rounded-sm bg-indigo-500 mr-1 align-middle" /> mois en cours &nbsp;·&nbsp;
                <span className="inline-block w-2 h-2 rounded-sm bg-emerald-500 mr-1 align-middle" /> objectif atteint &nbsp;·&nbsp;
                <span className="inline-block w-3 h-px bg-red-500 mr-1 align-middle" /> objectif mensuel
              </p>
            </Card>
          );
        })}
        {!loading && rows.length === 0 && (
          <p className="text-sm text-slate-500 col-span-full">Aucune vente enregistrée pour {year}.</p>
        )}
      </div>
    </div>
  );
}
