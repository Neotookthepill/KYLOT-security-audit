import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Sparkles, Trash2, Users as UsersIcon } from "lucide-react";
import { toast } from "sonner";

// iter49: date locale Europe/Paris — jamais toISOString() (shift UTC -1j la nuit)
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/**
 * Create / edit / delete a company event on the planning.
 * Distinct from projects (chantiers) and absences — has its own visual style.
 */
export default function EventDialog({ open, onOpenChange, event, onSaved, defaultDate }) {
  const isEdit = !!event?.id;
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({
    title: "",
    date: defaultDate || today(),
    start_time: "",
    end_time: "",
    description: "",
    all_company: false,
    participants: [],
    show_on_dashboard: false,
    send_notification: false,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/users").then((r) => setUsers(r.data || [])).catch(() => setUsers([]));
    if (event) {
      setForm({
        title: event.title || "",
        date: event.date || today(),
        start_time: event.start_time || "",
        end_time: event.end_time || "",
        description: event.description || "",
        all_company: !!event.all_company,
        participants: Array.isArray(event.participants) ? event.participants : [],
        show_on_dashboard: !!event.show_on_dashboard,
        send_notification: false,
      });
    } else {
      setForm({
        title: "", date: defaultDate || today(), start_time: "", end_time: "",
        description: "", all_company: false, participants: [], show_on_dashboard: false, send_notification: false,
      });
    }
  }, [open, event, defaultDate]);

  const toggleParticipant = (uid) => {
    setForm((prev) => ({
      ...prev,
      participants: prev.participants.includes(uid) ? prev.participants.filter((x) => x !== uid) : [...prev.participants, uid],
    }));
  };

  const submit = async () => {
    if (!form.title.trim()) return toast.error("Titre requis");
    if (!form.date) return toast.error("Date requise");
    // iter50: validation "fin >= début" quand les deux sont saisis
    if (form.start_time && form.end_time && form.end_time < form.start_time) {
      return toast.error("L'heure de fin doit être postérieure à l'heure de début.");
    }
    if (!form.all_company && form.participants.length === 0) return toast.error("Sélectionnez au moins 1 participant ou cochez « Toute la société »");
    setSaving(true);
    try {
      if (isEdit) {
        await api.put(`/events/${event.id}`, form);
        toast.success("Événement mis à jour");
      } else {
        await api.post("/events", form);
        toast.success("Événement créé");
      }
      onSaved?.();
      onOpenChange(false);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    if (!isEdit) return;
    if (!window.confirm("Supprimer cet événement ?")) return;
    try {
      const notify = form.send_notification ? "?notify=true" : "";
      await api.delete(`/events/${event.id}${notify}`);
      toast.success("Événement supprimé");
      onSaved?.();
      onOpenChange(false);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const sortedUsers = useMemo(
    () => [...users].filter((u) => u.role !== "super_admin").sort((a, b) => (a.name || "").localeCompare(b.name || "", "fr")),
    [users]
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="event-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <Sparkles size={18} className="text-violet-500" />
            {isEdit ? "Modifier l'événement" : "Nouvel événement"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Titre</Label>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Repas de fin d'année, réunion mensuelle…" data-testid="event-title" />
          </div>

          {/* iter50 : layout séparé date / horaires — colonnes plus larges + saisie clavier possible */}
          <div className="space-y-1">
            <Label className="text-xs">Date</Label>
            <Input
              type="date"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
              className="w-full h-10 text-base"
              data-testid="event-date"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Début</Label>
              <Input
                type="time"
                value={form.start_time || ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm((prev) => {
                    // Si l'heure de fin devient antérieure au début, on la remet à vide
                    const nextEnd = prev.end_time && v && prev.end_time < v ? "" : prev.end_time;
                    return { ...prev, start_time: v, end_time: nextEnd };
                  });
                }}
                step="60"
                className="w-full h-10 text-base font-mono tabular-nums tracking-tight"
                data-testid="event-start"
                placeholder="12:30"
                aria-label="Heure de début"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Fin</Label>
              <Input
                type="time"
                value={form.end_time || ""}
                onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                step="60"
                min={form.start_time || undefined}
                className={`w-full h-10 text-base font-mono tabular-nums tracking-tight ${form.start_time && form.end_time && form.end_time < form.start_time ? "border-red-400 focus-visible:ring-red-400" : ""}`}
                data-testid="event-end"
                placeholder="15:00"
                aria-label="Heure de fin"
              />
              {form.start_time && form.end_time && form.end_time < form.start_time && (
                <p className="text-[11px] text-red-600 mt-0.5" data-testid="event-time-error">La fin doit être après le début.</p>
              )}
            </div>
          </div>

          <div className="space-y-1">
            <Label>Description</Label>
            <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Note ou détails…" data-testid="event-desc" />
          </div>

          <div className="rounded-lg border border-slate-200 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-900 flex items-center gap-1.5"><UsersIcon size={13} /> Participants</p>
                <p className="text-xs text-slate-500">Seules ces personnes verront l'événement.</p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={form.all_company} onCheckedChange={(v) => setForm({ ...form, all_company: v })} data-testid="event-all-company" />
                Toute la société
              </label>
            </div>
            {!form.all_company && (
              <div className="max-h-40 overflow-y-auto rounded-md border border-slate-100 p-2 space-y-1">
                {sortedUsers.length === 0 && <p className="text-xs text-slate-500">Aucun utilisateur.</p>}
                {sortedUsers.map((u) => (
                  <label key={u.id} className="flex items-center gap-2 py-1 cursor-pointer text-sm" data-testid={`event-part-${u.id}`}>
                    <input
                      type="checkbox"
                      checked={form.participants.includes(u.id)}
                      onChange={() => toggleParticipant(u.id)}
                      className="rounded border-slate-300"
                    />
                    <span className="flex-1 truncate">{u.name}</span>
                    <Badge className="bg-slate-100 text-slate-600 border-0 text-[10px]">{u.role}</Badge>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 p-3 space-y-2">
            <label className="flex items-center gap-3 cursor-pointer" data-testid="event-notif-toggle">
              <Switch checked={form.send_notification} onCheckedChange={(v) => setForm({ ...form, send_notification: v })} />
              <div>
                <p className="text-sm font-semibold text-slate-900">Envoyer une notification</p>
                <p className="text-xs text-slate-500">Seuls les participants reçoivent la notification (création, modification ou annulation).</p>
              </div>
            </label>
            <label className="flex items-center gap-3 cursor-pointer" data-testid="event-dashboard-toggle">
              <Switch checked={form.show_on_dashboard} onCheckedChange={(v) => setForm({ ...form, show_on_dashboard: v })} />
              <div>
                <p className="text-sm font-semibold text-slate-900">Afficher sur le tableau de bord</p>
                <p className="text-xs text-slate-500">Ajoute l'événement dans « Événements à venir » chez les participants.</p>
              </div>
            </label>
          </div>
        </div>

        <DialogFooter className="mt-2 flex justify-between sm:justify-between gap-2">
          <div>
            {isEdit && (
              <Button variant="outline" onClick={remove} className="border-red-200 text-red-700 hover:bg-red-50" data-testid="event-delete">
                <Trash2 size={13} className="mr-1" /> Supprimer
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
            <Button onClick={submit} disabled={saving} data-testid="event-save">
              {saving ? "Enregistrement…" : isEdit ? "Enregistrer" : "Créer"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
