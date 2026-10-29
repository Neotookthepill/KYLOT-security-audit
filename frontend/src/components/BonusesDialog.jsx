import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Plus, Trash2, Save, Pencil, X, TrendingUp, Loader2 } from "lucide-react";
import useTeam from "@/lib/useTeam";

const PERIODS = [
  { value: "month", label: "Mensuel" },
  { value: "quarter", label: "Trimestriel" },
  { value: "year", label: "Annuel" },
  { value: "all", label: "Depuis toujours" },
];

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

const EMPTY = { name: "", ca_threshold: 10000, amount: 500, period: "month", commerciaux: [], active: true, notify_reached: true, notify_near: false, near_threshold_pct: 90 };

export default function BonusesDialog({ open, onOpenChange, onChanged }) {
  const { commerciaux } = useTeam();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null); // null | "new" | id
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/bonuses");
      setItems(data || []);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (open) { load(); setEditing(null); } }, [open]);

  const startNew = () => { setForm(EMPTY); setEditing("new"); };
  const startEdit = (b) => { setForm({ ...EMPTY, ...b, commerciaux: b.commerciaux || [] }); setEditing(b.id); };
  const cancel = () => { setEditing(null); setForm(EMPTY); };

  const submit = async () => {
    const name = (form.name || "").trim();
    if (!name) { toast.error("Nom obligatoire"); return; }
    const th = parseFloat(String(form.ca_threshold).replace(",", ".")) || 0;
    const amt = parseFloat(String(form.amount).replace(",", ".")) || 0;
    if (th < 0 || amt < 0) { toast.error("Valeurs invalides"); return; }
    setSaving(true);
    try {
      const payload = {
        name,
        ca_threshold: th,
        amount: amt,
        period: form.period,
        commerciaux: form.commerciaux || [],
        active: !!form.active,
        notify_reached: !!form.notify_reached,
        notify_near: !!form.notify_near,
        near_threshold_pct: parseFloat(form.near_threshold_pct) || 90,
      };
      if (editing === "new") await api.post("/bonuses", payload);
      else await api.put(`/bonuses/${editing}`, payload);
      toast.success(editing === "new" ? "Prime créée" : "Prime enregistrée");
      cancel();
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async (b) => {
    if (!window.confirm(`Supprimer la prime « ${b.name} » ?`)) return;
    try {
      await api.delete(`/bonuses/${b.id}`);
      toast.success("Prime supprimée");
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const toggleActive = async (b) => {
    try {
      await api.put(`/bonuses/${b.id}`, { active: !b.active });
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const toggleCommercial = (name) => {
    setForm((prev) => {
      const set = new Set(prev.commerciaux || []);
      if (name === "*") return { ...prev, commerciaux: ["*"] };
      set.delete("*");
      if (set.has(name)) set.delete(name); else set.add(name);
      return { ...prev, commerciaux: Array.from(set) };
    });
  };

  const isAllSelected = (form.commerciaux || []).includes("*") || (form.commerciaux || []).length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><TrendingUp size={18} /> Primes par palier CA</DialogTitle>
          <DialogDescription>
            Configurez les paliers de CA qui déclenchent une prime pour un ou tous les commerciaux. Une prime peut être mensuelle, trimestrielle, annuelle ou globale.
          </DialogDescription>
        </DialogHeader>

        {editing === null && (
          <div className="space-y-3">
            {loading && <p className="text-xs text-slate-500 inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" />Chargement…</p>}
            {!loading && items.length === 0 && (
              <p className="text-sm text-slate-500 border border-dashed border-slate-200 rounded-lg p-4 text-center">Aucune prime configurée.</p>
            )}
            <div className="space-y-2 max-h-[45vh] overflow-y-auto pr-1">
              {items.map((b) => (
                <div key={b.id} className={`rounded-lg border p-3 flex items-start gap-3 ${b.active ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50/60"}`} data-testid={`bonus-row-${b.id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-900 truncate">{b.name}</p>
                      <span className="text-[11px] uppercase tracking-widest text-slate-500">{PERIODS.find((p) => p.value === b.period)?.label || b.period}</span>
                      {!b.active && <span className="text-[11px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-600">Désactivée</span>}
                    </div>
                    <p className="text-sm text-slate-600 mt-1">
                      À partir de <b>{fmtEur(b.ca_threshold)}</b> de CA · Prime <b className="text-emerald-700">{fmtEur(b.amount)}</b>
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {(!b.commerciaux || b.commerciaux.length === 0 || b.commerciaux.includes("*")) ? "Tous les commerciaux" : b.commerciaux.join(" · ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Switch checked={!!b.active} onCheckedChange={() => toggleActive(b)} data-testid={`bonus-toggle-${b.id}`} />
                    <Button variant="ghost" size="sm" onClick={() => startEdit(b)} data-testid={`bonus-edit-${b.id}`}><Pencil size={13} /></Button>
                    <Button variant="ghost" size="sm" onClick={() => remove(b)} className="text-red-600 hover:text-red-800" data-testid={`bonus-del-${b.id}`}><Trash2 size={13} /></Button>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end pt-2">
              <Button onClick={startNew} data-testid="bonus-add-btn"><Plus size={14} className="mr-1" /> Nouvelle prime</Button>
            </div>
          </div>
        )}

        {editing !== null && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label>Nom du palier</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex : Palier Or, Prime Argent…" data-testid="bonus-name" />
              </div>
              <div>
                <Label>Seuil CA (€)</Label>
                <Input type="number" min="0" step="500" value={form.ca_threshold} onChange={(e) => setForm({ ...form, ca_threshold: e.target.value })} data-testid="bonus-threshold" />
              </div>
              <div>
                <Label>Prime (€)</Label>
                <Input type="number" min="0" step="50" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="bonus-amount" />
              </div>
              <div>
                <Label>Période</Label>
                <Select value={form.period} onValueChange={(v) => setForm({ ...form, period: v })}>
                  <SelectTrigger data-testid="bonus-period"><SelectValue /></SelectTrigger>
                  <SelectContent>{PERIODS.map((p) => (<SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>))}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Statut</Label>
                <div className="flex items-center gap-2 h-9">
                  <Switch checked={!!form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} data-testid="bonus-active" />
                  <span className="text-sm text-slate-600">{form.active ? "Active" : "Désactivée"}</span>
                </div>
              </div>
              <div className="sm:col-span-2">
                <Label>Commerciaux concernés</Label>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  <button
                    type="button"
                    onClick={() => toggleCommercial("*")}
                    className={`px-2 py-1 rounded-full text-xs border ${isAllSelected ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 text-slate-700 hover:bg-slate-100"}`}
                    data-testid="bonus-comm-all"
                  >Tous</button>
                  {(commerciaux || []).map((c) => {
                    const active = (form.commerciaux || []).includes(c.name) && !isAllSelected;
                    return (
                      <button
                        key={c.id || c.name}
                        type="button"
                        onClick={() => toggleCommercial(c.name)}
                        className={`px-2 py-1 rounded-full text-xs border ${active ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 text-slate-700 hover:bg-slate-100"}`}
                        data-testid={`bonus-comm-${c.name}`}
                      >{c.name}</button>
                    );
                  })}
                </div>
              </div>
              <div className="sm:col-span-2 border-t border-slate-200 pt-3">
                <Label>Notifications</Label>
                <div className="mt-1 space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <Switch checked={!!form.notify_reached} onCheckedChange={(v) => setForm({ ...form, notify_reached: v })} data-testid="bonus-notif-reached" />
                    <span>Notifier quand le palier est atteint</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <Switch checked={!!form.notify_near} onCheckedChange={(v) => setForm({ ...form, notify_near: v })} data-testid="bonus-notif-near" />
                    <span>Notifier quand proche ({form.near_threshold_pct || 90}%)</span>
                  </label>
                  {form.notify_near && (
                    <div className="ml-6">
                      <Label className="text-xs">Seuil (%)</Label>
                      <Input type="number" min="1" max="100" value={form.near_threshold_pct} onChange={(e) => setForm({ ...form, near_threshold_pct: e.target.value })} className="w-24" data-testid="bonus-notif-near-pct" />
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={cancel} disabled={saving}><X size={14} className="mr-1" />Annuler</Button>
              <Button onClick={submit} disabled={saving} data-testid="bonus-save">
                {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} {editing === "new" ? "Créer" : "Enregistrer"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
