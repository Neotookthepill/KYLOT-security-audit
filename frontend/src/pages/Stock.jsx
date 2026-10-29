import React, { useCallback, useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Search, Plus, Minus, PackageCheck, Boxes, Loader2, Trash2, AlertTriangle, ArrowDownToLine, HardHat, User as UserIcon, ClipboardList, Pencil, RotateCcw, Check, X, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const fmtShortDate = (iso) => {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
};
const STATUS_LABEL = { a_planifier: "À planifier", en_cours: "PROG" };
const STATUS_CLS = { a_planifier: "bg-slate-100 text-slate-700 border-slate-200", en_cours: "bg-amber-100 text-amber-800 border-amber-200" };

function StatusDot({ status }) {
  const map = {
    red: "bg-red-500",
    orange: "bg-amber-500",
    green: "bg-emerald-500",
  };
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${map[status] || "bg-slate-300"}`} />;
}

// iter65 : cellule éditable pour override manuel d'une valeur auto-calculée
function OverrideCell({ value, autoValue, override, onSave, onRevert, canEdit, testId, tone = "default", extraLink = null }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(String(value ?? 0));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setVal(String(value ?? 0)); }, [value]);

  const isOverridden = !!override;
  const displayVal = value ?? 0;

  const toneCls = (() => {
    if (tone === "prev") return displayVal < 0 ? "text-red-700" : displayVal === 0 ? "text-amber-700" : "text-emerald-700";
    if (tone === "reste") return displayVal > 0 ? "text-red-700" : "text-slate-500";
    if (tone === "besoin") return displayVal > 0 ? "text-slate-900" : "text-slate-400";
    return "text-slate-900";
  })();

  const commit = async () => {
    const n = Math.max(-100000, Math.min(100000, parseInt(val, 10) || 0));
    if (n === Number(autoValue || 0) && !isOverridden) { setEditing(false); return; }
    setSaving(true);
    try {
      await onSave(n);
      setEditing(false);
    } catch (_) {
      setVal(String(value ?? 0));
    } finally { setSaving(false); }
  };

  if (editing) {
    return (
      <div className="inline-flex items-center gap-1 justify-end" data-testid={`${testId}-edit`}>
        <Input
          type="number"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            else if (e.key === "Escape") { setVal(String(value ?? 0)); setEditing(false); }
          }}
          autoFocus
          className="w-20 h-7 text-right text-sm px-2"
          data-testid={`${testId}-input`}
        />
        <button
          type="button"
          onClick={commit}
          disabled={saving}
          className="h-7 w-7 grid place-items-center rounded-md border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
          aria-label="Valider"
          data-testid={`${testId}-confirm`}
        >{saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}</button>
        <button
          type="button"
          onClick={() => { setVal(String(value ?? 0)); setEditing(false); }}
          disabled={saving}
          className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50"
          aria-label="Annuler"
          data-testid={`${testId}-cancel`}
        ><X size={12} /></button>
      </div>
    );
  }

  const tooltip = isOverridden
    ? `Valeur manuelle · Modifié par ${override.updated_by_name || "?"} le ${new Date(override.updated_at).toLocaleString("fr-FR")} · Auto : ${autoValue}`
    : (canEdit ? "Cliquer pour saisir une valeur manuelle" : "");

  return (
    <div
      className={`inline-flex items-center gap-1 justify-end group ${isOverridden ? "px-1.5 py-0.5 rounded-md bg-amber-50 border border-amber-300" : ""}`}
      title={tooltip}
      data-testid={testId}
    >
      <span className={`font-display font-semibold tabular-nums ${toneCls}`}>
        {extraLink ? (
          <button
            type="button"
            onClick={extraLink}
            className="hover:text-indigo-700 hover:underline underline-offset-2 transition"
            title="Voir les chantiers concernés"
          >{displayVal}</button>
        ) : (
          displayVal
        )}
      </span>
      {isOverridden && (
        <>
          <Pencil size={10} className="text-amber-600 shrink-0" aria-hidden="true" />
          {canEdit && (
            <button
              type="button"
              onClick={onRevert}
              className="h-5 w-5 grid place-items-center rounded text-amber-700 hover:bg-amber-100 transition"
              title={`Revenir au calcul automatique (${autoValue})`}
              aria-label="Revenir au calcul automatique"
              data-testid={`${testId}-revert`}
            ><RotateCcw size={10} /></button>
          )}
        </>
      )}
      {canEdit && !isOverridden && (
        <button
          type="button"
          onClick={() => { setVal(String(value ?? 0)); setEditing(true); }}
          className="h-5 w-5 grid place-items-center rounded text-slate-300 hover:text-slate-700 hover:bg-slate-100 opacity-0 group-hover:opacity-100 transition"
          title="Modifier manuellement"
          aria-label="Modifier manuellement"
          data-testid={`${testId}-edit-btn`}
        ><Pencil size={10} /></button>
      )}
      {canEdit && isOverridden && (
        <button
          type="button"
          onClick={() => { setVal(String(value ?? 0)); setEditing(true); }}
          className="h-5 w-5 grid place-items-center rounded text-amber-700 hover:bg-amber-100 transition"
          title="Modifier la valeur manuelle"
          aria-label="Modifier la valeur manuelle"
          data-testid={`${testId}-edit-btn`}
        ><Pencil size={10} /></button>
      )}
    </div>
  );
}

// iter207 : cellule "nom produit" avec renommage inline pour le technicien
// qui a créé le produit lui-même (created_by_technician_by_me=true).
function ProductNameCell({ row, canRename, onRename, testId }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(row.product_name || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setVal(row.product_name || ""); }, [row.product_name]);

  const commit = async () => {
    const n = (val || "").trim();
    if (!n || n === (row.product_name || "").trim()) { setEditing(false); return; }
    setSaving(true);
    try {
      await onRename(row, n);
      setEditing(false);
    } catch (_) {
      setVal(row.product_name || "");
    } finally { setSaving(false); }
  };

  if (editing) {
    return (
      <div className="inline-flex items-center gap-1 w-full" data-testid={`${testId}-edit`}>
        <Input
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            else if (e.key === "Escape") { setVal(row.product_name || ""); setEditing(false); }
          }}
          autoFocus
          className="h-7 text-sm flex-1 min-w-0"
          data-testid={`${testId}-input`}
        />
        <button type="button" onClick={commit} disabled={saving}
          className="h-7 w-7 grid place-items-center rounded-md border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
          aria-label="Valider" data-testid={`${testId}-confirm`}
        >{saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}</button>
        <button type="button" onClick={() => { setVal(row.product_name || ""); setEditing(false); }} disabled={saving}
          className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50"
          aria-label="Annuler" data-testid={`${testId}-cancel`}
        ><X size={12} /></button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 group min-w-0" data-testid={testId}>
      <p className="font-semibold text-slate-900 truncate">{row.product_name}</p>
      {canRename && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="h-6 w-6 grid place-items-center rounded text-slate-300 hover:text-indigo-700 hover:bg-indigo-50 opacity-0 group-hover:opacity-100 focus:opacity-100 transition shrink-0"
          title="Renommer ce produit"
          aria-label="Renommer ce produit"
          data-testid={`${testId}-edit-btn`}
        ><Pencil size={11} /></button>
      )}
    </div>
  );
}

function NumberEditor({ value, onCommit, testId, disabled }) {
  const [val, setVal] = useState(String(value ?? 0));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setVal(String(value ?? 0)); }, [value]);
  const commit = async (next) => {
    const n = Math.max(0, Math.min(100000, parseInt(next, 10) || 0));
    if (n === Number(value || 0)) { setVal(String(value ?? 0)); return; }
    setSaving(true);
    try {
      await onCommit(n);
    } catch (e) {
      setVal(String(value ?? 0));
    } finally { setSaving(false); }
  };
  return (
    <div className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={() => commit(Number(val || 0) - 1)}
        disabled={disabled || saving || Number(val || 0) <= 0}
        className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
        aria-label="Diminuer"
        data-testid={`${testId}-dec`}
      ><Minus size={12} /></button>
      <Input
        type="number"
        min="0"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => commit(val)}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
        className="w-16 h-7 text-center text-sm px-1"
        disabled={disabled || saving}
        data-testid={testId}
      />
      <button
        type="button"
        onClick={() => commit(Number(val || 0) + 1)}
        disabled={disabled || saving}
        className="h-7 w-7 grid place-items-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
        aria-label="Augmenter"
        data-testid={`${testId}-inc`}
      ><Plus size={12} /></button>
      {saving && <Loader2 size={12} className="animate-spin text-slate-400 ml-1" />}
    </div>
  );
}

export default function Stock() {
  const { user } = useAuth();
  const isTechnicien = user?.role === "technicien";
  const canEdit = user?.role === "admin" || user?.role === "responsable";
  const [rows, setRows] = useState([]);
  // iter68 : réponse structurée pour un technicien = { mode:"technicien", sections:{mine,others,company}, can_view_* }
  const [techPayload, setTechPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [newName, setNewName] = useState("");
  // iter49 : drill-down "Besoin chantiers" — dialog listant les projets qui consomment un produit
  const [detail, setDetail] = useState(null); // {product_name, product_key, loading, data}
  // iter58 : filtre de période (besoin chantiers sur X jours)
  const [period, setPeriod] = useState("all"); // all | week | 2weeks | month | custom
  const [customUntil, setCustomUntil] = useState("");

  const periodBounds = useMemo(() => {
    const toIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const today = new Date();
    if (period === "week") return { until: toIso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 7)) };
    if (period === "2weeks") return { until: toIso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 14)) };
    if (period === "month") return { until: toIso(new Date(today.getFullYear(), today.getMonth() + 1, today.getDate())) };
    if (period === "custom" && customUntil) return { until: customUntil };
    return {};
  }, [period, customUntil]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (periodBounds.until) params.set("until", periodBounds.until);
      const suffix = params.toString() ? `?${params}` : "";
      const data = (await api.get(`/stock${suffix}`)).data;
      // iter68 : payload technicien = objet {mode,sections,...}. Managers = array.
      if (data && !Array.isArray(data) && data.mode === "technicien") {
        setTechPayload(data);
        setRows([]);
      } else {
        setTechPayload(null);
        setRows(data || []);
      }
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, [periodBounds]);
  useEffect(() => { load(); }, [load]);

  // iter52 : rafraîchir le stock quand une vente change de statut (annule → besoin recalculé)
  useEffect(() => {
    const onSalesUpdated = () => { load(); };
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    return () => window.removeEventListener("kylot:sales-updated", onSalesUpdated);
  }, [load]);

  const filtered = useMemo(() => {
    const t = q.toLowerCase();
    return rows.filter((r) => (r.product_name || "").toLowerCase().includes(t));
  }, [rows, q]);

  const totals = useMemo(() => {
    let toOrder = 0, covered = 0, low = 0;
    for (const r of rows) {
      if (r.status === "red") toOrder += 1;
      else if (r.status === "green") covered += 1;
      if (r.low_stock) low += 1;
    }
    return { toOrder, covered, low };
  }, [rows]);

  const updateField = async (row, patch) => {
    try {
      await api.post("/stock", { product_name: row.product_name, ...patch });
      await load();
    } catch (err) { toast.error(formatApiError(err)); throw err; }
  };

  const receive = async (row) => {
    if (!row.id || (row.commande_en_cours || 0) <= 0) return;
    try {
      await api.post(`/stock/${row.id}/receive`, {});
      toast.success(`+${row.commande_en_cours} ${row.product_name} reçu(s)`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const del = async (row) => {
    if (!row.id) return;
    if (!window.confirm(`Supprimer la ligne stock « ${row.product_name} » ?`)) return;
    try {
      await api.delete(`/stock/${row.id}`);
      toast.success("Ligne supprimée");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const addManual = async () => {
    const n = (newName || "").trim();
    if (!n) return toast.error("Nom du produit requis");
    try {
      await api.post("/stock", { product_name: n });
      setNewName("");
      toast.success("Produit ajouté");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const openDetail = async (row) => {
    if (!row.besoin || row.besoin <= 0) return;
    setDetail({ product_name: row.product_name, product_key: row.product_key, loading: true, data: null });
    try {
      const r = await api.get(`/stock/product/${encodeURIComponent(row.product_key)}/projects`);
      setDetail((d) => (d ? { ...d, loading: false, data: r.data } : d));
    } catch (err) {
      toast.error(formatApiError(err));
      setDetail((d) => (d ? { ...d, loading: false, data: { projects: [] } } : d));
    }
  };

  // iter65 : override manuel + revert des valeurs auto-calculées
  const saveOverride = async (row, field, value) => {
    if (!row.id) { toast.error("Ligne stock non enregistrée — ajoutez d'abord le produit."); throw new Error("no id"); }
    try {
      await api.put(`/stock/${row.id}/override`, { field, value });
      toast.success("Valeur manuelle enregistrée");
      await load();
    } catch (err) { toast.error(formatApiError(err)); throw err; }
  };

  const revertOverride = async (row, field) => {
    if (!row.id) return;
    try {
      await api.delete(`/stock/${row.id}/override/${field}`);
      toast.success("Retour au calcul automatique");
      await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter89 : dialog d'ajout d'un produit au stock personnel du technicien
  const [addDialog, setAddDialog] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [addSid, setAddSid] = useState("");
  const [addQty, setAddQty] = useState(1);
  useEffect(() => {
    if (!addDialog?.open) return;
    (async () => {
      try { setCatalog((await api.get("/stock/catalog")).data || []); }
      catch (err) { toast.error(formatApiError(err)); }
    })();
  }, [addDialog?.open]);
  const [addNewMode, setAddNewMode] = useState(false);
  const [addNewName, setAddNewName] = useState("");
  const submitAdd = async () => {
    const qty = Math.max(1, parseInt(addQty, 10) || 0);
    try {
      if (addNewMode) {
        // iter127 : le technicien crée un produit qui n'est pas encore dans le catalogue
        const name = (addNewName || "").trim();
        if (!name) return toast.error("Nom du produit requis");
        await api.post("/stock/tech-create-and-hold", { product_name: name, qty });
        toast.success(`+${qty} ${name} ajouté(s) à votre stock (nouveau produit)`);
      } else {
        if (!addSid) return toast.error("Choisissez un produit");
        await api.post(`/stock/${addSid}/holder-adjust`, { delta: qty });
        const p = catalog.find((c) => c.id === addSid);
        toast.success(`+${qty} ${p?.product_name || ""} ajouté(s) à votre stock`);
      }
      setAddDialog(null); setAddSid(""); setAddQty(1); setAddNewMode(false); setAddNewName("");
      await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter77 : le technicien met à jour SA propre quantité en absolu.
  // On envoie un delta au endpoint holder-adjust (positif ou négatif).
  const adjustMyHolder = async (row, newQty) => {
    if (!row.id) return;
    const delta = Math.round(newQty - (row.qty || 0));
    if (delta === 0) return;
    try {
      await api.post(`/stock/${row.id}/holder-adjust`, { delta });
      toast.success(delta > 0 ? `+${delta} enregistré(s) sur ${row.product_name}` : `${delta} enregistré(s) sur ${row.product_name}`);
      await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter207 : renommage d'un produit créé par le technicien lui-même.
  const renameMyProduct = async (row, newName) => {
    if (!row.id) return;
    try {
      await api.put(`/stock/${row.id}/rename`, { product_name: newName });
      toast.success(`Produit renommé : « ${newName} »`);
      await load();
    } catch (err) {
      toast.error(formatApiError(err));
      throw err;
    }
  };

  // iter82 : admin fixe la quantité d'un holder (technicien) directement depuis la section groupée.
  const setHolderQty = async (sid, userId, name, quantity, productName) => {
    try {
      await api.post(`/stock/${sid}/holder`, { user_id: userId, name, quantity: Math.max(0, Math.round(quantity)) });
      toast.success(`${productName} · ${name} → ${quantity}`);
      await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter82 : regroupement holders par technicien pour la vue admin
  const holdersByTech = useMemo(() => {
    if (isTechnicien) return [];
    const map = new Map();
    for (const r of rows) {
      for (const h of (r.holders || [])) {
        const uid = h.user_id; if (!uid) continue;
        const qty = Number(h.qty || 0);
        if (qty <= 0) continue;
        if (!map.has(uid)) map.set(uid, { user_id: uid, name: h.name || "Technicien", items: [] });
        map.get(uid).items.push({
          sid: r.id, product_key: r.product_key, product_name: r.product_name, qty,
        });
      }
    }
    return Array.from(map.values())
      .map(t => ({ ...t, items: t.items.sort((a,b) => (a.product_name||"").localeCompare(b.product_name||"")) }))
      .sort((a,b) => (a.name||"").localeCompare(b.name||""));
  }, [rows, isTechnicien]);

  // iter68 : vue Technicien — 3 sections indépendantes (mon stock / autres techs / société)
  if (isTechnicien && techPayload) {
    const s = techPayload.sections || {};
    const mine = s.mine || [];
    const others = s.others || [];
    const company = s.company || [];
    const nothing = !techPayload.can_view_own && !techPayload.can_view_others && !techPayload.can_view_company;
    return (
      <div className="p-4 md:p-8 max-w-[1400px]" data-testid="stock-technicien-view">
        <div className="mb-6">
          <p className="overline">Inventaire</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Stock</h1>
          <p className="text-sm text-slate-500 mt-2 max-w-2xl">
            Vue technicien — ce que vous détenez, ce que les autres techniciens ont, et le stock disponible au dépôt société.
          </p>
        </div>
        {loading && <p className="text-sm text-slate-500" data-testid="stock-tech-loading">Chargement…</p>}
        {nothing && !loading && (
          <Card className="p-8 text-center border-amber-200 bg-amber-50/50" data-testid="stock-tech-empty-perms">
            <Boxes size={32} className="inline-block mb-3 text-amber-500" />
            <p className="text-sm text-slate-700 font-medium">Aucune section de stock n'a été activée pour votre compte.</p>
            <p className="text-xs text-slate-500 mt-1">Demandez à un administrateur d'activer au moins l'une des visibilités : « son stock », « stocks des autres techniciens » ou « stock société ».</p>
          </Card>
        )}
        {!nothing && !loading && (
          <div className="space-y-6">
            {techPayload.can_view_own && (
              <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="stock-tech-mine">
                <div className="p-4 border-b border-slate-200 flex items-center gap-2 bg-indigo-50/40">
                  <UserIcon size={16} className="text-indigo-600" />
                  <p className="font-display text-base font-semibold">Mon stock</p>
                  <span className="ml-auto text-xs text-slate-500">{mine.length} produit{mine.length > 1 ? "s" : ""}</span>
                  <button
                    type="button"
                    onClick={() => setAddDialog({ open: true })}
                    className="text-xs px-2 py-1 rounded-md border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 inline-flex items-center gap-1"
                    data-testid="stock-tech-add-btn"
                  >
                    <Plus size={12} /> Ajouter un produit
                  </button>
                </div>
                {mine.length === 0 ? (
                  <p className="p-6 text-sm text-slate-500 text-center">Vous ne détenez actuellement aucun matériel.</p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {mine.map((r) => (
                      <li key={r.product_key} className="p-3.5 flex items-center gap-3" data-testid={`stock-tech-mine-${r.product_key}`}>
                        <div className="flex-1 min-w-0">
                          {/* iter207 : renommage inline autorisé sur les produits créés par le technicien lui-même */}
                          <ProductNameCell
                            row={r}
                            canRename={!!r.created_by_technician_by_me}
                            onRename={renameMyProduct}
                            testId={`stock-tech-mine-name-${r.product_key}`}
                          />
                          {r.besoin > 0 && <p className="text-[11px] text-amber-700">Besoin chantiers : {r.besoin}</p>}
                        </div>
                        {/* iter77 : édition inline directe pour le technicien de sa propre quantité */}
                        <NumberEditor
                          value={r.qty}
                          onCommit={(n) => adjustMyHolder(r, n)}
                          disabled={!r.id}
                          testId={`stock-tech-mine-qty-${r.product_key}`}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
            {techPayload.can_view_others && (
              <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="stock-tech-others">
                <div className="p-4 border-b border-slate-200 flex items-center gap-2 bg-slate-50/60">
                  <HardHat size={16} className="text-slate-500" />
                  <p className="font-display text-base font-semibold">Stocks des autres techniciens</p>
                  <span className="ml-auto text-xs text-slate-500">{others.length} technicien{others.length > 1 ? "s" : ""}</span>
                </div>
                {others.length === 0 ? (
                  <p className="p-6 text-sm text-slate-500 text-center">Aucun autre technicien n'a de stock personnel actuellement.</p>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {others.map((o) => (
                      <div key={o.user_id} className="p-3.5" data-testid={`stock-tech-other-${o.user_id}`}>
                        <p className="font-semibold text-slate-900 mb-2 flex items-center gap-2"><HardHat size={13} className="text-amber-600" />{o.name}</p>
                        <ul className="space-y-1 pl-6">
                          {o.rows.map((r) => (
                            <li key={r.product_key} className="text-sm flex items-center justify-between border-l-2 border-slate-200 pl-3">
                              <span className="text-slate-700 truncate">{r.product_name}</span>
                              <span className="font-display font-semibold tabular-nums text-slate-900 ml-3">{r.qty}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}
            {techPayload.can_view_company && (
              <Card className="border-slate-200 shadow-sm overflow-hidden" data-testid="stock-tech-company">
                <div className="p-4 border-b border-slate-200 flex items-center gap-2 bg-emerald-50/40">
                  <Boxes size={16} className="text-emerald-700" />
                  <p className="font-display text-base font-semibold">Stock société (dépôt)</p>
                  <span className="ml-auto text-xs text-slate-500">{company.length} produit{company.length > 1 ? "s" : ""}</span>
                </div>
                {company.length === 0 ? (
                  <p className="p-6 text-sm text-slate-500 text-center">Aucun produit disponible au dépôt société.</p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {company.map((r) => (
                      <li key={r.product_key} className={`p-3.5 flex items-center gap-3 ${r.low_stock ? "bg-amber-50/40" : ""}`} data-testid={`stock-tech-company-${r.product_key}`}>
                        <StatusDot status={r.status} />
                        {r.low_stock && <AlertCircle size={14} className="text-amber-600 shrink-0" aria-label="Stock bas" />}
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-slate-900 truncate">{r.product_name}{r.low_stock && <span className="ml-2 text-[10px] font-semibold text-amber-700 uppercase tracking-wider">Stock bas</span>}</p>
                          <div className="flex flex-wrap gap-x-3 text-[11px] text-slate-500 mt-0.5">
                            {r.besoin > 0 && <span>Besoin : {r.besoin}</span>}
                            {r.commande_en_cours > 0 && <span>Commande : {r.commande_en_cours}</span>}
                          </div>
                        </div>
                        <p className={`font-display text-xl font-semibold tabular-nums ${r.low_stock ? "text-amber-700" : "text-emerald-700"}`}>{r.qty}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
          </div>
        )}
        <p className="text-[11px] text-slate-500 mt-6">
          Modifiez librement la quantité de <strong>votre</strong> stock — la synchronisation avec l'administrateur est automatique. La modification du stock société ou de celui d'un autre technicien reste réservée à un administrateur.
        </p>
        {addDialog?.open && (
          <Dialog open onOpenChange={(o) => { if (!o) { setAddDialog(null); setAddSid(""); setAddQty(1); setAddNewMode(false); setAddNewName(""); } }}>
            <DialogContent className="max-w-md" data-testid="stock-tech-add-dialog">
              <DialogHeader><DialogTitle>Ajouter un produit à mon stock</DialogTitle></DialogHeader>
              <div className="space-y-3 mt-2">
                {/* iter127 : toggle mode existing / new */}
                <div className="flex gap-1 p-1 rounded-lg bg-slate-100 text-xs" data-testid="stock-tech-add-mode">
                  <button type="button" onClick={() => setAddNewMode(false)} className={`flex-1 py-1.5 rounded-md transition ${!addNewMode ? "bg-white text-slate-900 shadow-sm font-medium" : "text-slate-500 hover:text-slate-800"}`} data-testid="stock-tech-add-mode-existing">Produit existant</button>
                  <button type="button" onClick={() => setAddNewMode(true)} className={`flex-1 py-1.5 rounded-md transition ${addNewMode ? "bg-white text-slate-900 shadow-sm font-medium" : "text-slate-500 hover:text-slate-800"}`} data-testid="stock-tech-add-mode-new">Nouveau produit</button>
                </div>
                {!addNewMode ? (
                  <label className="block">
                    <span className="text-xs text-slate-600 mb-1 block">Produit (catalogue société)</span>
                    <select
                      value={addSid}
                      onChange={(e) => setAddSid(e.target.value)}
                      className="w-full h-10 px-3 rounded-md border border-slate-200 text-sm bg-white"
                      data-testid="stock-tech-add-product"
                    >
                      <option value="">— Choisir un produit —</option>
                      {catalog.map((c) => (<option key={c.id} value={c.id}>{c.product_name}</option>))}
                    </select>
                  </label>
                ) : (
                  <label className="block">
                    <span className="text-xs text-slate-600 mb-1 block">Nom du nouveau produit</span>
                    <Input
                      value={addNewName}
                      onChange={(e) => setAddNewName(e.target.value)}
                      placeholder="ex: Colliers de serrage 60mm"
                      data-testid="stock-tech-add-new-name"
                    />
                    <p className="text-[10px] text-slate-400 mt-1">Créé dans le catalogue société avec 0 au dépôt — l'admin peut valider ensuite.</p>
                  </label>
                )}
                <label className="block">
                  <span className="text-xs text-slate-600 mb-1 block">Quantité en votre possession</span>
                  <Input type="number" min="1" value={addQty} onChange={(e) => setAddQty(e.target.value)} data-testid="stock-tech-add-qty" />
                </label>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => { setAddDialog(null); setAddSid(""); setAddQty(1); setAddNewMode(false); setAddNewName(""); }}>Annuler</Button>
                  <Button onClick={submitAdd} disabled={(addNewMode ? !addNewName.trim() : !addSid) || !addQty} data-testid="stock-tech-add-submit">Ajouter</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="mb-6 flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="overline">Inventaire</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Stock</h1>
          <p className="text-sm text-slate-500 mt-2 max-w-2xl">
            Besoin des chantiers actifs (À&nbsp;planifier + En&nbsp;cours) et stock physique.
            Le « à commander » est recalculé automatiquement.
          </p>
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Nouveau produit…"
              className="h-9 w-56"
              onKeyDown={(e) => { if (e.key === "Enter") addManual(); }}
              data-testid="stock-new-name"
            />
            <Button onClick={addManual} size="sm" data-testid="stock-add-btn"><Plus size={14} className="mr-1" /> Ajouter</Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <Card className="p-4 border-slate-200 shadow-sm flex items-center gap-3" data-testid="stock-stat-to-order">
          <div className="h-10 w-10 rounded-lg bg-red-50 text-red-700 grid place-items-center"><AlertTriangle size={18} /></div>
          <div>
            <p className="overline">À commander</p>
            <p className="font-display text-2xl font-semibold">{totals.toOrder}</p>
          </div>
        </Card>
        <Card className={`p-4 border shadow-sm flex items-center gap-3 ${totals.low > 0 ? "border-amber-400 bg-amber-50/50" : "border-slate-200"}`} data-testid="stock-stat-low">
          <div className="h-10 w-10 rounded-lg bg-amber-100 text-amber-700 grid place-items-center"><AlertCircle size={18} /></div>
          <div>
            <p className="overline">Stock bas</p>
            <p className={`font-display text-2xl font-semibold ${totals.low > 0 ? "text-amber-800" : "text-slate-900"}`}>{totals.low}</p>
            <p className="text-[10px] text-slate-500">seuil par produit</p>
          </div>
        </Card>
        <Card className="p-4 border-slate-200 shadow-sm flex items-center gap-3" data-testid="stock-stat-covered">
          <div className="h-10 w-10 rounded-lg bg-emerald-50 text-emerald-700 grid place-items-center"><PackageCheck size={18} /></div>
          <div>
            <p className="overline">Stock couvert</p>
            <p className="font-display text-2xl font-semibold">{totals.covered}</p>
          </div>
        </Card>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-[200px]">
            <Search size={16} className="text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un produit…" className="border-0 shadow-none focus-visible:ring-0 h-9 px-0" data-testid="stock-search" />
            {loading && <Loader2 size={14} className="animate-spin text-slate-400" />}
          </div>
        </div>
        <div className="md:hidden divide-y divide-slate-100" data-testid="stock-mobile-list">
          {filtered.length === 0 && !loading && (
            <p className="p-8 text-center text-sm text-slate-500">Aucun produit à afficher.</p>
          )}
          {filtered.map((r) => (
            <div key={r.product_key} className={`p-4 ${r.low_stock ? "bg-amber-50/40" : ""}`} data-testid={`stock-card-${r.product_key}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <StatusDot status={r.status} />
                  <p className="font-semibold text-slate-900 break-words">{r.product_name}</p>
                  {r.low_stock && <AlertCircle size={13} className="text-amber-600 shrink-0" />}
                </div>
                {canEdit && r.id && (
                  <button onClick={() => del(r)} className="h-8 w-8 shrink-0 grid place-items-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50" aria-label="Supprimer" data-testid={`m-stock-delete-${r.product_key}`}><Trash2 size={14} /></button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Stock physique</p>
                  <NumberEditor value={r.stock_disponible} onCommit={(n) => updateField(r, { stock_disponible: n })} disabled={!canEdit} testId={`m-stock-dispo-${r.product_key}`} />
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Besoin chantiers</p>
                  <OverrideCell value={r.besoin} autoValue={r.besoin_auto ?? r.besoin} override={(r.manual_overrides || {}).besoin} canEdit={canEdit && !!r.id}
                    onSave={(n) => saveOverride(r, "besoin", n)} onRevert={() => revertOverride(r, "besoin")} testId={`m-stock-besoin-${r.product_key}`} tone="besoin"
                    extraLink={!(r.manual_overrides || {}).besoin && r.besoin > 0 ? () => openDetail(r) : null} />
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">À commander</p>
                  <OverrideCell value={r.reste_a_commander} autoValue={r.reste_a_commander_auto ?? r.reste_a_commander} override={(r.manual_overrides || {}).reste_a_commander} canEdit={canEdit && !!r.id}
                    onSave={(n) => saveOverride(r, "reste_a_commander", n)} onRevert={() => revertOverride(r, "reste_a_commander")} testId={`m-stock-reste-${r.product_key}`} tone="reste" />
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Alerte si ≤</p>
                  <Input type="number" min="0" defaultValue={r.low_stock_threshold ?? 2}
                    onBlur={(e) => { const n = Math.max(0, parseInt(e.target.value, 10) || 0); if (n !== (r.low_stock_threshold ?? 2)) updateField(r, { low_stock_threshold: n }); }}
                    onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                    className="h-8 w-20 text-center text-sm bg-white" disabled={!canEdit} data-testid={`m-stock-threshold-${r.product_key}`} />
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline w-6"></th>
                <th className="px-4 py-3 overline">Produit</th>
                <th className="px-4 py-3 overline text-right">Stock physique</th>
                <th className="px-4 py-3 overline text-right">Besoin chantiers</th>
                <th className="px-4 py-3 overline text-right">À commander</th>
                <th className="px-4 py-3 overline text-right" title="Seuil d'alerte stock bas (par produit) — 0 pour désactiver">Alerte ≤</th>
                <th className="px-4 py-3 overline text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && !loading && (
                <tr><td colSpan={7} className="p-10 text-center text-slate-500">
                  <Boxes size={22} className="inline-block mb-2 text-slate-400" />
                  <p>Aucun produit à afficher. Créez une vente avec quantités pour alimenter automatiquement les besoins.</p>
                </td></tr>
              )}
              {filtered.map((r) => (
                <tr key={r.product_key} className={`border-b border-slate-100 last:border-0 hover:bg-slate-50/40 ${r.low_stock ? "bg-amber-50/30" : ""}`} data-testid={`stock-row-${r.product_key}`}>
                  <td className="px-4 py-3 align-middle">
                    <div className="flex items-center gap-1.5">
                      <StatusDot status={r.status} />
                      {r.low_stock && (
                        <AlertCircle size={12} className="text-amber-600" aria-label="Stock bas (≤ 2)" data-testid={`stock-low-badge-${r.product_key}`}>
                          <title>Stock bas — plus que {r.stock_disponible} unité(s) au dépôt</title>
                        </AlertCircle>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-900">{r.product_name}</td>
                  <td className="px-4 py-3 text-right">
                    <NumberEditor
                      value={r.stock_disponible}
                      onCommit={(n) => updateField(r, { stock_disponible: n })}
                      disabled={!canEdit}
                      testId={`stock-dispo-${r.product_key}`}
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {(() => {
                      const ov = (r.manual_overrides || {}).besoin;
                      const editable = canEdit && !!r.id;
                      return (
                        <OverrideCell
                          value={r.besoin}
                          autoValue={r.besoin_auto ?? r.besoin}
                          override={ov}
                          canEdit={editable}
                          onSave={(n) => saveOverride(r, "besoin", n)}
                          onRevert={() => revertOverride(r, "besoin")}
                          testId={`stock-besoin-${r.product_key}`}
                          tone="besoin"
                          extraLink={!ov && r.besoin > 0 ? () => openDetail(r) : null}
                        />
                      );
                    })()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <OverrideCell
                      value={r.reste_a_commander}
                      autoValue={r.reste_a_commander_auto ?? r.reste_a_commander}
                      override={(r.manual_overrides || {}).reste_a_commander}
                      canEdit={canEdit && !!r.id}
                      onSave={(n) => saveOverride(r, "reste_a_commander", n)}
                      onRevert={() => revertOverride(r, "reste_a_commander")}
                      testId={`stock-reste-${r.product_key}`}
                      tone="reste"
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1.5" title="Seuil d'alerte — 0 pour désactiver l'alerte sur ce produit">
                      <Input
                        type="number"
                        min="0"
                        defaultValue={r.low_stock_threshold ?? 2}
                        onBlur={(e) => {
                          const n = Math.max(0, parseInt(e.target.value, 10) || 0);
                          if (n !== (r.low_stock_threshold ?? 2)) updateField(r, { low_stock_threshold: n });
                        }}
                        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                        className="w-14 h-7 text-center text-sm px-1"
                        disabled={!canEdit}
                        data-testid={`stock-threshold-${r.product_key}`}
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {canEdit && r.id && (
                      <button
                        onClick={() => del(r)}
                        className="ml-2 h-8 w-8 inline-grid place-items-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition align-middle"
                        title="Supprimer la ligne (les besoins restent calculés depuis les ventes)"
                        aria-label="Supprimer"
                        data-testid={`stock-delete-${r.product_key}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-[11px] text-slate-500 mt-4">
        <strong>Formules :</strong> À&nbsp;commander = max(0, Besoin − Stock physique).
        Les produits ne sont <strong>jamais</strong> déduits du stock physique tant que le chantier n'est pas terminé.
        La ligne devient <span className="text-red-600 font-medium">🔴 rouge</span> si un produit manque, <span className="text-amber-600 font-medium">🟠 orange</span> si partiellement couvert, <span className="text-emerald-600 font-medium">🟢 verte</span> si tout est couvert.
        Un badge <AlertCircle size={10} className="inline text-amber-600" /> ambre signale un stock bas selon le seuil configuré par produit.
        {canEdit && (
          <> · <span className="inline-flex items-center gap-1 text-amber-700 font-medium"><Pencil size={10} />Override admin</span> : cliquez sur l'icône crayon d'une valeur calculée pour la remplacer manuellement, puis <RotateCcw size={10} className="inline" /> pour revenir au calcul automatique.</>
        )}
      </p>

      {/* iter82 : Stock personnel par technicien (vue admin) */}
      {canEdit && holdersByTech.length > 0 && (
        <Card className="border-slate-200 shadow-sm overflow-hidden mt-6" data-testid="stock-per-tech">
          <div className="p-4 border-b border-slate-200 flex items-center gap-2">
            <HardHat size={16} className="text-amber-600" />
            <p className="font-display text-lg font-semibold">Stock par technicien</p>
            <span className="ml-auto text-xs text-slate-500">{holdersByTech.length} technicien{holdersByTech.length > 1 ? "s" : ""} avec du matériel</span>
          </div>
          <div className="divide-y divide-slate-100">
            {holdersByTech.map((t) => (
              <div key={t.user_id} className="p-4" data-testid={`stock-per-tech-${t.user_id}`}>
                <p className="font-display font-semibold text-slate-900 flex items-center gap-2 mb-2.5">
                  <HardHat size={13} className="text-amber-600" />
                  {t.name}
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 font-normal">· {t.items.length} produit{t.items.length > 1 ? "s" : ""}</span>
                </p>
                <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                  {t.items.map((it) => (
                    <li key={`${t.user_id}-${it.product_key}`} className="flex items-center gap-2 border border-slate-100 rounded-md px-3 py-2 hover:bg-slate-50/40 transition" data-testid={`stock-per-tech-${t.user_id}-${it.product_key}`}>
                      <span className="flex-1 min-w-0 text-sm truncate">{it.product_name}</span>
                      <NumberEditor
                        value={it.qty}
                        onCommit={(n) => setHolderQty(it.sid, t.user_id, t.name, n, it.product_name)}
                        testId={`stock-per-tech-qty-${t.user_id}-${it.product_key}`}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 p-3 border-t border-slate-100">
            Éditez directement la quantité d'un produit détenu par un technicien — la valeur remplace l'existante et se synchronise instantanément côté technicien.
          </p>
        </Card>
      )}

      {/* iter49 : drill-down des chantiers qui consomment ce produit */}
      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="stock-detail-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-xl flex items-center gap-2">
              <ClipboardList size={18} className="text-slate-500" />
              Besoin chantiers · {detail?.product_name}
            </DialogTitle>
            {detail?.data && (
              <p className="text-xs text-slate-500">
                Besoin total : <span className="font-semibold text-slate-800">{detail.data.total_needed || 0}</span> · {(detail.data.projects || []).length} chantier{(detail.data.projects || []).length > 1 ? "s" : ""} actif{(detail.data.projects || []).length > 1 ? "s" : ""}
              </p>
            )}
          </DialogHeader>
          <div className="overflow-y-auto -mx-6 px-6 pb-2">
            {detail?.loading && (
              <div className="py-10 text-center text-slate-500"><Loader2 size={16} className="inline animate-spin mr-2" /> Chargement…</div>
            )}
            {!detail?.loading && (!detail?.data || (detail.data.projects || []).length === 0) && (
              <p className="text-sm text-slate-500 py-10 text-center" data-testid="stock-detail-empty">
                Aucun chantier actif n'utilise ce produit actuellement.
              </p>
            )}
            <ul className="divide-y divide-slate-100">
              {(detail?.data?.projects || []).map((p) => (
                <li key={p.project_id} className="py-3 flex items-start justify-between gap-3" data-testid={`stock-detail-row-${p.project_id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-900 truncate">{p.client_name}</p>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${STATUS_CLS[p.status] || "bg-slate-100 text-slate-600 border-slate-200"}`}>{STATUS_LABEL[p.status] || p.status}</span>
                      <span className="text-[10px] text-slate-400 tabular-nums">{fmtShortDate(p.scheduled_date)}{p.duration_days > 1 ? ` · ${p.duration_days} j` : ""}</span>
                    </div>
                    {p.service && <p className="text-xs text-slate-600 truncate mt-0.5" title={p.service}>{p.service}</p>}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                      {p.commercial && (
                        <span className="inline-flex items-center gap-1">
                          <UserIcon size={10} className="text-indigo-500" />
                          {p.commercial}{p.commercial_2 ? ` + ${p.commercial_2}` : ""}
                        </span>
                      )}
                      {(p.techniciens || []).length > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <HardHat size={10} className="text-amber-600" />
                          {(p.techniciens || []).join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-display text-lg font-semibold tabular-nums text-slate-900">{p.quantity}<span className="text-xs text-slate-400 ml-1">×</span></p>
                    <p className="text-[11px] text-slate-500 tabular-nums">{fmtEur(p.amount)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
