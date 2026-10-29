import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";

const QUICK = [400, 500, 600];

export const ProspecteurField = ({ form, setForm, testPrefix }) => {
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const canComm = ["admin", "responsable"].includes(user?.role);
  useEffect(() => {
    api.get("/prospecteurs").then((r) => setList(r.data || [])).catch(() => {});
  }, []);
  const pid = form.prospecteur_id || "";
  return (
    <div className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-slate-50/50 p-3" data-testid={`${testPrefix}-prospecteur-block`}>
      <div className="space-y-1.5">
        <Label>Prospecteur</Label>
        <Select value={pid || "__none"} onValueChange={(v) => setForm({ ...form, prospecteur_id: v === "__none" ? "" : v })}>
          <SelectTrigger data-testid={`${testPrefix}-prospecteur`}><SelectValue placeholder="—" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none">—</SelectItem>
            {list.map((p) => (<SelectItem key={p.id} value={p.id}>{p.name}{p.role === "responsable_prospecteur" ? " (Responsable prospection)" : ""}</SelectItem>))}
          </SelectContent>
        </Select>
      </div>
      {pid && canComm && (
        <div className="space-y-1.5">
          <Label>Commission prospecteur (€)</Label>
          <Input type="number" min={0} step="10" value={form.prospecteur_commission ?? ""} placeholder="Montant fixe"
            data-testid={`${testPrefix}-prospecteur-commission`}
            onChange={(e) => setForm({ ...form, prospecteur_commission: e.target.value })} />
          <div className="flex gap-1.5">
            {QUICK.map((n) => (
              <button key={n} type="button" data-testid={`${testPrefix}-prospecteur-quick-${n}`}
                onClick={() => setForm({ ...form, prospecteur_commission: n })}
                className={`text-xs px-2 py-1 rounded-md border transition-colors ${Number(form.prospecteur_commission) === n ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 hover:bg-white"}`}>
                {n} €
              </button>
            ))}
          </div>
        </div>
      )}
      {list.length === 0 && (
        <p className="col-span-2 text-[11px] text-slate-500">Aucun prospecteur : créez un utilisateur avec le rôle « Prospecteur ».</p>
      )}
    </div>
  );
};

export const prospecteurPayload = (form) => ({
  prospecteur_id: form.prospecteur_id || "",
  prospecteur_commission: form.prospecteur_id && form.prospecteur_commission !== "" && form.prospecteur_commission != null
    ? parseFloat(form.prospecteur_commission) : null,
});
