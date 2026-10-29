import React, { useEffect, useMemo, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, Trash2, Plus, Check, Search, Camera, Image as ImageIcon, X } from "lucide-react";
import { toast } from "sonner";
import useTeam from "@/lib/useTeam";
import ZoomableImage from "@/components/ZoomableImage";

// iter49: date locale Europe/Paris — jamais toISOString() (shift UTC -1j la nuit)
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// iter179 : compression photo mobile (long side 1600px, jpeg 0.8) — évite d'envoyer 5 Mo depuis iPhone
const compressImage = (file) => new Promise((resolve) => {
  if (!file.type?.startsWith("image/")) return resolve(null);
  const img = new Image();
  const reader = new FileReader();
  reader.onload = (e) => { img.src = e.target.result; };
  img.onload = () => {
    try {
      const MAX = 1600;
      let { width, height } = img;
      if (Math.max(width, height) > MAX) {
        const r = MAX / Math.max(width, height);
        width = Math.round(width * r); height = Math.round(height * r);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width; canvas.height = height;
      canvas.getContext("2d").drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL("image/jpeg", 0.8));
    } catch (_) { resolve(null); }
  };
  img.onerror = () => resolve(null);
  reader.onerror = () => resolve(null);
  reader.readAsDataURL(file);
});

/**
 * ReinterventionDialog.
 * If `client` is passed → single-client mode (add from a client fiche).
 * If `client` is null → global mode (planning page): pick a client too.
 */
export default function ReinterventionDialog({ open, onOpenChange, client, onChanged }) {
  const { techniciens, sousTraitants } = useTeam();
  // iter149 : sous-traitants sélectionnables dans les réinterventions (même logique que iter140)
  const assignables = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const t of (techniciens || [])) {
      const k = (t.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...t, _kind: "technicien" }); }
    }
    for (const s of (sousTraitants || [])) {
      const k = (s.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...s, _kind: "sous_traitant" }); }
    }
    return out;
  }, [techniciens, sousTraitants]);
  const [items, setItems] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ client_id: client?.id || "", technician_name: "", scheduled_date: today(), scheduled_time: "", note: "" });
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  // iter179 : photos jointes à la nouvelle réintervention (data URIs base64)
  const [photos, setPhotos] = useState([]);
  const cameraRef = useRef(null);
  const filesRef = useRef(null);
  const [previewPhoto, setPreviewPhoto] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const url = client ? `/reinterventions?client_id=${client.id}` : `/reinterventions`;
      setItems((await api.get(url)).data || []);
      if (!client) setClients((await api.get("/clients")).data || []);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) { setForm({ client_id: client?.id || "", technician_name: "", scheduled_date: today(), scheduled_time: "", note: "" }); setPhotos([]); load(); } }, [open, client?.id]);

  const onPhotosSelected = async (fs) => {
    if (!fs || !fs.length) return;
    const arr = Array.from(fs).slice(0, 6);
    const compressed = await Promise.all(arr.map((f) => compressImage(f)));
    const valid = compressed.filter(Boolean);
    if (valid.length === 0) { toast.error("Impossible de lire les photos."); return; }
    setPhotos((prev) => [...prev, ...valid].slice(0, 8));
  };
  const removePhoto = (i) => setPhotos((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!form.client_id) return toast.error("Client requis");
    if (!form.scheduled_date) return toast.error("Date requise");
    setSaving(true);
    try {
      await api.post("/reinterventions", { ...form, photos });
      toast.success("Réintervention ajoutée");
      setForm({ client_id: client?.id || "", technician_name: "", scheduled_date: today(), scheduled_time: "", note: "" });
      setPhotos([]);
      await load();
      onChanged?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Supprimer cette réintervention ?")) return;
    try { await api.delete(`/reinterventions/${id}`); await load(); onChanged?.(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const toggleStatus = async (r) => {
    const next = r.status === "terminee" ? "a_faire" : "terminee";
    try { await api.put(`/reinterventions/${r.id}`, { status: next }); await load(); onChanged?.(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const filteredClients = useMemo(() => {
    const t = q.trim().toLowerCase();
    return !t ? clients.slice(0, 40) : clients.filter((c) => `${c.name} ${c.phone||""} ${c.city||""}`.toLowerCase().includes(t)).slice(0, 40);
  }, [clients, q]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="reinter-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <RefreshCw size={18} className="text-orange-600" />
            Réinterventions{client ? ` — ${client.name}` : ""}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-3 border border-orange-100 rounded-lg p-3 bg-orange-50/40">
          <p className="overline">Nouvelle réintervention</p>
          {!client && (
            <div className="space-y-1">
              <Label className="text-xs">Client</Label>
              <div className="relative">
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un client…" className="pl-7 h-9" />
              </div>
              <Select value={form.client_id || "__none"} onValueChange={(v) => setForm({ ...form, client_id: v === "__none" ? "" : v })}>
                <SelectTrigger className="h-9" data-testid="reinter-client"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {filteredClients.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}{c.city ? ` · ${c.city}` : ""}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Date</Label>
              <Input type="date" value={form.scheduled_date} onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })} data-testid="reinter-date" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Heure</Label>
              <Input type="time" value={form.scheduled_time} onChange={(e) => setForm({ ...form, scheduled_time: e.target.value })} data-testid="reinter-time" />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Technicien ou sous-traitant</Label>
            <Select value={form.technician_name || "__none"} onValueChange={(v) => setForm({ ...form, technician_name: v === "__none" ? "" : v })}>
              <SelectTrigger className="h-9" data-testid="reinter-tech"><SelectValue placeholder="Choisir…" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">—</SelectItem>
                {assignables.map((t) => (
                  <SelectItem key={t.id} value={t.name}>
                    {t.name}{t._kind === "sous_traitant" ? " · S/T" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Motif / note</Label>
            <Textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Ex : reprise étanchéité, réglage VMC, remplacement pièce, contrôle SAV…" data-testid="reinter-note" />
          </div>
          {/* iter179 — Photos jointes (avant / après / preuve) */}
          <div className="space-y-1">
            <Label className="text-xs">Photos (facultatif, max 8)</Label>
            <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => { onPhotosSelected(e.target.files); e.target.value = ""; }} data-testid="reinter-camera-input" />
            <input ref={filesRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { onPhotosSelected(e.target.files); e.target.value = ""; }} data-testid="reinter-files-input" />
            <div className="flex flex-wrap gap-2 items-center">
              <Button type="button" size="sm" variant="outline" onClick={() => cameraRef.current?.click()} data-testid="reinter-camera-btn"><Camera size={13} className="mr-1" /> Prendre</Button>
              <Button type="button" size="sm" variant="outline" onClick={() => filesRef.current?.click()} data-testid="reinter-attach-btn"><ImageIcon size={13} className="mr-1" /> Galerie</Button>
              {photos.map((p, i) => (
                <div key={i} className="relative">
                  <img src={p} alt={`photo-${i}`} className="h-14 w-14 object-cover rounded-md border border-slate-200 cursor-zoom-in" onClick={() => setPreviewPhoto(p)} data-testid={`reinter-photo-thumb-${i}`} />
                  <button type="button" onClick={() => removePhoto(i)} className="absolute -top-1 -right-1 bg-white rounded-full border border-slate-200 shadow-sm p-0.5" aria-label="Retirer" data-testid={`reinter-photo-remove-${i}`}>
                    <X size={10} className="text-red-600" />
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end">
            <Button size="sm" onClick={submit} disabled={saving} data-testid="reinter-add"><Plus size={13} className="mr-1" />{saving ? "Enregistrement…" : "Ajouter"}</Button>
          </div>
        </div>

        <div className="mt-4 max-h-72 overflow-y-auto space-y-2">
          <p className="overline">Historique{client ? " du client" : ""}</p>
          {loading && <p className="text-sm text-slate-500">Chargement…</p>}
          {!loading && items.length === 0 && <p className="text-sm text-slate-500">Aucune réintervention.</p>}
          {items.map((r) => (
            <div key={r.id} className="flex items-center justify-between border border-slate-200 bg-white rounded-md px-3 py-2" data-testid={`reinter-row-${r.id}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-slate-900 flex items-center gap-2 flex-wrap">
                  <Badge className={`border-0 ${r.status === "terminee" ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"}`}>
                    {r.status === "terminee" ? "Terminée" : "À faire"}
                  </Badge>
                  <span>{r.scheduled_date}{r.scheduled_time ? ` · ${r.scheduled_time}` : ""}</span>
                  {r.technician_name && <span className="text-slate-500 text-xs">→ {r.technician_name}</span>}
                </div>
                {!client && r.client_name && <div className="text-xs text-slate-600 mt-0.5">{r.client_name}</div>}
                {r.note && <div className="text-xs text-slate-500 mt-0.5">{r.note}</div>}
                {Array.isArray(r.photos) && r.photos.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1" data-testid={`reinter-photos-${r.id}`}>
                    {r.photos.map((p, i) => (
                      <img key={i} src={p} alt={`p-${i}`} className="h-10 w-10 object-cover rounded border border-slate-200 cursor-zoom-in" onClick={() => setPreviewPhoto(p)} data-testid={`reinter-photo-${r.id}-${i}`} />
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => toggleStatus(r)} className="text-slate-400 hover:text-emerald-700" title={r.status === "terminee" ? "Repasser À faire" : "Marquer terminée"} data-testid={`reinter-toggle-${r.id}`}>
                  <Check size={14} />
                </button>
                <button onClick={() => remove(r.id)} className="text-slate-400 hover:text-red-600" aria-label="Supprimer" data-testid={`reinter-del-${r.id}`}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* iter201 — Lightbox photo avec ZOOM (roulette, double-clic, pinch, +/-, drag) */}
        {previewPhoto && (
          <ZoomableImage src={previewPhoto} onClose={() => setPreviewPhoto(null)} testid="reinter-photo-preview" />
        )}

        <DialogFooter className="mt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
