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
import { Trash2, KeyRound, Shield, Settings2 } from "lucide-react";
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
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "technicien", collaborator_status: "salarie", cost_coefficient: 1.875, hourly_cost: 0 });
  const [collabEditing, setCollabEditing] = useState(null);
  const [collabForm, setCollabForm] = useState({ collaborator_status: "salarie", cost_coefficient: 1.875, hourly_cost: 0 });
  const [pwEditing, setPwEditing] = useState(null);
  const [newPw, setNewPw] = useState("");
  const [permsEditing, setPermsEditing] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ name: "", email: "", role: "commercial" });
  const [inviteLink, setInviteLink] = useState("");

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
      setForm({ name: "", email: "", password: "", role: "technicien", collaborator_status: "salarie", cost_coefficient: 1.875, hourly_cost: 0 });
      setOpen(false);
      load();
      notifyTeamSync();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const invite = async () => {
    try {
      if (!inviteForm.name || !inviteForm.email) return toast.error("Nom et email requis");
      const { data } = await api.post("/users/invite", inviteForm);
      const url = data?.invite_url || "";
      setInviteLink(url.startsWith("http") ? url : `${window.location.origin}${url}`);
      setInviteForm({ name: "", email: "", role: "commercial" });
      load();
      notifyTeamSync();
      toast.success("Invitation créée");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const copyInvite = async () => {
    try { await navigator.clipboard.writeText(inviteLink); toast.success("Lien copié"); }
    catch (_) { toast.error("Copie impossible — sélectionne le lien"); }
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

  const openCollab = (u) => {
    setCollabEditing(u);
    setCollabForm({
      collaborator_status: u.collaborator_status || "salarie",
      cost_coefficient: u.cost_coefficient ?? 1.875,
      hourly_cost: u.hourly_cost ?? 0,
    });
  };
  const saveCollab = async () => {
    if (!collabEditing) return;
    try {
      await api.put(`/users/${collabEditing.id}`, {
        collaborator_status: collabForm.collaborator_status,
        cost_coefficient: Number(collabForm.cost_coefficient) || 1,
        hourly_cost: Number(collabForm.hourly_cost) || 0,
      });
      toast.success("Statut et coûts mis à jour");
      setCollabEditing(null);
      load();
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
          <p className="overline">Comptes et droits d’accès</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Utilisateurs & permissions</h1>
          <p className="text-sm text-slate-500 mt-2">Créez des comptes et personnalisez précisément les droits de chaque utilisateur.</p>
        </div>
        <Dialog open={inviteOpen} onOpenChange={(v) => { setInviteOpen(v); if (!v) setInviteLink(""); }}>
          <DialogTrigger asChild>
            <Button variant="outline" data-testid="invite-user-btn">Inviter un utilisateur</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md" data-testid="invite-user-dialog">
            <DialogHeader><DialogTitle className="font-display text-2xl">Inviter un utilisateur</DialogTitle></DialogHeader>
            {inviteLink ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">Envoie ce lien personnel au testeur. Il choisira son mot de passe à la première ouverture. Le lien expire dans 7 jours.</p>
                <Input readOnly value={inviteLink} data-testid="invite-link-input" />
                <div className="flex gap-2">
                  <Button type="button" onClick={copyInvite} data-testid="invite-copy-btn">Copier le lien</Button>
                  <Button type="button" variant="outline" onClick={() => { setInviteOpen(false); setInviteLink(""); }}>Fermer</Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div><Label>Nom complet</Label><Input value={inviteForm.name} onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })} data-testid="invite-name-input" /></div>
                <div><Label>Email</Label><Input type="email" value={inviteForm.email} onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })} data-testid="invite-email-input" /></div>
                <div>
                  <Label>Rôle</Label>
                  <Select value={inviteForm.role} onValueChange={(v) => setInviteForm({ ...inviteForm, role: v })}>
                    <SelectTrigger data-testid="invite-role-select" aria-label="Rôle de l'utilisateur invité"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Admin — accès complet</SelectItem>
                      <SelectItem value="responsable">Responsable — équipes, planning, chantiers</SelectItem>
                      <SelectItem value="commercial">Commercial — ses ventes et clients uniquement</SelectItem>
                      <SelectItem value="technicien">Technicien — ses chantiers + heures sup</SelectItem>
                      <SelectItem value="sous_traitant">Sous-traitant — Chantiers &amp; Planning uniquement</SelectItem>
                      <SelectItem value="comptable">Comptable — Commissions + rapports</SelectItem>
                      <SelectItem value="prospecteur">Prospecteur — ses clients prospectés</SelectItem>
                      <SelectItem value="responsable_prospecteur">Responsable prospecteur</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-[11px] text-slate-500">Aucun email automatique : tu copies le lien toi-même. Le compte reste inactif jusqu'à l'activation.</p>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setInviteOpen(false)}>Annuler</Button>
                  <Button onClick={invite} data-testid="invite-submit-btn">Créer l'invitation</Button>
                </DialogFooter>
              </div>
            )}
          </DialogContent>
        </Dialog>

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
                  <SelectTrigger data-testid="user-role-select" aria-label="Rôle du nouvel utilisateur"><SelectValue /></SelectTrigger>
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
                <p className="text-[11px] text-slate-600 mt-1.5">Le rôle définit les droits par défaut, vous pourrez ensuite les personnaliser via le bouton bouclier.</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Statut collaborateur</Label>
                  <Select value={form.collaborator_status || "salarie"} onValueChange={(v) => setForm({ ...form, collaborator_status: v })}>
                    <SelectTrigger data-testid="user-collab-status"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="salarie">Salarié</SelectItem><SelectItem value="independant">Indépendant</SelectItem><SelectItem value="sous_traitant">Sous-traitant</SelectItem></SelectContent>
                  </Select>
                </div>
                <div><Label>Coefficient charges</Label><Input type="number" min="1" step="0.01" value={form.cost_coefficient ?? 1.875} onChange={(e) => setForm({ ...form, cost_coefficient: e.target.value })} data-testid="user-cost-coefficient" /></div>
              </div>
              <div><Label>Coût horaire chargé (€)</Label><Input type="number" min="0" step="0.01" value={form.hourly_cost ?? 0} onChange={(e) => setForm({ ...form, hourly_cost: e.target.value })} data-testid="user-hourly-cost" /></div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
              <Button onClick={create} data-testid="user-submit-btn">Créer</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Tableau défilant">
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
                      <SelectTrigger className="h-8 w-44" aria-label={`Rôle de ${uName}`}><SelectValue /></SelectTrigger>
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
                    <Button variant="ghost" size="sm" onClick={() => openCollab(u)} data-testid={`user-collab-${u.id}`} aria-label="Statut et coût" title="Statut et coût">
                      <Settings2 size={14} />
                    </Button>
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

      <Dialog open={!!collabEditing} onOpenChange={(v) => { if (!v) setCollabEditing(null); }}>
        <DialogContent className="sm:max-w-sm" data-testid="user-collab-dialog">
          <DialogHeader><DialogTitle className="font-display text-xl">Statut et coût — {collabEditing?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Statut collaborateur</Label>
              <Select value={collabForm.collaborator_status} onValueChange={(v) => setCollabForm({ ...collabForm, collaborator_status: v })}>
                <SelectTrigger data-testid="user-collab-edit-status"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="salarie">Salarié</SelectItem><SelectItem value="independant">Indépendant</SelectItem><SelectItem value="sous_traitant">Sous-traitant</SelectItem></SelectContent>
              </Select>
            </div>
            <div><Label>Coefficient de charges</Label><Input type="number" min="1" step="0.01" value={collabForm.cost_coefficient} onChange={(e) => setCollabForm({ ...collabForm, cost_coefficient: e.target.value })} data-testid="user-collab-edit-coefficient" /></div>
            <div><Label>Coût horaire chargé (€)</Label><Input type="number" min="0" step="0.01" value={collabForm.hourly_cost} onChange={(e) => setCollabForm({ ...collabForm, hourly_cost: e.target.value })} data-testid="user-collab-edit-hourly" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCollabEditing(null)}>Annuler</Button>
            <Button onClick={saveCollab} data-testid="user-collab-save">Enregistrer</Button>
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
