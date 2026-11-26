import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { Lock, TrendingUp, RotateCcw, Pencil } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n || 0);
const COLORS = {
  gold: "border-amber-300 bg-amber-50 text-amber-800",
  green: "border-emerald-200 bg-emerald-50 text-emerald-800",
  red: "border-red-200 bg-red-50 text-red-800",
  gray: "border-slate-200 bg-slate-50 text-slate-700",
};

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
      internal_labor_hours: data.internal_labor_hours ?? "",
      internal_labor_cost: data.breakdown?.labor_final ?? "",
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
  if (loading && !data) return <Card className="mt-5 p-4 text-sm text-slate-500">Chargement de la rentabilité…</Card>;
  if (!data?.forecast || !data?.final) return null;
  const color = COLORS[data.color] || COLORS.gray;
  const current = data.finalized ? data.final : data.forecast;

  return (
    <Card className={`mt-5 p-4 border ${color}`} data-testid="sale-profitability">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[.16em] opacity-70">Rentabilité du chantier</p>
          <p className="text-xs opacity-70 mt-1">
            {data.stage === "final" ? "Marge définitive" : data.stage === "provisional" ? "Marge provisoire" : "Marge prévisionnelle"}
            {!data.costs_complete && " · coûts incomplets"}
          </p>
        </div>
        {canEdit && (
          <Button size="sm" variant="outline" onClick={openEdit} data-testid="profitability-edit-btn"><Pencil size={12} className="mr-1" /> Coûts</Button>
        )}
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3 mt-3">
        <div>
          <p className="font-display text-3xl font-semibold" data-testid="profitability-margin">{fmt(current.margin)}</p>
          <p className="text-xs opacity-75">Marge restante</p>
        </div>
        <div className="text-right">
          <p className="font-display text-2xl font-semibold" data-testid="profitability-percent">{current.percent.toFixed(1).replace(".", ",")} %</p>
          <p className="text-xs opacity-75">du CA HT</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div className="rounded-md bg-white/60 p-2"><span className="opacity-70">Marge prévisionnelle</span><br /><b>{fmt(data.forecast.margin)} · {data.forecast.percent.toFixed(1).replace(".", ",")} %</b></div>
        <div className="rounded-md bg-white/60 p-2"><span className="opacity-70">Marge définitive</span><br /><b>{fmt(data.final.margin)} · {data.final.percent.toFixed(1).replace(".", ",")} %</b></div>
      </div>

      <div className="mt-3 text-xs space-y-1 border-t border-current/10 pt-3">
        <div className="flex justify-between"><span>Commission commercial</span><b>− {fmt(data.breakdown.commercial)}</b></div>
        <div className="flex justify-between"><span>Commission prospecteur</span><b>− {fmt(data.breakdown.prospecteur)}</b></div>
        <div className="flex justify-between"><span>Responsable prospection</span><b>− {fmt(data.breakdown.manager)}</b></div>
        <div className="flex justify-between"><span>Frais acquisition</span><b>− {fmt(data.breakdown.acquisition)}</b></div>
        <div className="flex justify-between"><span>Main-d’œuvre</span><b>− {fmt(data.breakdown.labor_final)}</b></div>
        <div className="flex justify-between"><span>Sous-traitance</span><b>− {fmt(data.breakdown.subcontract_cost)}</b></div>
        <div className="flex justify-between"><span>Matériaux</span><b>− {fmt(data.breakdown.materials_cost)}</b></div>
        <div className="flex justify-between"><span>Frais divers</span><b>− {fmt((data.breakdown.extra_costs || 0) + (data.breakdown.other_costs || 0))}</b></div>
        <div className="flex justify-between border-t border-current/20 pt-1 mt-1"><span>CA HT</span><b>{fmt(data.amount)}</b></div>
      </div>

      {data.finalized ? (
        <p className="mt-3 text-[11px] flex items-center gap-1 opacity-75"><Lock size={11} /> Marge définitive validée</p>
      ) : data.stage === "provisional" && canEdit ? (
        <Button size="sm" className="mt-3 w-full" onClick={() => save(true)} disabled={saving} data-testid="profitability-finalize-btn">
          <TrendingUp size={13} className="mr-1" /> Valider la marge définitive
        </Button>
      ) : null}
      {data.finalized && canEdit && (
        <Button size="sm" variant="outline" className="mt-2 w-full" onClick={() => save(false)} disabled={saving} data-testid="profitability-reopen-btn">
          <RotateCcw size={13} className="mr-1" /> Rouvrir la marge
        </Button>
      )}
      {!!data.history?.length && canView && (
        <details className="mt-3 text-[11px] opacity-80">
          <summary className="cursor-pointer">Historique des modifications ({data.history.length})</summary>
          <div className="mt-2 space-y-1">
            {data.history.slice(0, 5).map((h) => <div key={h.id} className="flex justify-between gap-2"><span>{h.at?.slice(0, 16).replace("T", " ")} · {h.user_name}</span><span>{h.action}</span></div>)}
          </div>
        </details>
      )}

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md" data-testid="profitability-dialog">
          <DialogHeader><DialogTitle className="font-display text-2xl">Coûts du chantier</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <div><Label>Heures main-d’œuvre</Label><Input type="number" min="0" step="0.5" value={form.internal_labor_hours ?? ""} onChange={(e) => setForm({ ...form, internal_labor_hours: e.target.value })} data-testid="profitability-hours" /></div>
            <div><Label>Coût main-d’œuvre (€)</Label><Input type="number" min="0" step="0.01" value={form.internal_labor_cost ?? ""} onChange={(e) => setForm({ ...form, internal_labor_cost: e.target.value })} data-testid="profitability-labor" /></div>
            <div><Label>Sous-traitance HT (€)</Label><Input type="number" min="0" step="0.01" value={form.subcontract_cost} onChange={(e) => setForm({ ...form, subcontract_cost: e.target.value })} data-testid="profitability-subcontract" /></div>
            <div><Label>Matériaux (€)</Label><Input type="number" min="0" step="0.01" value={form.materials_cost} onChange={(e) => setForm({ ...form, materials_cost: e.target.value })} data-testid="profitability-materials" /></div>
            <div><Label>Frais supplémentaires (€)</Label><Input type="number" min="0" step="0.01" value={form.extra_costs} onChange={(e) => setForm({ ...form, extra_costs: e.target.value })} data-testid="profitability-extra" /></div>
            <div><Label>Autres coûts (€)</Label><Input type="number" min="0" step="0.01" value={form.other_costs} onChange={(e) => setForm({ ...form, other_costs: e.target.value })} data-testid="profitability-other" /></div>
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
