import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Trash2, Building2, Plus } from "lucide-react";

export default function Companies() {
  const [companies, setCompanies] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", admin_email: "", admin_password: "", admin_name: "" });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try { setCompanies((await api.get("/superadmin/companies")).data); }
    catch (err) { toast.error(formatApiError(err)); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) return toast.error("Nom d'entreprise requis");
    setSaving(true);
    try {
      await api.post("/superadmin/companies", form);
      toast.success("Entreprise créée");
      setForm({ name: "", admin_email: "", admin_password: "", admin_name: "" });
      setOpen(false);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async (c) => {
    if (!window.confirm(`Supprimer l'entreprise ${c.name} et TOUTES ses données ?`)) return;
    try {
      await api.delete(`/superadmin/companies/${c.id}`);
      toast.success("Entreprise supprimée");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div className="p-8 max-w-[1200px]">
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="overline">Super-admin</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight">Entreprises</h1>
          <p className="text-sm text-slate-500 mt-2">Chaque entreprise est totalement isolée : utilisateurs, ventes, chantiers, planning, paramètres.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-company-btn"><Plus size={14} className="mr-1" /> Nouvelle entreprise</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md" data-testid="new-company-dialog">
            <DialogHeader>
              <DialogTitle className="font-display text-2xl">Nouvelle entreprise</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div><Label>Nom de l'entreprise</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="company-name-input" /></div>
              <div className="rounded-md border border-slate-200 p-3 bg-slate-50/60 space-y-3">
                <p className="text-xs text-slate-500">Créer aussi le compte admin (optionnel)</p>
                <div><Label>Nom admin</Label><Input value={form.admin_name} onChange={(e) => setForm({ ...form, admin_name: e.target.value })} data-testid="company-admin-name" placeholder={form.name || "Nom du responsable"} /></div>
                <div><Label>Email admin</Label><Input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} data-testid="company-admin-email" /></div>
                <div><Label>Mot de passe admin</Label><Input type="password" autoComplete="new-password" value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} placeholder="16 caractères minimum" data-testid="company-admin-password" /></div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
              <Button onClick={create} disabled={saving} data-testid="company-submit-btn">Créer</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-5 py-3 overline">Entreprise</th>
                <th className="px-5 py-3 overline">ID</th>
                <th className="px-5 py-3 overline text-right">Utilisateurs</th>
                <th className="px-5 py-3 overline text-right">Ventes</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {companies.length === 0 && (<tr><td colSpan={5} className="p-6 text-center text-slate-500">Aucune entreprise.</td></tr>)}
              {companies.map((c) => (
                <tr key={c.id} className="data-row border-b border-slate-100" data-testid={`company-row-${c.id}`}>
                  <td className="px-5 py-3 font-semibold flex items-center gap-2"><Building2 size={14} className="text-slate-400" />{c.name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">{c.id}</td>
                  <td className="px-5 py-3 text-right">{c.user_count ?? 0}</td>
                  <td className="px-5 py-3 text-right">{c.sales_count ?? 0}</td>
                  <td className="px-5 py-3 text-right">
                    <Button variant="ghost" size="sm" onClick={() => remove(c)} data-testid={`company-delete-${c.id}`} aria-label="Supprimer">
                      <Trash2 size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
