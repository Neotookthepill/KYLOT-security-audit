import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ShieldOff, ShieldCheck } from "lucide-react";

export default function CompanyUsersDialog({ company, open, onOpenChange }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    if (!company?.id) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/superadmin/companies/${company.id}/users`);
      setRows(data.users || []);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, company?.id]);

  const resetMfa = async (user) => {
    const reason = window.prompt(
      `Réinitialiser la MFA de ${user.name || user.email} ?\n\nMotif obligatoire (au moins 5 caractères) :`
    );
    if (reason === null) return;
    if (reason.trim().length < 5) {
      toast.error("Le motif doit contenir au moins 5 caractères.");
      return;
    }
    setBusyId(user.id);
    try {
      await api.post(`/superadmin/users/${user.id}/mfa/reset`, { reason: reason.trim() });
      toast.success("MFA réinitialisée. Toutes les sessions de cet utilisateur sont révoquées.");
      await load();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl" data-testid="company-users-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">
            Utilisateurs — {company?.name || ""}
          </DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-600">
          En cas de téléphone perdu et de codes de secours perdus, réinitialisez la MFA.
          Le mot de passe reste inchangé et toutes les sessions de l'utilisateur sont révoquées.
        </p>
        <div className="max-h-[55vh] overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-50">
              <tr className="text-left border-b border-slate-200">
                <th className="px-3 py-2 overline">Utilisateur</th>
                <th className="px-3 py-2 overline">Rôle</th>
                <th className="px-3 py-2 overline">MFA</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={4} className="p-4 text-center text-slate-500">Chargement…</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={4} className="p-4 text-center text-slate-500">Aucun utilisateur.</td></tr>
              )}
              {rows.map((u) => (
                <tr key={u.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium">{u.name || "—"}</div>
                    <div className="text-xs text-slate-500">{u.email}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{u.role}</td>
                  <td className="px-3 py-2">
                    {u.mfa_enabled ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                        <ShieldCheck size={13} /> Activée
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                        <ShieldOff size={13} /> Désactivée
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {u.mfa_enabled && u.role !== "super_admin" && (
                      <Button
                        variant="outline" size="sm" disabled={busyId === u.id}
                        onClick={() => resetMfa(u)}
                        data-testid={`reset-mfa-${u.id}`}
                      >
                        Réinitialiser la MFA
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
