import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Clock, Search, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import useTeam from "@/lib/useTeam";

/**
 * Curated list of people eligible for the "Heures sup" module.
 * Independent from user accounts, roles, or planning:
 *   - Adding someone → they appear as a card + row and can log hours.
 *   - Removing someone → they disappear from the overtime module (but keep
 *     their planning / chantiers / user account intact).
 *
 * Persisted server-side under settings.overtime_eligible (list of names).
 * If never configured, backend falls back to the full technicien list.
 */
export default function OvertimeAccessDialog({ open, onOpenChange, onChanged }) {
  const { commerciaux, techniciens, reload: reloadTeam } = useTeam();
  const [eligible, setEligible] = useState([]);      // current curated list
  const [initialConfigured, setInitialConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");

  // Load current eligibility from /settings when the dialog opens
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [s] = await Promise.all([api.get("/settings"), reloadTeam?.()]);
        if (cancelled) return;
        const raw = s.data?.overtime_eligible;
        if (Array.isArray(raw)) {
          setEligible(raw);
          setInitialConfigured(true);
        } else {
          // First-time setup — pre-seed with every technicien so we don't
          // silently break the current behaviour when the admin saves.
          setEligible((techniciens || []).map((t) => t.name));
          setInitialConfigured(false);
        }
      } catch (err) { toast.error(formatApiError(err)); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const candidates = useMemo(() => {
    // Merge techniciens + commerciaux from team_members as pickable people.
    // Also include any name already in `eligible` that doesn't match either
    // list (e.g. an old free-typed name) so admin can still remove it.
    const seen = new Map();
    for (const t of techniciens || []) seen.set(t.name, { name: t.name, type: "technicien" });
    for (const c of commerciaux || []) if (!seen.has(c.name)) seen.set(c.name, { name: c.name, type: "commercial" });
    for (const n of eligible) if (!seen.has(n)) seen.set(n, { name: n, type: "autre" });
    const arr = Array.from(seen.values());
    const term = q.trim().toLowerCase();
    return arr
      .filter((p) => !term || p.name.toLowerCase().includes(term))
      .sort((a, b) => a.name.localeCompare(b.name, "fr"));
  }, [techniciens, commerciaux, eligible, q]);

  const isOn = (name) => eligible.includes(name);

  const toggle = (name) => {
    setEligible((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  };

  const save = async () => {
    setSaving(true);
    try {
      const clean = Array.from(new Set(eligible.map((n) => (n || "").trim()).filter(Boolean)));
      await api.put("/settings", { overtime_eligible: clean });
      toast.success("Liste des heures sup mise à jour");
      onChanged?.();
      onOpenChange(false);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const eligibleCount = eligible.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="overtime-access-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <Clock size={18} /> Personnes éligibles aux heures sup
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-slate-500">
          Ajoutez ou retirez des personnes de la gestion des heures supplémentaires. Cette liste est <span className="font-semibold text-slate-700">indépendante</span> des comptes utilisateurs et du planning : un technicien sous-traitant peut rester dans les chantiers/planning sans apparaître ici.
        </p>

        <div className="flex items-center gap-2 text-xs">
          <Badge className="bg-slate-100 text-slate-700 border-0">
            {eligibleCount} personne{eligibleCount > 1 ? "s" : ""} éligible{eligibleCount > 1 ? "s" : ""}
          </Badge>
          {!initialConfigured && (
            <span className="text-amber-700">Liste pré-remplie avec tous les techniciens — décochez les sous-traitants.</span>
          )}
        </div>

        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-8 h-9"
            placeholder="Rechercher…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="ot-eligible-search"
          />
        </div>

        <div className="max-h-96 overflow-y-auto -mx-1 px-1 divide-y divide-slate-100">
          {loading && <p className="text-sm text-slate-500 py-4">Chargement…</p>}
          {!loading && candidates.length === 0 && (
            <p className="text-sm text-slate-500 py-4">Aucune personne dans l'équipe. Ajoutez-en dans « Utilisateurs → Équipe ».</p>
          )}
          {candidates.map((p) => {
            const on = isOn(p.name);
            return (
              <div key={p.name} className="flex items-center justify-between py-2.5" data-testid={`ot-eligible-row-${p.name}`}>
                <div className="min-w-0 flex items-center gap-3">
                  <div className={`h-8 w-8 rounded-full grid place-items-center text-xs font-semibold uppercase shrink-0 ${on ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500"}`}>
                    {(p.name || "?").slice(0, 2)}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate flex items-center gap-2">
                      {p.name}
                      <Badge className={`border-0 text-[10px] ${p.type === "technicien" ? "bg-blue-50 text-blue-800" : p.type === "commercial" ? "bg-indigo-50 text-indigo-800" : "bg-slate-100 text-slate-700"}`}>
                        {p.type}
                      </Badge>
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant={on ? "outline" : "default"}
                  onClick={() => toggle(p.name)}
                  className={on ? "border-red-200 text-red-700 hover:bg-red-50" : ""}
                  data-testid={`ot-eligible-toggle-${p.name}`}
                >
                  {on ? (<><X size={14} className="mr-1" /> Retirer</>) : (<><UserPlus size={14} className="mr-1" /> Ajouter</>)}
                </Button>
              </div>
            );
          })}
        </div>

        <DialogFooter className="mt-2 flex justify-between sm:justify-between gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
          <Button onClick={save} disabled={saving || loading} data-testid="ot-eligible-save">
            {saving ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
