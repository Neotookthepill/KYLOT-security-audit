import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Trash2, KeyRound, Shield } from "lucide-react";
import TeamSection from "@/components/TeamSection";
import PermissionsDialog from "@/components/PermissionsDialog";
import { ROLE_LABELS } from "@/lib/permissions";

const roleMeta = {
  admin: { label: "Admin", cls: "bg-slate-900 text-white" },
  responsable: { label: "Responsable", cls: "bg-indigo-100 text-indigo-800" },
  commercial: { label: "Commercial", cls: "bg-blue-100 text-blue-800" },
  technicien: { label: "Technicien", cls: "bg-emerald-100 text-emerald-800" },
  sous_traitant: { label: "Sous-traitant", cls: "bg-teal-100 text-teal-800" },
  comptable: { label: "Comptable", cls: "bg-amber-100 text-amber-800" },
  prospecteur: { label: "Prospecteur", cls: "bg-rose-100 text-rose-800" },
  responsable_prospecteur: { label: "Responsable prospecteur", cls: "bg-pink-100 text-pink-800" },
};

export default function Users() {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "technicien" });
  const [pwEditing, setPwEditing] = useState(null);
  const [newPw, setNewPw] = useState("");
  const [permsEditing, setPermsEditing] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/users");
      setUsers(Array.isArray(r.data) ? r.data : []);
    } catch (err) {
      setUsers([]);
      toast.error(formatApiError(err));
    }
  };
  useEffect(() => { load(); }, []);
  // iter92 : sync avec TeamSection (Sous-traitants ajoutés depuis le bloc)
  useEffect(() => {
    const h = () => load();
    window.addEventListener("kylot:team-updated", h);
    return () => window.removeEventListener("kylot:team-updated", h);
  }, []);

  const notifyTeamSync = () => window.dispatchEvent(new CustomEvent("kylot:team-updated"));

  const create = async () => {
    try {
      if (!form.name || !form.email || !form.password) return toast.error("Tous les champs sont requis");
      await api.post("/users", form);
      toast.success("Utilisateur créé");
      setForm({ name: "", email: "", password: "", role: "technicien" });
      setOpen(false);
      load();
      notifyTeamSync();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const remove = async (uid) => {
    if (!window.confirm("Supprimer cet utilisateur ?")) return;
    try {
      await api.delete(`/users/${uid}`);
      toast.success("Utilisateur supprimé");
      load();
      notifyTeamSync();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const changeRole = async (uid, role) => {
    try {
      await api.put(`/users/${uid}`, { role });
      toast.success("Rôle mis à jour");
      load();
      notifyTeamSync();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const savePassword = async () => {
    try {
      await api.put(`/users/${pwEditing.id}`, { password: newPw });
      toast.success("Mot de passe modifié");
      setPwEditing(null);
      setNewPw("");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div className="p-4 md:p-8 max-w-[1200px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div>
          <p className="overline">Gestion des accès</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Utilisateurs & permissions</h1>
          <p className="text-sm text-slate-500 mt-2">Créez des comptes et personnalisez précisément les droits de chaque utilisateur.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-user-btn">+ Nouvel utilisateur</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md" data-testid="new-user-dialog">
            <DialogHeader><DialogTitle className="font-display text-2xl">Nouvel utilisateur</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label>Nom complet</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" /></div>
              <div><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" /></div>
              <div><Label>Mot de passe</Label><Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="user-password-input" placeholder="12 caractères minimum" /></div>
              <div>
                <Label>Rôle</Label>
                <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                  <SelectTrigger data-testid="user-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin — accès complet</SelectItem>
                    <SelectItem value="responsable">Responsable — équipes, planning, chantiers</SelectItem>
                    <SelectItem value="commercial">Commercial — ses ventes et clients uniquement</SelectItem>
                    <SelectItem value="technicien">Technicien — ses chantiers + heures sup</SelectItem>
                    <SelectItem value="sous_traitant">Sous-traitant — Chantiers &amp; Planning uniquement</SelectItem>
                    <SelectItem value="comptable">Comptable — Commissions + rapports</SelectItem>
                    <SelectItem value="prospecteur">Prospecteur — ses clients prospectés (lecture seule)</SelectItem>
                    <SelectItem value="responsable_prospecteur">Responsable prospecteur — tous les prospecteurs + CA</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-slate-500 mt-1.5">Le rôle définit les droits par défaut, vous pourrez ensuite les personnaliser via le bouton bouclier.</p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
              <Button onClick={create} data-testid="user-submit-btn">Créer</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-5 py-3 overline">Nom</th>
                <th className="px-5 py-3 overline">Email</th>
                <th className="px-5 py-3 overline">Rôle</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(Array.isArray(users) ? users : []).map((u) => {
                if (!u || !u.id) return null;
                const uName = u.name || "(sans nom)";
                const uEmail = u.email || "";
                const uRole = u.role || "commercial";
                return (
                <tr key={u.id} className="data-row border-b border-slate-100" data-testid={`user-row-${u.id}`}>
                  <td className="px-5 py-3 font-semibold">{uName}</td>
                  <td className="px-5 py-3 text-slate-600">{uEmail}</td>
                  <td className="px-5 py-3">
                    <Select value={uRole} onValueChange={(v) => changeRole(u.id, v)}>
                      <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">Admin</SelectItem>
                        <SelectItem value="responsable">Responsable</SelectItem>
                        <SelectItem value="commercial">Commercial</SelectItem>
                        <SelectItem value="technicien">Technicien</SelectItem>
                        <SelectItem value="sous_traitant">Sous-traitant</SelectItem>
                        <SelectItem value="comptable">Comptable</SelectItem>
                        <SelectItem value="prospecteur">Prospecteur</SelectItem>
                        <SelectItem value="responsable_prospecteur">Responsable prospecteur</SelectItem>
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-5 py-3 text-right space-x-1">
                    <Button variant="ghost" size="sm" onClick={() => setPermsEditing(u)} data-testid={`user-perms-${u.id}`} aria-label="Personnaliser les permissions" title="Personnaliser les permissions">
                      <Shield size={14} />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setPwEditing(u)} data-testid={`user-pw-${u.id}`} aria-label="Changer mot de passe">
                      <KeyRound size={14} />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => remove(u.id)} data-testid={`user-delete-${u.id}`} aria-label="Supprimer">
                      <Trash2 size={14} />
                    </Button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={!!pwEditing} onOpenChange={(v) => { if (!v) { setPwEditing(null); setNewPw(""); } }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle className="font-display text-xl">Nouveau mot de passe</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label>Mot de passe pour {pwEditing?.name}</Label>
            <Input type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="12 caractères minimum" data-testid="user-new-password-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setPwEditing(null); setNewPw(""); }}>Annuler</Button>
            <Button onClick={savePassword} data-testid="user-save-password-btn">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PermissionsDialog
        user={permsEditing}
        open={!!permsEditing}
        onOpenChange={(v) => !v && setPermsEditing(null)}
        onSaved={load}
      />

      {/* Team management */}
      <div className="mt-10">
        <div className="mb-4">
          <p className="overline">Équipes commerciales et techniques</p>
          <h2 className="font-display text-2xl font-semibold tracking-tight">Équipe</h2>
          <p className="text-sm text-slate-500 mt-1">Ajoutez ou retirez des commerciaux (utilisés dans les Ventes & Commissions) et des techniciens (utilisés dans les Chantiers & Planning).</p>
        </div>
        <TeamSection />
      </div>
    </div>
  );
}
