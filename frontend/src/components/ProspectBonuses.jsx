import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus, Trash2, Gift } from "lucide-react";

const newBonus = () => ({ sales: 5, amount: 200 });

export const ProspectBonusesEditor = ({ value, onChange }) => {
  const list = Array.isArray(value) ? value : [];
  const set = (i, patch) => onChange(list.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  return (
    <div className="border-t border-slate-100 mt-5 pt-5" data-testid="prospect-bonuses">
      <p className="text-sm font-semibold text-slate-800 mb-1 flex items-center gap-1.5"><Gift size={14} className="text-emerald-600" /> Primes prospecteur par nombre de ventes</p>
      <p className="text-xs text-slate-500 mb-3">Primes cumulables sur la période affichée. Exemple : 200 € à la 5e vente, puis 200 € supplémentaires à la 8e. Une annulation recalcule automatiquement le compteur.</p>
      <div className="space-y-2">
        {list.length === 0 && <p className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-md p-3 text-center">Aucune prime configurée.</p>}
        {list.map((b, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`prospect-bonus-${i}`}>
            <span className="text-slate-500">À partir de</span>
            <Input type="number" min="1" step="1" value={b.sales} onChange={(e) => set(i, { sales: e.target.value })} className="h-9 w-24 text-center font-mono" aria-label={`Nombre de ventes de la prime ${i+1}`} data-testid={`prospect-bonus-sales-${i}`} />
            <span className="text-slate-500">vente(s) → prime</span>
            <Input type="number" min="0" step="10" value={b.amount} onChange={(e) => set(i, { amount: e.target.value })} className="h-9 w-28 text-center font-mono" aria-label={`Montant de la prime ${i+1}`} data-testid={`prospect-bonus-amount-${i}`} />
            <span className="text-slate-500">€</span>
            <button type="button" onClick={() => onChange(list.filter((_, j) => j !== i))} className="text-slate-400 hover:text-red-600 transition-colors" aria-label={`Supprimer la prime ${i+1}`} data-testid={`prospect-bonus-del-${i}`}><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => onChange([...list, newBonus()])} data-testid="prospect-bonus-add"><Plus size={14} className="mr-1" /> Ajouter un palier</Button>
    </div>
  );
};

export const cleanProspectBonuses = (list) => (Array.isArray(list) ? list : [])
  .map((b) => ({ sales: parseInt(b.sales, 10) || 0, amount: parseFloat(b.amount) || 0 }))
  .filter((b) => b.sales > 0)
  .sort((a, b) => a.sales - b.sales);

export const primeForCount = (bonuses, count) => cleanProspectBonuses(bonuses)
  .filter((b) => Number(count) >= b.sales)
  .reduce((sum, b) => sum + b.amount, 0);
