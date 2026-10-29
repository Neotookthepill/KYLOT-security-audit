import React, { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertTriangle, Loader2, Check } from "lucide-react";
import { toast } from "sonner";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

// iter187 — Ce dialogue N'UTILISE PLUS `useTeam().commerciaux` (qui liste des
// team_members potentiellement sans compte utilisateur). Il liste directement les
// USERS de la société avec un rôle commercial (commercial / responsable / admin).
// Sinon, l'admin picke un team_member sans user, le backend fuzzy-matche
// silencieusement vers un autre user et la vente semble revenir dans la liste.

export default function UnmatchedCommercialsDialog({ open, onOpenChange, onBound }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [picks, setPicks] = useState({}); // sale_id -> user_id
  const [saving, setSaving] = useState({}); // sale_id -> bool
  const [users, setUsers] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rs, us] = await Promise.all([
        api.get("/sales/unmatched-commercials"),
        api.get("/users"),
      ]);
      setRows(rs.data || []);
      const list = Array.isArray(us.data) ? us.data : (us.data?.items || []);
      // Seuls les rôles habilités à porter une commission apparaissent.
      const eligible = list.filter((u) => ["commercial", "responsable", "admin"].includes(u.role));
      eligible.sort((a, b) => (a.name || "").localeCompare(b.name || "", "fr"));
      setUsers(eligible);
    }
    catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (open) load(); }, [open, load]);

  const bind = async (row) => {
    const user_id = picks[row.id];
    if (!user_id) { toast.error("Sélectionne un commercial d'abord"); return; }
    setSaving((s) => ({ ...s, [row.id]: true }));
    try {
      await api.post(`/sales/${row.id}/bind-commercial`, { slot: "commercial", user_id });
      toast.success("Vente attribuée");
      setRows((rs) => rs.filter((r) => r.id !== row.id));
      onBound?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving((s) => ({ ...s, [row.id]: false })); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="unmatched-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-500" /> Ventes non associées à un commercial
          </DialogTitle>
          <p className="text-sm text-slate-500">
            Ces ventes contiennent un nom de vendeur qui ne correspond à aucun utilisateur reconnu. Choisis le bon commercial pour chaque ligne. Les ventes au nom de « Direction » sont reconnues automatiquement.
          </p>
          {!loading && users.length === 0 && (
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 mt-2">
              Aucun utilisateur commercial disponible. Ajoute d'abord un utilisateur (rôle Commercial / Responsable / Admin) depuis <span className="font-semibold">Utilisateurs</span>.
            </p>
          )}
        </DialogHeader>

        {loading && <div className="p-6 text-center text-slate-500"><Loader2 size={16} className="animate-spin inline mr-2" />Chargement…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-emerald-700 font-medium">
            <Check size={18} className="inline mr-1" /> Toutes les ventes sont associées à un commercial.
          </div>
        )}
        {!loading && rows.length > 0 && (
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left">
                  <th className="px-3 py-2 overline">Date</th>
                  <th className="px-3 py-2 overline">Client</th>
                  <th className="px-3 py-2 overline">Nom saisi</th>
                  <th className="px-3 py-2 overline text-right">Montant</th>
                  <th className="px-3 py-2 overline">Attribuer à</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100" data-testid={`unmatched-row-${r.id}`}>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{r.sale_date}</td>
                    <td className="px-3 py-2 font-medium">{r.client_name || "—"}</td>
                    <td className="px-3 py-2 text-slate-700 italic">{r.commercial || <span className="text-slate-400">—</span>}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">{fmtEur(r.amount)}</td>
                    <td className="px-3 py-2">
                      <Select value={picks[r.id] || ""} onValueChange={(v) => setPicks((p) => ({ ...p, [r.id]: v }))}>
                        <SelectTrigger className="h-8 w-[220px]" data-testid={`unmatched-select-${r.id}`}><SelectValue placeholder="Choisir un utilisateur…" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__direction__" data-testid={`unmatched-direction-${r.id}`}>Direction<span className="text-slate-400 text-[10px] ml-1">(vente direction)</span></SelectItem>
                          {users.map((u) => (
                            <SelectItem key={u.id} value={u.id}>{u.name}<span className="text-slate-400 text-[10px] ml-1">({u.role})</span></SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button size="sm" onClick={() => bind(r)} disabled={!picks[r.id] || saving[r.id]} data-testid={`unmatched-bind-${r.id}`}>
                        {saving[r.id] ? <Loader2 size={12} className="animate-spin" /> : "Attribuer"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
