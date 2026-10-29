import React, { useEffect, useState, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, CalendarOff, Clock } from "lucide-react";
import { toast } from "sonner";
import useTeam from "@/lib/useTeam";

// iter49: date locale Europe/Paris — jamais toISOString() (shift UTC -1j la nuit)
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function AbsencesDialog({ open, onOpenChange, onChanged }) {
  const { commerciaux, techniciens } = useTeam();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    person_type: "technicien",
    person_name: "",
    date_from: today(),
    date_to: today(),
    reason: "",
    all_day: true,
    start_time: "",
    end_time: "",
    note: "",
  });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/absences");
      setItems(r.data || []);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (open) load(); }, [open]);

  const peopleForType = useMemo(() => (form.person_type === "commercial" ? commerciaux : techniciens), [form.person_type, commerciaux, techniciens]);

  const submit = async () => {
    if (!form.person_name) { toast.error("Sélectionnez une personne"); return; }
    if (!form.date_from || !form.date_to) { toast.error("Dates requises"); return; }
    if (form.date_to < form.date_from) { toast.error("La date de fin doit être ≥ date de début"); return; }
    if (!form.all_day) {
      if (form.date_from !== form.date_to) { toast.error("Une absence partielle doit être sur une seule journée"); return; }
      if (!form.start_time || !form.end_time) { toast.error("Heure de début et fin requises"); return; }
      if (form.end_time <= form.start_time) { toast.error("La fin doit être après le début"); return; }
    }
    setSaving(true);
    try {
      const payload = {
        person_type: form.person_type,
        person_name: form.person_name,
        date_from: form.date_from,
        date_to: form.date_to,
        reason: form.reason,
        all_day: form.all_day,
        start_time: form.all_day ? "" : form.start_time,
        end_time: form.all_day ? "" : form.end_time,
        note: form.note,
      };
      await api.post("/absences", payload);
      toast.success("Absence enregistrée");
      setForm({ ...form, person_name: "", date_from: today(), date_to: today(), reason: "", start_time: "", end_time: "", note: "", all_day: true });
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Supprimer cette absence ?")) return;
    try {
      await api.delete(`/absences/${id}`);
      toast.success("Absence supprimée");
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const fmtRange = (a) => {
    const dateRange = a.date_from === a.date_to ? a.date_from : `${a.date_from} → ${a.date_to}`;
    if (!a.all_day && a.start_time && a.end_time) return `${dateRange} · ${a.start_time}–${a.end_time}`;
    return dateRange;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="absences-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <CalendarOff size={18} /> Absences (planning)
          </DialogTitle>
        </DialogHeader>

        <div className="mt-3 space-y-3 border border-slate-200 rounded-lg p-3 bg-slate-50/50">
          <p className="overline">Nouvelle absence</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Type</Label>
              <Select value={form.person_type} onValueChange={(v) => setForm({ ...form, person_type: v, person_name: "" })}>
                <SelectTrigger className="h-9" data-testid="abs-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="technicien">Technicien</SelectItem>
                  <SelectItem value="commercial">Commercial</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Personne</Label>
              <Select value={form.person_name || "__none"} onValueChange={(v) => setForm({ ...form, person_name: v === "__none" ? "" : v })}>
                <SelectTrigger className="h-9" data-testid="abs-name"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {peopleForType.map((p) => (<SelectItem key={p.id} value={p.name}>{p.name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Du</Label>
              <Input type="date" value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value, ...(form.all_day ? {} : { date_to: e.target.value }) })} data-testid="abs-from" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Au</Label>
              <Input type="date" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} disabled={!form.all_day} data-testid="abs-to" />
            </div>
          </div>
          {/* iter51 : bascule Journée entière + heures partielles */}
          <label className="flex items-center gap-3 cursor-pointer" data-testid="abs-allday-toggle">
            <Switch
              checked={form.all_day}
              onCheckedChange={(v) => setForm((prev) => ({
                ...prev,
                all_day: v,
                ...(v ? { start_time: "", end_time: "" } : { date_to: prev.date_from }),
              }))}
              data-testid="abs-allday"
            />
            <div>
              <p className="text-sm font-semibold text-slate-900 flex items-center gap-1.5"><Clock size={13} className="text-slate-500" /> Journée entière</p>
              <p className="text-[11px] text-slate-500">Désactivez pour saisir un créneau horaire précis (RDV, matin, après-midi…)</p>
            </div>
          </label>
          {!form.all_day && (
            <div className="grid grid-cols-2 gap-2 pl-9" data-testid="abs-times">
              <div className="space-y-1">
                <Label className="text-xs">Heure début</Label>
                <Input
                  type="time"
                  step="60"
                  value={form.start_time}
                  onChange={(e) => setForm((prev) => {
                    const v = e.target.value;
                    const nextEnd = prev.end_time && v && prev.end_time <= v ? "" : prev.end_time;
                    return { ...prev, start_time: v, end_time: nextEnd };
                  })}
                  className="h-10 text-base font-mono tabular-nums"
                  placeholder="09:00"
                  data-testid="abs-start"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Heure fin</Label>
                <Input
                  type="time"
                  step="60"
                  value={form.end_time}
                  onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                  min={form.start_time || undefined}
                  className={`h-10 text-base font-mono tabular-nums ${form.start_time && form.end_time && form.end_time <= form.start_time ? "border-red-400 focus-visible:ring-red-400" : ""}`}
                  placeholder="12:00"
                  data-testid="abs-end"
                />
              </div>
              {form.start_time && form.end_time && form.end_time <= form.start_time && (
                <p className="col-span-2 text-[11px] text-red-600 -mt-1" data-testid="abs-time-error">La fin doit être après le début.</p>
              )}
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs">Motif (court)</Label>
            <Input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Ex : Congé, Maladie, RTT, RDV médical…" data-testid="abs-reason" maxLength={80} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Note / Commentaire (optionnel)</Label>
            <Textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Ex : Retour prévu après le déjeuner…" data-testid="abs-note" />
          </div>
          <div className="flex justify-end">
            <Button size="sm" onClick={submit} disabled={saving} data-testid="abs-add-btn">
              <Plus size={14} className="mr-1" /> {saving ? "Enregistrement…" : "Ajouter"}
            </Button>
          </div>
        </div>

        <div className="mt-4 max-h-80 overflow-y-auto space-y-2">
          <p className="overline">Absences enregistrées</p>
          {loading && <p className="text-sm text-slate-500">Chargement…</p>}
          {!loading && items.length === 0 && <p className="text-sm text-slate-500">Aucune absence.</p>}
          {items.map((a) => (
            <div key={a.id} className="flex items-center justify-between border border-red-100 bg-red-50/50 rounded-md px-3 py-2" data-testid={`abs-row-${a.id}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-red-900 truncate">
                  <Badge className="bg-red-100 text-red-800 border-0 mr-2">{a.person_type}</Badge>
                  {a.person_name}
                </div>
                <div className="text-xs text-red-700/80">{fmtRange(a)}{a.reason ? ` · ${a.reason}` : ""}</div>
                {a.note && <div className="text-[11px] text-red-700/60 italic mt-0.5">« {a.note} »</div>}
              </div>
              <button onClick={() => remove(a.id)} className="text-red-500 hover:text-red-700 shrink-0" aria-label="Supprimer" data-testid={`abs-del-${a.id}`}>
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
