import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Sun, Trash2, Plus } from "lucide-react";
import useTeam from "@/lib/useTeam";

// iter49: date locale Europe/Paris — jamais toISOString() (shift UTC -1j la nuit)
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function OffDaysDialog({ open, onOpenChange, onChanged, month }) {
  const { commerciaux, techniciens } = useTeam();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ date: today(), date_end: "", scope: "company", person_name: "", reason: "" });
  const [saving, setSaving] = useState(false);

  const people = useMemo(() => {
    const seen = new Map();
    for (const t of techniciens || []) seen.set(t.name, { name: t.name, type: "technicien" });
    for (const c of commerciaux || []) if (!seen.has(c.name)) seen.set(c.name, { name: c.name, type: "commercial" });
    return Array.from(seen.values()).sort((a, b) => a.name.localeCompare(b.name, "fr"));
  }, [techniciens, commerciaux]);

  const load = async () => {
    setLoading(true);
    try { setItems((await api.get(`/off-days${month ? `?month=${month}` : ""}`)).data || []); }
    catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) load(); }, [open, month]);

  const submit = async () => {
    if (!form.date) return toast.error("Date requise");
    if (form.scope === "person" && !form.person_name) return toast.error("Sélectionnez une personne");
    const end = form.date_end || form.date;
    if (end < form.date) return toast.error("La date de fin doit être après la date de début");
    const dates = [];
    const [y, m, d] = form.date.split("-").map(Number);
    for (let cur = new Date(y, m - 1, d); dates.length < 366; cur.setDate(cur.getDate() + 1)) {
      const iso = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
      if (iso > end) break;
      dates.push(iso);
    }
    setSaving(true);
    try {
      let ok = 0;
      for (const date of dates) {
        try {
          await api.post("/off-days", {
            date,
            scope: form.scope,
            person_names: form.scope === "person" ? [form.person_name] : [],
            reason: form.reason,
          });
          ok++;
        } catch (err) { if (dates.length === 1) throw err; }
      }
      toast.success(`${ok} journée${ok > 1 ? "s" : ""} OFF ajoutée${ok > 1 ? "s" : ""}`);
      setForm({ ...form, reason: "", date_end: "" });
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const bulkWeekend = async (which) => {
    // which = "sat" | "sun" | "both" — creates a company OFF for every matching day in the given month
    if (!month) return toast.error("Ouvrez le mois voulu dans le planning d'abord");
    const [y, m] = month.split("-").map(Number);
    const daysInMonth = new Date(y, m, 0).getDate();
    const dates = [];
    for (let d = 1; d <= daysInMonth; d++) {
      const wd = new Date(y, m - 1, d).getDay(); // 0=Sun, 6=Sat
      if ((which === "sat" || which === "both") && wd === 6) dates.push(d);
      if ((which === "sun" || which === "both") && wd === 0) dates.push(d);
    }
    setSaving(true);
    try {
      for (const d of dates) {
        const date = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        try { await api.post("/off-days", { date, scope: "company", reason: which === "sat" ? "Samedi" : which === "sun" ? "Dimanche" : "Week-end" }); } catch (_) {}
      }
      toast.success(`${dates.length} journée${dates.length > 1 ? "s" : ""} OFF ajoutée${dates.length > 1 ? "s" : ""}`);
      await load();
      onChanged?.();
    } finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Supprimer ce jour OFF ?")) return;
    try {
      await api.delete(`/off-days/${id}`);
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="offdays-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <Sun size={18} /> Journées OFF (non travaillées)
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-3 border border-slate-200 rounded-lg p-3 bg-slate-50/50">
          <p className="overline">Ajouter</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Du</Label>
              <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="off-date" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Au (optionnel)</Label>
              <Input type="date" value={form.date_end} min={form.date} onChange={(e) => setForm({ ...form, date_end: e.target.value })} data-testid="off-date-end" />
            </div>
            <div className="space-y-1 col-span-2">
              <Label className="text-xs">Portée</Label>
              <Select value={form.scope} onValueChange={(v) => setForm({ ...form, scope: v, person_name: "" })}>
                <SelectTrigger className="h-9" data-testid="off-scope"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="company">Toute la société</SelectItem>
                  <SelectItem value="person">Une personne</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {form.scope === "person" && (
            <div className="space-y-1">
              <Label className="text-xs">Personne</Label>
              <Select value={form.person_name || "__none"} onValueChange={(v) => setForm({ ...form, person_name: v === "__none" ? "" : v })}>
                <SelectTrigger className="h-9" data-testid="off-person"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {people.map((p) => (<SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs">Motif (optionnel)</Label>
            <Input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Vacances, Férié, Pont, RTT…" data-testid="off-reason" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={submit} disabled={saving} data-testid="off-add"><Plus size={13} className="mr-1" /> Ajouter</Button>
            {month && (
              <>
                <Button size="sm" variant="outline" onClick={() => bulkWeekend("sat")} disabled={saving}>+ Tous les samedis du mois</Button>
                <Button size="sm" variant="outline" onClick={() => bulkWeekend("sun")} disabled={saving}>+ Tous les dimanches</Button>
                <Button size="sm" variant="outline" onClick={() => bulkWeekend("both")} disabled={saving}>+ Week-ends</Button>
              </>
            )}
          </div>
        </div>

        <div className="mt-4 max-h-72 overflow-y-auto space-y-2">
          <p className="overline">Journées enregistrées{month ? ` — ${month}` : ""}</p>
          {loading && <p className="text-sm text-slate-500">Chargement…</p>}
          {!loading && items.length === 0 && <p className="text-sm text-slate-500">Aucun jour OFF.</p>}
          {items.map((o) => (
            <div key={o.id} className="flex items-center justify-between border border-slate-200 bg-white rounded-md px-3 py-2" data-testid={`off-row-${o.id}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-900 truncate flex items-center gap-2">
                  <Badge className={`border-0 ${o.scope === "company" ? "bg-slate-100 text-slate-700" : "bg-indigo-50 text-indigo-800"}`}>
                    {o.scope === "company" ? "Société" : (o.person_names || []).join(", ")}
                  </Badge>
                  {o.date}
                </div>
                {o.reason && <div className="text-xs text-slate-500 mt-0.5">{o.reason}</div>}
              </div>
              <button onClick={() => remove(o.id)} className="text-slate-400 hover:text-red-600" aria-label="Supprimer" data-testid={`off-del-${o.id}`}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

        <DialogFooter className="mt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
