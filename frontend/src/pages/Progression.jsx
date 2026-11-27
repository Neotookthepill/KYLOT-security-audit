import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, TrendingUp, Trophy, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"];
const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

function AnnualChart({ monthly, objectifMonthly, year, height = 90 }) {
  const [active, setActive] = useState(null);
  const wrapRef = useRef(null);
  const [chartWidth, setChartWidth] = useState(312);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const measure = () => setChartWidth(Math.max(250, Math.round(el.clientWidth)));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const max = Math.max(...monthly, objectifMonthly || 0, 1);
  const gap = 4;
  const barW = Math.max(12, (chartWidth - gap * 11) / 12);
  const w = (barW + gap) * 12;
  const activeMonth = active === null ? null : active;
  const activeValue = activeMonth === null ? 0 : Number(monthly[activeMonth] || 0);
  const activeGoal = activeMonth === null ? 0 : Number(objectifMonthly || 0);
  const leftPct = activeMonth === null ? 0 : ((activeMonth * (barW + gap) + barW / 2) / w) * 100;
  const tooltipStyle = leftPct < 28
    ? { left: 0, transform: "none" }
    : leftPct > 72
      ? { right: 0, left: "auto", transform: "none" }
      : { left: `${leftPct}%` };

  return (
    <div className="relative w-full pb-1" ref={wrapRef}>
      {activeMonth !== null && (
        <div
          className="qy-chart-tooltip"
          style={tooltipStyle}
          role="status"
          data-testid={`annual-tooltip-${activeMonth}`}
        >
          <div className="font-semibold">{MONTHS[activeMonth]} {year}</div>
          <div>CA réalisé : <b>{fmtEur(activeValue)}</b></div>
          <div>Objectif mensuel : <b>{activeGoal > 0 ? fmtEur(activeGoal) : "—"}</b></div>
        </div>
      )}
      <div className="w-full overflow-hidden" tabIndex={0} role="region" aria-label="Graphique annuel du chiffre d’affaires">
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
              <rect
                x={x} y={y} width={barW} height={h} fill={fill} rx={2}
                className="qy-annual-bar"
                tabIndex={0}
                role="button"
                aria-label={`${MONTHS[i]} ${year}, ${fmtEur(v)}, objectif ${objectifMonthly > 0 ? fmtEur(objectifMonthly) : "non défini"}`}
                data-testid={`annual-bar-${i}`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                style={{ cursor: "pointer", outline: "none" }}
              />
              <text x={x + barW / 2} y={height + 14} textAnchor="middle" fontSize="9" fill="#64748b">{MONTHS[i]}</text>
            </g>
          );
        })}
      </svg>
      </div>
      {activeMonth !== null && (
        <div className="qy-chart-tooltip-mobile" role="status" data-testid={`annual-tooltip-mobile-${activeMonth}`}>
          <div className="font-semibold">{MONTHS[activeMonth]} {year}</div>
          <div>CA réalisé : <b>{fmtEur(activeValue)}</b></div>
          <div>Objectif mensuel : <b>{activeGoal > 0 ? fmtEur(activeGoal) : "—"}</b></div>
        </div>
      )}
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
            CA mensuel {isCommercial ? "personnel" : "par commercial"} · ligne rouge = objectif mensuel · vert = objectif atteint.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setYear(year - 1)} data-testid="progression-prev-year" aria-label="Année précédente"><ChevronLeft size={16} /></Button>
          <div className="font-display text-lg font-semibold w-24 text-center flex items-center justify-center gap-2">
            <CalendarIcon size={16} className="text-slate-400" />{year}
          </div>
          <Button variant="outline" size="icon" onClick={() => setYear(year + 1)} data-testid="progression-next-year" aria-label="Année suivante"><ChevronRight size={16} /></Button>
          {year !== new Date().getFullYear() && (
            <Button variant="ghost" size="sm" onClick={() => setYear(new Date().getFullYear())}>Cette année</Button>
          )}
        </div>
      </div>

      {!isCommercial && (
        <Card className="p-4 sm:p-5 border-slate-200 shadow-sm mb-4" data-testid="progression-company">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:flex-wrap">
            <div>
              <p className="overline">Société · Total {year}</p>
              <p className="font-display text-4xl font-semibold tracking-tight mt-1">{fmtEur(companyTotal)}</p>
              <p className="text-sm text-slate-500 mt-1">
                Objectif annuel : <span className="font-semibold text-slate-800">{fmtEur(companyObjAnnual)}</span>
                {companyObjAnnual > 0 && (
                  <> · <span className={companyProgress >= 100 ? "text-emerald-700 font-semibold" : "text-slate-800 font-semibold"}>{companyProgress}%</span></>
                )}
              </p>
              {companyObjAnnual > 0 && (
                <div className="mt-2 h-1.5 max-w-[320px] overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${companyProgress >= 100 ? "bg-gradient-to-r from-emerald-500 to-teal-400" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`} style={{ width: `${Math.min(100, companyProgress)}%` }} />
                </div>
              )}
            </div>
            <div className="w-full min-w-0 sm:flex-1">
              <AnnualChart monthly={companyMonthly} objectifMonthly={companyObjMonthly} year={year} height={58} />
            </div>
          </div>
        </Card>
      )}

      {loading && rows.length === 0 && (
        <div className="text-sm text-slate-500 flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Chargement…</div>
      )}

      {rows.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-500 mb-2">
          <span><span className="inline-block w-2 h-2 rounded-sm bg-indigo-500 mr-1 align-middle" />mois en cours</span>
          <span><span className="inline-block w-2 h-2 rounded-sm bg-emerald-500 mr-1 align-middle" />objectif atteint</span>
          <span><span className="inline-block w-3 h-px bg-red-500 mr-1 align-middle" />objectif mensuel</span>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {rows.map((r) => {
          const reached = r.objectif_annual > 0 && r.total >= r.objectif_annual;
          return (
            <Card key={r.commercial} className={`group relative overflow-hidden p-4 border shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${reached ? "border-emerald-300 bg-gradient-to-br from-emerald-50/80 to-white" : "border-slate-200 bg-white"}`} data-testid={`progression-row-${r.commercial}`}>
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] uppercase tracking-widest text-slate-500">{r.commercial}</p>
                  <p className="font-display text-[28px] leading-none font-semibold mt-1 tracking-tight">{fmtEur(r.total)}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Objectif annuel : <span className="font-semibold text-slate-700">{r.objectif_annual > 0 ? fmtEur(r.objectif_annual) : "—"}</span>
                    {r.objectif_annual > 0 && (
                      <> · <span className={reached ? "text-emerald-700 font-semibold" : "text-slate-700 font-semibold"}>{r.progress_pct}% de l’objectif</span></>
                    )}
                  </p>
                  {r.objectif_annual > 0 && (
                    <div className="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                      <div className={`h-full rounded-full ${reached ? "bg-gradient-to-r from-emerald-500 to-teal-400" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`} style={{ width: `${Math.min(100, r.progress_pct)}%` }} />
                    </div>
                  )}
                </div>
                {reached && (
                  <span className="inline-flex items-center gap-1 text-emerald-700 text-xs bg-emerald-100 border border-emerald-200 rounded-full px-2 py-1">
                    <Trophy size={12} /> Objectif atteint
                  </span>
                )}
              </div>
              <AnnualChart monthly={r.monthly} objectifMonthly={r.objectif_monthly} year={year} height={66} />
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
