import React from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";

/**
 * List editor for sale prestations: each row = { name, quantity (1..10) }.
 * Fully controlled; parent owns state.
 */
export default function ProductsEditor({ value, onChange, testIdPrefix = "prestation" }) {
  const list = Array.isArray(value) ? value : [];

  const update = (idx, patch) => {
    const next = list.map((it, i) => (i === idx ? { ...it, ...patch } : it));
    onChange(next);
  };
  const add = () => onChange([...list, { name: "", quantity: 1 }]);
  const remove = (idx) => onChange(list.filter((_, i) => i !== idx));

  return (
    <div className="space-y-2" data-testid={`${testIdPrefix}-editor`}>
      {list.length === 0 && (
        <p className="text-xs text-slate-500 italic px-2">Aucun produit. Cliquez sur « + Ajouter un produit ».</p>
      )}
      {list.map((it, idx) => (
        <div key={idx} className="flex items-center gap-2" data-testid={`${testIdPrefix}-row-${idx}`}>
          <Input
            value={it.name || ""}
            onChange={(e) => update(idx, { name: e.target.value })}
            placeholder="Ex : Système anti-incendie"
            className="flex-1 h-9"
            data-testid={`${testIdPrefix}-name-${idx}`}
          />
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-xs text-slate-500">Qté</span>
            <select
              value={Number(it.quantity || 1)}
              onChange={(e) => update(idx, { quantity: parseInt(e.target.value, 10) })}
              className="h-9 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-slate-900"
              data-testid={`${testIdPrefix}-qty-${idx}`}
            >
              {[1,2,3,4,5,6,7,8,9,10].map((n) => (<option key={n} value={n}>{n}</option>))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => remove(idx)}
            aria-label="Retirer ce produit"
            className="h-9 w-9 grid place-items-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition"
            data-testid={`${testIdPrefix}-remove-${idx}`}
          >
            <X size={14} />
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        className="w-full"
        data-testid={`${testIdPrefix}-add-btn`}
      >
        <Plus size={14} className="mr-1" /> Ajouter un produit
      </Button>
    </div>
  );
}

// Helpers used by NewSale/EditSale/Stock display.
export function prestationsToServiceString(list) {
  if (!Array.isArray(list) || list.length === 0) return "";
  return list
    .filter((p) => (p?.name || "").trim())
    .map((p) => `${p.name.trim()} ×${Math.max(1, Math.min(10, parseInt(p.quantity || 1, 10)))}`)
    .join(", ");
}

export function parseServiceToPrestations(service) {
  if (!service || typeof service !== "string") return [];
  return service
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const m = s.match(/^(.*?)\s*[x×]\s*(\d{1,2})$/i);
      if (m) return { name: m[1].trim(), quantity: Math.max(1, Math.min(10, parseInt(m[2], 10))) };
      return { name: s, quantity: 1 };
    });
}
