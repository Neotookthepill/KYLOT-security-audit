import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

// Cache global to avoid refetching too often
let cache = { commerciaux: null, techniciens: null, sousTraitants: null, ts: 0 };
const listeners = new Set();
function notifyAll() { listeners.forEach((fn) => fn(cache)); }

export default function useTeam() {
  const [commerciaux, setCommerciaux] = useState(cache.commerciaux || []);
  const [techniciens, setTechniciens] = useState(cache.techniciens || []);
  const [sousTraitants, setSousTraitants] = useState(cache.sousTraitants || []);
  const [loading, setLoading] = useState(!cache.commerciaux);

  const load = useCallback(async () => {
    try {
      const [c, t, st, users] = await Promise.all([
        api.get("/team?type=commercial"),
        api.get("/team?type=technicien"),
        api.get("/team?type=sous_traitant").catch(() => ({ data: [] })),
        api.get("/users"),
      ]);
      // iter90 : coerce en Array pour tolérer une réponse malformée
      const asArr = (x) => (Array.isArray(x) ? x : []);
      const cData = asArr(c.data);
      const tData = asArr(t.data);
      // iter135 : fusionne users (role=sous_traitant) + team_members (type=sous_traitant)
      // en dédupliquant par email OU nom normalisé. Les entries `team_members` (sans compte)
      // portent un marker `_account_less: true` pour que la UI puisse router les actions.
      const userSt = asArr(users.data).filter((u) => u && u.role === "sous_traitant");
      const tmSt = asArr(st.data).map((m) => ({ ...m, _account_less: true }));
      const norm = (s) => (s || "").trim().toLowerCase();
      const seen = new Set();
      const merged = [];
      for (const u of userSt) {
        const key = norm(u.email) || `n:${norm(u.name)}`;
        if (!seen.has(key)) { seen.add(key); merged.push(u); }
      }
      for (const m of tmSt) {
        const key = norm(m.email) || `n:${norm(m.name)}`;
        if (!seen.has(key)) { seen.add(key); merged.push(m); }
      }
      cache = { commerciaux: cData, techniciens: tData, sousTraitants: merged, ts: Date.now() };
      setCommerciaux(cData);
      setTechniciens(tData);
      setSousTraitants(merged);
      notifyAll();
    } catch (e) {
      // ignore, keep old data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const l = (c) => {
      setCommerciaux(c.commerciaux || []);
      setTechniciens(c.techniciens || []);
      setSousTraitants(c.sousTraitants || []);
    };
    listeners.add(l);
    // iter92 : auto-sync when a user role changes elsewhere (Users page, promotions…)
    const onExternal = () => { load(); };
    window.addEventListener("kylot:team-updated", onExternal);
    return () => {
      listeners.delete(l);
      window.removeEventListener("kylot:team-updated", onExternal);
    };
  }, [load]);

  return { commerciaux, techniciens, sousTraitants, loading, reload: load };
}
