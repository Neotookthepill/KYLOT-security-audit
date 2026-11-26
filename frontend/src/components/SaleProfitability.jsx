import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { Lock, TrendingUp, RotateCcw, Pencil, ChevronDown, ShieldCheck } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n || 0);
const pct = (n) => (Number.isFinite(n) ? n : 0).toFixed(1).replace(".", ",");
const PALETTE = {
  gold: {
    card: "border-amber-300/80 bg-amber-50/80 dark:border-amber-800/60 dark:bg-amber-950/20",
    title: "text-amber-950 dark:text-amber-100", muted: "text-amber-800/80 dark:text-amber-200/75",
    chip: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100", bar: "bg-amber-500",
  },
  green: {
    card: "border-emerald-200/80 bg-emerald-50/70 dark:border-emerald-800/60 dark:bg-emerald-950/20",
    title: "text-emerald-950 dark:text-emerald-100", muted: "text-emerald-800/80 dark:text-emerald-200/75",
    chip: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100", bar: "bg-emerald-500",
  },
  red: {
    card: "border-red-200/80 bg-red-50/70 dark:border-red-800/60 dark:bg-red-950/20",
    title: "text-red-950 dark:text-red-100", muted: "text-red-800/80 dark:text-red-200/75",
    chip: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100", bar: "bg-red-500",
  },
  gray: {
    card: "border-border bg-card", title: "text-foreground", muted: "text-muted-foreground",
    chip: "bg-muted text-muted-foreground", bar: "bg-slate-400 dark:bg-slate-500",
  },
};
const STAGE = { forecast: "Prévisionnelle", provisional: "Provisoire", final: "Définitive" };

export default function SaleProfitability({ saleId }) {
  const { user, can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});

  const canView = can?.("financial", "view") || user?.role === "admin";
  const canEdit = can?.("financial", "edit") || user?.role === "admin";

  const load = React.useCallback(async () => {
    if (!saleId || !canView) return;
    setLoading(true);
    try { setData((await api.get(`/sales/${saleId}/profitability`)).data); }
    catch (err) { if (err?.response?.status !== 403) toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, [saleId, canView]);
  useEffect(() => { load(); }, [load]);

  const openEdit = () => {
    if (!data) return;
    setForm({
      internal_labor_hours: data.manual?.internal_labor_hours ?? data.internal_labor_hours ?? "",
      internal_labor_cost: data.manual?.internal_labor_cost ?? "",
      subcontract_cost: data.manual?.subcontract_cost ?? 0,
      materials_cost: data.manual?.materials_cost ?? 0,
      extra_costs: data.manual?.extra_costs ?? 0,
      other_costs: data.manual?.other_costs ?? 0,
    });
    setEditOpen(true);
  };

  const save = async (finalized) => {
    setSaving(true);
    try {
      const payload = {
        internal_labor_hours: form.internal_labor_hours === "" ? null : Number(form.internal_labor_hours),
        internal_labor_cost: form.internal_labor_cost === "" ? null : Number(form.internal_labor_cost),
        subcontract_cost: Number(form.subcontract_cost || 0),
        materials_cost: Number(form.materials_cost || 0),
        extra_costs: Number(form.extra_costs || 0),
        other_costs: Number(form.other_costs || 0),
      };
      if (finalized !== undefined) payload.finalized = finalized;
      const res = await api.put(`/sales/${saleId}/profitability`, payload);
      setData(res.data);
      setEditOpen(false);
      toast.success(finalized === true ? "Marge définitive validée" : finalized === false ? "Marge rouverte" : "Coûts enregistrés");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  if (!canView) return null;
  if (loading && !data) return <Card className="mt-5 p-4 text-sm text-muted-foreground">Chargement de la rentabilité…</Card>;
  if (!data?.forecast || !data?.final) return null;

  const p = PALETTE[data.color] || PALETTE.gray;
  const current = data.finalized ? data.final : data.forecast;
  const barWidth = Math.max(0, Math.min(100, current.percent));
  const commercialLines = [
    ["Commission commercial", data.breakdown.commercial],
    ["Commission prospecteur", data.breakdown.prospecteur],
    ["Prime prospecteur", data.breakdown.prospecteur_prime],
    ["Responsable prospection", data.breakdown.manager],
    ["Frais d’acquisition", data.breakdown.acquisition],
  ];
  const siteLines = [
    ["Main-d’œuvre", data.breakdown.labor_final],
    ["Sous-traitance", data.breakdown.subcontract_cost],
    ["Matériaux", data.breakdown.materials_cost],
    ["Frais supplémentaires", data.breakdown.extra_costs],
    ["Autres coûts", data.breakdown.other_costs],
  ];

  return (
    <Card className={`mt-5 overflow-hidden border ${p.card}`} data-testid="sale-profitability">
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className={`text-[10px] font-semibold uppercase tracking-[.16em] ${p.muted}`}>Rentabilité du chantier</p>
            <div className="flex flex-wrap items-center gap-2 mt-1.5">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${p.chip}`}>
                <ShieldCheck size={10} /> {STAGE[data.stage] || "Prévisionnelle"}
              </span>
              {!data.costs_complete && <span className={`text-[10px] ${p.muted}`}>Coûts à compléter</span>}
            </div>
          </div>
          {canEdit && (
            <Button size="sm" variant="outline" onClick={openEdit} className="shrink-0 bg-white/60 dark:bg-background/40" data-testid="profitability-edit-btn">
              <Pencil size={12} className="mr-1" /> Coûts
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-[1.2fr_1fr] gap-3 mt-4">
          <div className="min-w-0">
            <p className={`text-xs ${p.muted}`}>Marge restante</p>
            <p className={`font-display text-4xl font-semibold tracking-tight mt-0.5 ${p.title}`} data-testid="profitability-margin">{fmt(current.margin)}</p>
            <p className={`text-sm mt-1 ${p.muted}`}><b className={p.title}>{pct(current.percent)} %</b> du CA HT</p>
          </div>
          <div className="rounded-xl bg-white/55 p-3 dark:bg-background/35">
            <div className="flex items-center justify-between text-xs"><span className={p.muted}>CA HT</span><b className={p.title}>{fmt(data.amount)}</b></div>
            <div className="flex items-center justify-between text-xs mt-1"><span className={p.muted}>Coûts totaux</span><b className={p.title}>− {fmt(current.total_cost)}</b></div>
            <div className="h-2 rounded-full bg-black/10 dark:bg-white/10 mt-2.5 overflow-hidden">
              <div className={`h-full rounded-full ${p.bar} transition-[width] duration-500`} style={{ width: `${barWidth}%` }} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 mt-3">
          <div className={`rounded-lg border bg-white/55 p-3 dark:bg-background/35 ${data.finalized ? "border-border/60" : "border-current/20"}`}>
            <p className={`text-[10px] uppercase tracking-wide ${p.muted}`}>Prévisionnelle</p>
            <p className={`font-display text-xl font-semibold mt-0.5 ${p.title}`}>{fmt(data.forecast.margin)}</p>
            <p className={`text-[11px] ${p.muted}`}>{pct(data.forecast.percent)} %</p>
          </div>
          <div className={`rounded-lg border p-3 ${data.final.available ? "border-current/40 bg-white/75 dark:bg-background/55" : "border-border/50 bg-white/35 dark:bg-background/20"}`}>
            <p className={`text-[10px] uppercase tracking-wide ${p.muted}`}>Définitive</p>
            {data.final.available ? (
              <>
                <p className={`font-display text-xl font-semibold mt-0.5 ${p.title}`}>{fmt(data.final.margin)}</p>
                <p className={`text-[11px] ${p.muted}`}>{pct(data.final.percent)} %</p>
              </>
            ) : (
              <p className={`text-sm font-medium mt-1 ${p.muted}`}>En attente</p>
            )}
          </div>
        </div>

        <details className="mt-4 group">
          <summary className={`flex cursor-pointer list-none items-center justify-between gap-2 rounded-lg bg-white/45 px-3 py-2 text-xs font-medium dark:bg-background/30 ${p.title}`} data-testid="profitability-breakdown-toggle">
            <span>Détail des coûts</span>
            <ChevronDown size={14} className="transition-transform group-open:rotate-180 opacity-60" />
          </summary>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3 text-xs">
            <div>
              <p className={`text-[10px] font-semibold uppercase tracking-[.14em] mb-1.5 ${p.muted}`}>Coûts commerciaux</p>
              {commercialLines.filter(([, v]) => Number(v) > 0).map(([label, v]) => (
                <div key={label} className="flex justify-between gap-3 py-0.5"><span className={p.muted}>{label}</span><b className={p.title}>− {fmt(v)}</b></div>
              ))}
              {!commercialLines.some(([, v]) => Number(v) > 0) && <p className={p.muted}>Aucun coût commercial.</p>}
            </div>
            <div>
              <p className={`text-[10px] font-semibold uppercase tracking-[.14em] mb-1.5 ${p.muted}`}>Coûts chantier</p>
              {siteLines.filter(([, v]) => Number(v) > 0).map(([label, v]) => (
                <div key={label} className="flex justify-between gap-3 py-0.5"><span className={p.muted}>{label}</span><b className={p.title}>− {fmt(v)}</b></div>
              ))}
              {!siteLines.some(([, v]) => Number(v) > 0) && <p className={p.muted}>Aucun coût chantier.</p>}
            </div>
          </div>
        </details>

        <div className="mt-3 flex flex-wrap gap-2">
          {!data.finalized && data.stage === "provisional" && canEdit && (
            <Button size="sm" onClick={() => save(true)} disabled={saving} className="flex-1 min-w-[180px]" data-testid="profitability-finalize-btn">
              <TrendingUp size={13} className="mr-1.5" /> Valider la marge définitive
            </Button>
          )}
          {data.finalized && canEdit && (
            <Button size="sm" variant="outline" onClick={() => save(false)} disabled={saving} data-testid="profitability-reopen-btn">
              <RotateCcw size={13} className="mr-1.5" /> Rouvrir la marge
            </Button>
          )}
          {data.finalized && <span className={`inline-flex items-center gap-1 text-[11px] ${p.muted}`}><Lock size={11} /> Marge validée</span>}
        </div>

        {!!data.history?.length && (
          <details className="mt-3">
            <summary className={`cursor-pointer text-[11px] ${p.muted}`}>Historique ({data.history.length})</summary>
            <div className="mt-1 space-y-1">
              {data.history.slice(0, 5).map((h) => (
                <div key={h.id} className={`flex justify-between gap-2 text-[11px] ${p.muted}`}><span>{h.at?.slice(0, 16).replace("T", " ")} · {h.user_name}</span><span>{h.action}</span></div>
              ))}
            </div>
          </details>
        )}
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md" data-testid="profitability-dialog">
          <DialogHeader><DialogTitle className="font-display text-2xl">Coûts du chantier</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="overline mb-2">Main-d’œuvre</p>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Heures</Label><Input type="number" min="0" step="0.5" value={form.internal_labor_hours ?? ""} onChange={(e) => setForm({ ...form, internal_labor_hours: e.target.value })} data-testid="profitability-hours" /></div>
                <div>
                  <Label>Coût (€)</Label>
                  <Input type="number" min="0" step="0.01" placeholder={data.breakdown?.labor_rate ? `Auto : ${fmt(data.breakdown.labor_rate)}/h` : "Automatique"} value={form.internal_labor_cost ?? ""} onChange={(e) => setForm({ ...form, internal_labor_cost: e.target.value })} data-testid="profitability-labor" />
                  {data.breakdown?.labor_rate > 0 && <p className="mt-1 text-[10px] text-muted-foreground">{fmt(data.breakdown.labor_rate)}/h chargé · laisser vide pour calcul automatique</p>}
                </div>
              </div>
            </div>
            <div>
              <p className="overline mb-2">Coûts chantier</p>
              <div className="space-y-2">
                <div><Label>Sous-traitance HT</Label><Input type="number" min="0" step="0.01" value={form.subcontract_cost} onChange={(e) => setForm({ ...form, subcontract_cost: e.target.value })} data-testid="profitability-subcontract" /></div>
                <div><Label>Matériaux</Label><Input type="number" min="0" step="0.01" value={form.materials_cost} onChange={(e) => setForm({ ...form, materials_cost: e.target.value })} data-testid="profitability-materials" /></div>
                <div className="grid grid-cols-2 gap-2">
                  <div><Label>Frais suppl.</Label><Input type="number" min="0" step="0.01" value={form.extra_costs} onChange={(e) => setForm({ ...form, extra_costs: e.target.value })} data-testid="profitability-extra" /></div>
                  <div><Label>Autres</Label><Input type="number" min="0" step="0.01" value={form.other_costs} onChange={(e) => setForm({ ...form, other_costs: e.target.value })} data-testid="profitability-other" /></div>
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)} disabled={saving}>Annuler</Button>
            <Button onClick={() => save()} disabled={saving} data-testid="profitability-save">{saving ? "Enregistrement…" : "Enregistrer"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
