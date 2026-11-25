import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const empty = { name: "", phone: "", email: "", address: "", postal_code: "", city: "", notes: "" };

export default function ClientEditDialog({ client, clientId, open, onOpenChange, onSaved, canEdit = true }) {
  const id = client?.id || clientId;
  const [form, setForm] = useState(empty);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !id) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/clients?client_id=${encodeURIComponent(id)}&limit=1`)
      .then(({ data }) => {
        if (cancelled) return;
        const c = data?.[0] || client || {};
        setForm({
          name: c.name || "",
          phone: c.phone || "",
          email: c.email || "",
          address: c.address || "",
          postal_code: c.postal_code || "",
          city: c.city || "",
          notes: c.notes || "",
        });
      })
      .catch((err) => { if (!cancelled) toast.error(formatApiError(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // Le client peut être un objet partiel (fiche chantier) : l'id suffit,
    // la fiche complète est toujours relue depuis l'API.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, id]);

  const save = async () => {
    if (!canEdit) return;
    if (!form.name.trim()) return toast.error("Nom requis");
    setSaving(true);
    try {
      const { data } = await api.put(`/clients/${id}`, form);
      toast.success("Coordonnées mises à jour");
      onSaved?.(data);
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (!id) return null;
  return (
    <Dialog open={open} onOpenChange={(v) => !saving && onOpenChange(v)}>
      <DialogContent className="sm:max-w-md" data-testid="client-edit-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Modifier les coordonnées</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {loading ? <p className="py-6 text-center text-sm text-slate-500">Chargement…</p> : (
            <>
              <div><Label htmlFor="client-edit-name">Nom / Prénom</Label><Input id="client-edit-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="client-edit-name" /></div>
              <div><Label htmlFor="client-edit-phone">Téléphone</Label><Input id="client-edit-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="client-edit-phone" /></div>
              <div><Label htmlFor="client-edit-email">Email</Label><Input id="client-edit-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="client-edit-email" /></div>
              <div><Label htmlFor="client-edit-address">Adresse</Label><Input id="client-edit-address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="client-edit-address" /></div>
              <div className="grid grid-cols-[120px_1fr] gap-2">
                <div><Label htmlFor="client-edit-postal">Code postal</Label><Input id="client-edit-postal" value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} data-testid="client-edit-postal" /></div>
                <div><Label htmlFor="client-edit-city">Ville</Label><Input id="client-edit-city" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} data-testid="client-edit-city" /></div>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
          <Button onClick={save} disabled={saving || loading || !canEdit} data-testid="client-edit-save">{saving ? "Enregistrement…" : "Enregistrer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
