import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2, Trophy } from "lucide-react";

const newBonus = () => ({ id: `b${Date.now()}`, name: "", metric: "ca", threshold: 30000, amount: 300 });

export const ProspectMgrBonusesEditor = ({ value, onChange }) => {
  const list = Array.isArray(value) ? value : [];
  const set = (i, patch) => onChange(list.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  return (
    <div className="border-t border-slate-100 mt-5 pt-5" data-testid="prospect-mgr-bonuses">
      <p className="text-sm font-semibold text-slate-800 mb-1 flex items-center gap-1.5"><Trophy size={14} className="text-amber-500" /> Primes responsable prospection</p>
      <p className="text-xs text-slate-500 mb-3">Primes mensuelles, cumulables, déclenchées par le CA ou le nombre de ventes de toute l'équipe de prospection.</p>
      <div className="space-y-2">
        {list.length === 0 && <p className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-md p-3 text-center">Aucune prime configurée.</p>}
        {list.map((b, i) => (
          <div key={b.id || i} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`prospect-mgr-bonus-${i}`}>
            <Input value={b.name} onChange={(e) => set(i, { name: e.target.value })} placeholder="Nom (ex : Palier Or)" className="h-9 w-40" data-testid={`prospect-mgr-bonus-name-${i}`} />
            <span className="text-slate-500">dès</span>
            <Input type="number" min="0" value={b.threshold} onChange={(e) => set(i, { threshold: e.target.value })} className="h-9 w-28 text-center font-mono" data-testid={`prospect-mgr-bonus-threshold-${i}`} />
            <Select value={b.metric || "ca"} onValueChange={(v) => set(i, { metric: v })}>
              <SelectTrigger className="h-9 w-32" data-testid={`prospect-mgr-bonus-metric-${i}`}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ca">€ de CA</SelectItem>
                <SelectItem value="sales">ventes</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-slate-500">→ prime</span>
            <Input type="number" min="0" value={b.amount} onChange={(e) => set(i, { amount: e.target.value })} className="h-9 w-24 text-center font-mono" data-testid={`prospect-mgr-bonus-amount-${i}`} />
            <span className="text-slate-500">€</span>
            <button type="button" onClick={() => onChange(list.filter((_, j) => j !== i))} className="text-slate-400 hover:text-red-600 transition-colors" data-testid={`prospect-mgr-bonus-del-${i}`}><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => onChange([...list, newBonus()])} data-testid="prospect-mgr-bonus-add"><Plus size={14} className="mr-1" /> Ajouter une prime</Button>
    </div>
  );
};

export const cleanMgrBonuses = (list) => (Array.isArray(list) ? list : []).map((b) => ({
  id: b.id, name: (b.name || "").trim() || "Prime", metric: b.metric === "sales" ? "sales" : "ca",
  threshold: parseFloat(b.threshold) || 0, amount: parseFloat(b.amount) || 0,
}));

export const mgrBonusesFor = (bonuses, count, ca) => cleanMgrBonuses(bonuses)
  .filter((b) => (b.metric === "sales" ? count : ca) >= b.threshold);
