import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { RESOURCES, SCOPE_OPTIONS, ROLE_LABELS } from "@/lib/permissions";
import { RotateCcw, Shield } from "lucide-react";

export default function PermissionsDialog({ user, open, onOpenChange, onSaved }) {
  const [perms, setPerms] = useState(null);
  const [defaults, setDefaults] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !user) return;
    (async () => {
      try {
        const [p, d] = await Promise.all([
          api.get(`/users/${user.id}/permissions`),
          api.get(`/roles/defaults`),
        ]);
        setPerms(p.data.permissions || {});
        setDefaults(d.data || {});
      } catch (err) {
        toast.error(formatApiError(err));
      }
    })();
  }, [open, user]);

  const setVal = (resource, action, value) => {
    setPerms((prev) => ({
      ...prev,
      [resource]: { ...(prev?.[resource] || {}), [action]: value },
    }));
  };

  const reset = () => {
    if (!defaults[user.role]) {
      toast.info("Pas de préréglage pour ce rôle");
      return;
    }
    setPerms(JSON.parse(JSON.stringify(defaults[user.role])));
    toast.success(`Préréglage "${ROLE_LABELS[user.role] || user.role}" appliqué`);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/users/${user.id}/permissions`, { permissions: perms });
      toast.success("Permissions enregistrées");
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="permissions-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <Shield size={20} className="text-slate-500" />
            Permissions de {user.name}
          </DialogTitle>
          <p className="text-xs text-slate-500 mt-1">
            Rôle : <span className="font-semibold">{ROLE_LABELS[user.role] || user.role}</span> · Ajustez ci-dessous les accès de cet utilisateur.
          </p>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {perms == null ? (
            <p className="text-sm text-slate-500">Chargement…</p>
          ) : (
            RESOURCES.map((r) => (
              <div key={r.key} className="rounded-lg border border-slate-200 p-4" data-testid={`perm-resource-${r.key}`}>
                <p className="font-display text-sm font-semibold mb-3">{r.label}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {r.actions.map((a) => {
                    const cur = (perms[r.key] || {})[a.key];
                    if (a.type === "scope") {
                      const val = typeof cur === "string" ? cur : "none";
                      return (
                        <div key={a.key} className="flex items-center justify-between gap-2">
                          <span className="text-sm text-slate-700">{a.label}</span>
                          <Select value={val} onValueChange={(v) => setVal(r.key, a.key, v)}>
                            <SelectTrigger className="h-8 w-40" data-testid={`perm-${r.key}-${a.key}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {SCOPE_OPTIONS.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      );
                    }
                    return (
                      <div key={a.key} className="flex items-center justify-between gap-2">
                        <span className="text-sm text-slate-700">{a.label}</span>
                        <Switch
                          checked={!!cur}
                          onCheckedChange={(v) => setVal(r.key, a.key, !!v)}
                          data-testid={`perm-${r.key}-${a.key}`}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        <DialogFooter className="mt-4 flex-wrap gap-2">
          <Button variant="outline" onClick={reset} data-testid="perm-reset-btn">
            <RotateCcw size={12} className="mr-1.5" />
            Réinitialiser au rôle {ROLE_LABELS[user.role] || user.role}
          </Button>
          <div className="flex gap-2 sm:ml-auto">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving || !perms} data-testid="perm-save-btn">
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
