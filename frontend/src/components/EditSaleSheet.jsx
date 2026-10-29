import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { ChequeInstallmentsSelect } from "@/components/ChequeInstallmentsSelect";
import { ProspecteurField, prospecteurPayload } from "@/components/ProspecteurField";
import { SALE_STATUSES, formatRate, PAYMENT_OPTIONS, CHEQUE_INSTALLMENTS, SOURCES, orderStatuses, resolveStatusesFromPayload } from "@/lib/saleConstants";
import useTeam from "@/lib/useTeam";
import useCommissionRates from "@/lib/useCommissionRates";
import { useSettings } from "@/contexts/SettingsContext";

export default function EditSaleSheet({ sale, open, onOpenChange, onSaved }) {
  const { commerciaux } = useTeam();
  const commissionRates = useCommissionRates();
  const { settings } = useSettings();
  // iter163 : mêmes statuts que la page Ventes — charge /api/sale-statuses (custom
  // + actifs) + respect de l'ordre `sale_status_order`. Fallback sur SALE_STATUSES.
  const [saleStatusesPayload, setSaleStatusesPayload] = useState(null);
  useEffect(() => {
    let cancel = false;
    api.get("/sale-statuses").then((r) => { if (!cancel) setSaleStatusesPayload(r.data); }).catch(() => {});
    const onUpd = () => { api.get("/sale-statuses").then((r) => { if (!cancel) setSaleStatusesPayload(r.data); }).catch(() => {}); };
    window.addEventListener("kylot:settings-updated", onUpd);
    return () => { cancel = true; window.removeEventListener("kylot:settings-updated", onUpd); };
  }, []);
  const statuses = React.useMemo(() => {
    if (Array.isArray(saleStatusesPayload) && saleStatusesPayload.length) {
      const list = resolveStatusesFromPayload(saleStatusesPayload).filter((s) => s.active);
      const order = settings?.sale_status_order;
      if (!Array.isArray(order) || !order.length) return list;
      const map = new Map(list.map((s) => [s.value, s]));
      const seen = new Set();
      const out = [];
      for (const v of order) { const it = map.get(v); if (it && !seen.has(v)) { out.push(it); seen.add(v); } }
      for (const s of list) if (!seen.has(s.value)) out.push(s);
      return out;
    }
    return orderStatuses(settings?.sale_status_order);
  }, [saleStatusesPayload, settings?.sale_status_order]);
  const [form, setForm] = useState(null);
  const [client, setClient] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !sale) return;
    setForm({
      bdc: sale.bdc || "",
      service: sale.service || "",
      amount: sale.amount ?? "",
      payment_method: sale.payment_method || "",
      payment_installments: sale.payment_installments || 1,
      financement_amount: sale.financement_amount ?? "",
      comptant_installments: sale.comptant_installments || 1,
      commission_rate: sale.commission_rate ?? 0.10,
      commission_rate_2: sale.commission_rate_2 ?? null,
      commission_type: sale.commission_type || "fixed",
      commission_type_2: sale.commission_type_2 || (sale.commission_type === "evolutive_ca" ? "evolutive_ca" : "fixed"),
      evolutive_ca_threshold: sale.evolutive_ca_threshold ?? 30000,
      evolutive_rate_below: sale.evolutive_rate_below ?? 0.10,
      evolutive_rate_above: sale.evolutive_rate_above ?? 0.13,
      discount_percent: sale.discount_percent ?? null,
      commercial: sale.commercial || "",
      commercial_2: sale.commercial_2 || "",
      is_de: !!sale.is_de,
      commercial_share: sale.commercial_share ?? 0.5,
      source: sale.source || "",
      sale_date: sale.sale_date || "",
      desired_intervention_date: sale.desired_intervention_date || "",
      status: sale.status || "commercial_cheque",
      notes: sale.notes || "",
      prospecteur_id: sale.prospecteur_id || "",
      prospecteur_commission: sale.prospecteur_commission ?? "",
    });
    api.get("/clients").then((r) => {
      const c = r.data.find((x) => x.id === sale.client_id);
      if (c) setClient({ ...c });
    }).catch(() => {});
  }, [open, sale]);

  if (!sale || !form) return null;

  const save = async () => {
    setSaving(true);
    try {
      if (client) {
        await api.put(`/clients/${client.id}`, {
          name: client.name, phone: client.phone || "", email: client.email || "",
          address: client.address || "", postal_code: client.postal_code || "",
          city: client.city || "", notes: client.notes || "",
        });
      }
      await api.put(`/sales/${sale.id}`, {
        bdc: form.bdc,
        service: form.service,
        amount: parseFloat(form.amount || 0),
        payment_method: form.payment_method,
        payment_installments: parseInt(form.payment_installments || 1, 10),
        financement_amount: form.payment_method === "financement" && form.financement_amount !== "" ? parseFloat(form.financement_amount) : null,
        comptant_installments: parseInt(form.comptant_installments || 1, 10),
        commission_rate: parseFloat(form.commission_rate),
        commission_rate_2: !form.is_de ? null : (form.commission_rate_2 != null ? parseFloat(form.commission_rate_2) : (form.commission_type_2 === "evolutive_ca" ? parseFloat(form.evolutive_rate_below ?? 0.10) : parseFloat(form.commission_rate) || 0)),
        commission_type: form.commission_type || "fixed",
        commission_type_2: form.is_de ? (form.commission_type_2 || "fixed") : null,
        evolutive_ca_threshold: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? (parseFloat(form.evolutive_ca_threshold) || 30000) : null,
        evolutive_rate_below: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? parseFloat(form.evolutive_rate_below ?? 0.10) : null,
        evolutive_rate_above: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? parseFloat(form.evolutive_rate_above ?? 0.13) : null,
        discount_percent: form.commission_type === "evolutive_discount" ? (form.discount_percent != null ? parseFloat(form.discount_percent) : null) : null,
        commercial: form.commercial,
        commercial_2: form.is_de ? form.commercial_2 : "",
        is_de: !!form.is_de,
        commercial_share: form.is_de ? parseFloat(form.commercial_share ?? 0.5) : 1.0,
        source: form.source,
        // iter214 : force null si vide, sinon Pydantic pattern échoue avec un message technique
        sale_date: form.sale_date || null,
        desired_intervention_date: form.desired_intervention_date || null,
        status: form.status,
        notes: form.notes,
        ...prospecteurPayload(form),
      });
      toast.success("Vente mise à jour");
      onOpenChange(false);
      onSaved?.();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    if (!window.confirm("Supprimer cette vente ?")) return;
    try {
      await api.delete(`/sales/${sale.id}`);
      toast.success("Vente supprimée");
      onOpenChange(false);
      onSaved?.();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const showInstallments = form.payment_method === "cheque";
  const showFinancement = form.payment_method === "financement";
  const total = parseFloat(form.amount || 0);
  const fin = parseFloat(form.financement_amount || 0);
  const comptantPart = Math.max(0, total - (showFinancement ? fin : 0));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-xl overflow-y-auto" data-testid="edit-sale-sheet">
        <SheetHeader>
          <SheetTitle className="font-display text-2xl">Modifier la vente</SheetTitle>
          <p className="text-sm text-slate-500">Les modifications sur le client s'appliquent partout dans l'application.</p>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Date</Label>
              <Input type="date" value={form.sale_date} onChange={(e) => setForm({ ...form, sale_date: e.target.value })} data-testid="edit-sale-date" />
            </div>
            <div className="space-y-1.5"><Label>BDC</Label>
              <Input value={form.bdc} onChange={(e) => setForm({ ...form, bdc: e.target.value })} data-testid="edit-sale-bdc" />
            </div>
          </div>

          {client && (
            <div className="border border-slate-200 rounded-lg p-4 space-y-2 bg-slate-50/50">
              <p className="overline">Client</p>
              <Input placeholder="Nom / Prénom" value={client.name || ""} onChange={(e) => setClient({ ...client, name: e.target.value })} data-testid="edit-client-name" />
              <Input placeholder="Téléphone" value={client.phone || ""} onChange={(e) => setClient({ ...client, phone: e.target.value })} data-testid="edit-client-phone" />
              <Input placeholder="Adresse" value={client.address || ""} onChange={(e) => setClient({ ...client, address: e.target.value })} data-testid="edit-client-address" />
              <div className="grid grid-cols-[120px_1fr] gap-2">
                <Input placeholder="Code postal" value={client.postal_code || ""} onChange={(e) => setClient({ ...client, postal_code: e.target.value })} data-testid="edit-client-postal" />
                <Input placeholder="Ville" value={client.city || ""} onChange={(e) => setClient({ ...client, city: e.target.value })} data-testid="edit-client-city" />
              </div>
              <Input placeholder="Email" value={client.email || ""} onChange={(e) => setClient({ ...client, email: e.target.value })} />
            </div>
          )}

          <div className="space-y-1.5"><Label>Produits</Label>
            <Textarea rows={2} value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} data-testid="edit-sale-service" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Montant HT (€)</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="edit-sale-amount" />
            </div>
            <div className="space-y-1.5"><Label>Règlement</Label>
              <Select value={form.payment_method || "__none"} onValueChange={(v) => setForm({ ...form, payment_method: v === "__none" ? "" : v, payment_installments: v === "cheque" ? form.payment_installments || 1 : 1 })}>
                <SelectTrigger data-testid="edit-sale-payment"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {PAYMENT_OPTIONS.map((o) => (<SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {showInstallments && (
            <div className="space-y-1.5">
              <Label>Chèque en combien de fois ?</Label>
              <ChequeInstallmentsSelect key={sale?.id} testid="edit-sale-installments" value={form.payment_installments} onChange={(v) => setForm({ ...form, payment_installments: v })} />
              {total > 0 && form.payment_installments > 1 && (
                <p className="text-xs text-slate-500">Soit {(total / form.payment_installments).toFixed(2)} € par chèque × {form.payment_installments}</p>
              )}
            </div>
          )}

          {showFinancement && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 space-y-2" data-testid="edit-sale-financement-block">
              <Label className="text-xs">Montant financé (€)</Label>
              <Input type="number" step="0.01" min="0" max={total || undefined}
                value={form.financement_amount}
                onChange={(e) => setForm({ ...form, financement_amount: e.target.value })}
                placeholder="Ex: 10000"
                data-testid="edit-sale-financement-amount" />
              {total > 0 && (
                <div className="text-xs text-slate-700 space-y-0.5">
                  <p>Montant total : <span className="font-semibold">{total.toFixed(2)} €</span></p>
                  <p>Financement : <span className="font-semibold">{(fin || 0).toFixed(2)} €</span></p>
                  <p className="text-emerald-800">Part au comptant : <span className="font-semibold">{comptantPart.toFixed(2)} €</span></p>
                </div>
              )}
              {comptantPart > 0 && (
                <div className="pt-2">
                  <Label className="text-xs">Part comptant en combien de fois ?</Label>
                  <Select value={String(form.comptant_installments)} onValueChange={(v) => setForm({ ...form, comptant_installments: parseInt(v, 10) })}>
                    <SelectTrigger className="h-8" data-testid="edit-sale-comptant-installments"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[1,2,3,4,6,12].map((n) => (<SelectItem key={n} value={String(n)}>{n === 1 ? "En 1 fois" : `${n} fois`} · {(comptantPart / n).toFixed(2)} € / échéance</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}

          {form.payment_method && !showFinancement && !showInstallments && (
            <div className="space-y-1.5">
              <Label>Réglement en combien de fois ?</Label>
              <Select value={String(form.comptant_installments)} onValueChange={(v) => setForm({ ...form, comptant_installments: parseInt(v, 10) })}>
                <SelectTrigger data-testid="edit-sale-comptant-installments"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[1,2,3,4,6,12].map((n) => (<SelectItem key={n} value={String(n)}>{n === 1 ? "En 1 fois" : `${n} fois`}{total > 0 ? ` · ${(total / n).toFixed(2)} € / échéance` : ""}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Type de commission{form.is_de ? " commercial 1" : ""}</Label>
              <Select value={form.commission_type || "fixed"} onValueChange={(v) => setForm({ ...form, commission_type: v })}>
                <SelectTrigger data-testid="edit-sale-commission-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="fixed">Fixe</SelectItem>
                  <SelectItem value="evolutive_ca">Évolutive selon CA</SelectItem>
                  <SelectItem value="evolutive_discount">Évolutive selon remise</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.commission_type === "evolutive_discount" && (
              <div className="space-y-1.5"><Label>Remise (%)</Label>
                <Input type="number" min="0" max="100" step="0.5" value={form.discount_percent ?? ""} onChange={(e) => setForm({ ...form, discount_percent: e.target.value === "" ? null : parseFloat(e.target.value) })} data-testid="edit-sale-discount-percent" />
              </div>
            )}
          </div>

          {(form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 space-y-2" data-testid="edit-sale-evolutive-block">
              <p className="text-xs text-indigo-900 font-semibold">Palier de bascule automatique (CA mensuel de chaque commercial)</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1"><Label className="text-xs">Seuil CA (€)</Label>
                  <Input type="number" min="0" step="1000" value={form.evolutive_ca_threshold ?? 30000}
                    onChange={(e) => setForm({ ...form, evolutive_ca_threshold: parseFloat(e.target.value) || 0 })} data-testid="edit-sale-evolutive-threshold" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Taux en dessous</Label>
                  <Select value={String(form.evolutive_rate_below ?? 0.10)} onValueChange={(v) => setForm({ ...form, evolutive_rate_below: parseFloat(v) })}>
                    <SelectTrigger data-testid="edit-sale-evolutive-rate-below"><SelectValue /></SelectTrigger>
                    <SelectContent>{commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">Taux au-dessus</Label>
                  <Select value={String(form.evolutive_rate_above ?? 0.13)} onValueChange={(v) => setForm({ ...form, evolutive_rate_above: parseFloat(v) })}>
                    <SelectTrigger data-testid="edit-sale-evolutive-rate-above"><SelectValue /></SelectTrigger>
                    <SelectContent>{commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}</SelectContent>
                  </Select>
                </div>
              </div>
              <p className="text-[11px] text-indigo-700">Le taux est recalculé automatiquement à l'enregistrement pour toutes les ventes du mois{form.is_de ? ", pour les 2 commerciaux" : ""}.</p>
            </div>
          )}

          {(!form.commission_type || form.commission_type === "fixed") && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>{form.is_de ? "Commission commercial 1" : "Commission"}</Label>
              <Select value={String(form.commission_rate)} onValueChange={(v) => setForm({ ...form, commission_rate: parseFloat(v) })}>
                <SelectTrigger data-testid="edit-sale-commission"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Commercial{form.is_de ? " 1" : ""}</Label>
              <Select value={form.commercial || "__none"} onValueChange={(v) => setForm({ ...form, commercial: v === "__none" ? "" : v })}>
                <SelectTrigger data-testid="edit-sale-commercial"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {commerciaux.map((c) => (<SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Source</Label>
              <Select value={form.source || "__none"} onValueChange={(v) => setForm({ ...form, source: v === "__none" ? "" : v })}>
                <SelectTrigger data-testid="edit-sale-source"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {SOURCES.map((s) => (<SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <label className="flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/40 px-3 py-2 cursor-pointer" data-testid="edit-sale-de-toggle">
            <input type="checkbox" checked={!!form.is_de} onChange={(e) => setForm({ ...form, is_de: e.target.checked, commercial_2: e.target.checked ? form.commercial_2 : "", commission_rate_2: e.target.checked ? (form.commission_rate_2 ?? form.commission_rate) : null })} className="rounded border-indigo-300" />
            <div className="text-sm">
              <span className="font-semibold text-indigo-900">Vente en DE (2 commerciaux)</span>
              <span className="text-xs text-indigo-700 ml-2">CA réparti automatiquement 50 / 50 · commissions indépendantes</span>
            </div>
          </label>

          {form.is_de && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Commercial 2</Label>
                <Select value={form.commercial_2 || "__none"} onValueChange={(v) => setForm({ ...form, commercial_2: v === "__none" ? "" : v })}>
                  <SelectTrigger data-testid="edit-sale-commercial-2"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">—</SelectItem>
                    {commerciaux.filter((c) => c.name !== form.commercial).map((c) => (<SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Type de commission commercial 2</Label>
                <Select value={form.commission_type_2 || "fixed"} onValueChange={(v) => setForm({ ...form, commission_type_2: v, commission_rate_2: v === "evolutive_ca" ? null : form.commission_rate_2 })}>
                  <SelectTrigger data-testid="edit-sale-commission-type-2"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fixed">Fixe</SelectItem>
                    <SelectItem value="evolutive_ca">Évolutive selon CA</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Commission commercial 2</Label>
                {form.commission_type_2 === "evolutive_ca" ? (
                  <p className="h-10 flex items-center text-xs text-indigo-800 rounded-md border border-indigo-100 bg-indigo-50/60 px-3" data-testid="edit-sale-commission-2-evolutive">Évolutive selon son propre CA du mois</p>
                ) : (
                <Select value={String(form.commission_rate_2 ?? form.commission_rate ?? 0.10)} onValueChange={(v) => setForm({ ...form, commission_rate_2: parseFloat(v) })}>
                  <SelectTrigger data-testid="edit-sale-commission-2"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}
                  </SelectContent>
                </Select>
                )}
              </div>
              {form.commercial_2 && form.commission_type !== "evolutive_ca" && form.commission_type_2 !== "evolutive_ca" && parseFloat(form.amount || 0) > 0 && (
                <div className="col-span-2 rounded-md bg-indigo-50/60 border border-indigo-100 p-2.5">
                  <p className="text-[11px] text-indigo-800">
                    <strong>{form.commercial || "C1"}</strong> · CA {(parseFloat(form.amount || 0) * 0.5).toLocaleString("fr-FR")} € · Commission <strong>{(parseFloat(form.amount || 0) * 0.5 * (form.commission_rate || 0)).toLocaleString("fr-FR", {maximumFractionDigits: 0})} €</strong> ({formatRate(form.commission_rate || 0)})
                  </p>
                  <p className="text-[11px] text-indigo-800">
                    <strong>{form.commercial_2}</strong> · CA {(parseFloat(form.amount || 0) * 0.5).toLocaleString("fr-FR")} € · Commission <strong>{(parseFloat(form.amount || 0) * 0.5 * (form.commission_rate_2 ?? form.commission_rate ?? 0)).toLocaleString("fr-FR", {maximumFractionDigits: 0})} €</strong> ({formatRate(form.commission_rate_2 ?? form.commission_rate ?? 0)})
                  </p>
                </div>
              )}
            </div>
          )}

          <ProspecteurField form={form} setForm={setForm} testPrefix="edit-sale" />

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Statut</Label>
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger data-testid="edit-sale-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {statuses.map((s) => (<SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Date d’intervention</Label>
              <Input type="date" value={form.desired_intervention_date && !["attente_financement","attente_14j"].includes(form.desired_intervention_date) ? form.desired_intervention_date : ""} onChange={(e) => setForm({ ...form, desired_intervention_date: e.target.value })} disabled={["attente_financement","attente_14j"].includes(form.desired_intervention_date)} data-testid="edit-sale-intervention" />
              <Select value={["attente_financement","attente_14j"].includes(form.desired_intervention_date) ? form.desired_intervention_date : "__date"} onValueChange={(v) => setForm({ ...form, desired_intervention_date: v === "__date" ? "" : v })}>
                <SelectTrigger className="mt-1.5 h-8" data-testid="edit-sale-intervention-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__date">Date précise</SelectItem>
                  <SelectItem value="attente_financement">En attente d'acceptation financement</SelectItem>
                  <SelectItem value="attente_14j">En attente délai de 14 jours</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5"><Label>Notes</Label>
            <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="edit-sale-notes" />
          </div>
        </div>

        <SheetFooter className="mt-6 flex-col-reverse sm:flex-row sm:justify-between gap-2">
          <Button variant="ghost" onClick={remove} className="text-red-600 hover:text-red-700 hover:bg-red-50 w-full sm:w-auto" data-testid="edit-sale-delete-btn">
            <Trash2 size={14} className="mr-2" /> Supprimer
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving} data-testid="edit-sale-save-btn">
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
