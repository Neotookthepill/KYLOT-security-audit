import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";
import { ChequeInstallmentsSelect } from "@/components/ChequeInstallmentsSelect";
import { ProspecteurField, prospecteurPayload } from "@/components/ProspecteurField";
import { SALE_STATUSES, formatRate, PAYMENT_OPTIONS, CHEQUE_INSTALLMENTS, SOURCES, orderStatuses, resolveStatusesFromPayload } from "@/lib/saleConstants";
import useTeam from "@/lib/useTeam";
import useCommissionRates from "@/lib/useCommissionRates";
import { useSettings } from "@/contexts/SettingsContext";

// iter49: date locale Europe/Paris — jamais toISOString() (shift UTC -1j la nuit)
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function NewSaleSheet({ open, onOpenChange, onCreated, prefill = null }) {
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
  const [clients, setClients] = useState([]);
  const [clientMode, setClientMode] = useState("existing");
  const [selectedClientId, setSelectedClientId] = useState("");
  const [comboOpen, setComboOpen] = useState(false);
  const [newClient, setNewClient] = useState({ name: "", phone: "", email: "", address: "", postal_code: "", city: "", notes: "" });
  const [form, setForm] = useState({
    bdc: "", service: "", amount: "",
    payment_method: "cheque", payment_installments: 1,
    financement_amount: "", comptant_installments: 1,
    commission_rate: 0, commission_rate_2: null, commission_type: "fixed", commission_type_2: "fixed", discount_percent: null, evolutive_ca_threshold: 30000, evolutive_rate_below: 0.10, evolutive_rate_above: 0.13, commercial: "", commercial_2: "", is_de: false, commercial_share: 0.5, source: "",
    sale_date: today(), desired_intervention_date: "",
    status: "en_cours", notes: "",
  });
  const [saving, setSaving] = useState(false);
  // iter113 : CA cumulé du commercial pour le mois (source de vérité pour le taux évolutif)
  const [commercialMonthCA, setCommercialMonthCA] = useState(0);

  // iter113 : fetch le CA cumulé quand commercial ou sale_date change (pour la preview)
  useEffect(() => {
    if (!open || form.commission_type !== "evolutive_ca") { setCommercialMonthCA(0); return; }
    const name = (form.commercial || "").trim();
    const month = (form.sale_date || "").slice(0, 7);
    if (!name || !month) { setCommercialMonthCA(0); return; }
    let cancelled = false;
    api.get(`/sales/commercial-month-ca?commercial_name=${encodeURIComponent(name)}&month=${encodeURIComponent(month)}`)
      .then((r) => { if (!cancelled) setCommercialMonthCA(parseFloat(r.data?.total_ca) || 0); })
      .catch(() => { if (!cancelled) setCommercialMonthCA(0); });
    return () => { cancelled = true; };
  }, [open, form.commercial, form.sale_date, form.commission_type]);

  useEffect(() => {
    if (!open) return;
    api.get("/clients").then((r) => {
      setClients(r.data);
      // Apply prefill AFTER clients are loaded so we can match an existing one
      if (prefill) {
        if (prefill.client_id && r.data.some((c) => c.id === prefill.client_id)) {
          setClientMode("existing");
          setSelectedClientId(prefill.client_id);
        } else if (prefill.new_client && prefill.new_client.name) {
          setClientMode("new");
          setNewClient((prev) => ({ ...prev, ...prefill.new_client }));
        } else if (prefill.client_name) {
          // Try to find by name
          const match = r.data.find((c) => (c.name || "").toLowerCase() === prefill.client_name.toLowerCase());
          if (match) {
            setClientMode("existing");
            setSelectedClientId(match.id);
          } else {
            setClientMode("new");
            setNewClient((prev) => ({
              ...prev,
              name: prefill.client_name || "",
              phone: prefill.client_phone || "",
              address: prefill.client_address || "",
              postal_code: prefill.client_postal_code || "",
              city: prefill.client_city || "",
            }));
          }
        }
      }
    });
    if (prefill) {
      setForm((prev) => ({
        ...prev,
        bdc: prefill.bdc || "",
        service: prefill.service || "",
        amount: prefill.amount != null ? String(prefill.amount) : "",
        commercial: prefill.commercial || "",
        sale_date: prefill.sale_date || today(),
        source: prefill.source || "",
      }));
    } else {
      setClientMode("existing");
      setSelectedClientId("");
      setNewClient({ name: "", phone: "", email: "", address: "", postal_code: "", city: "", notes: "" });
      setForm({ bdc: "", service: "", amount: "", payment_method: "cheque", payment_installments: 1, financement_amount: "", comptant_installments: 1, commission_rate: 0, commission_rate_2: null, commission_type: "fixed", commission_type_2: "fixed", evolutive_ca_threshold: 30000, evolutive_rate_below: 0.10, evolutive_rate_above: 0.13, commercial: "", commercial_2: "", is_de: false, commercial_share: 0.5, source: "", sale_date: today(), desired_intervention_date: "", status: "en_cours", notes: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async () => {
    setSaving(true);
    try {
      const payload = {
        bdc: form.bdc,
        service: form.service,
        amount: parseFloat(form.amount || 0),
        payment_method: form.payment_method,
        payment_installments: parseInt(form.payment_installments || 1, 10),
        financement_amount: form.payment_method === "financement" && form.financement_amount !== "" ? parseFloat(form.financement_amount) : null,
        comptant_installments: parseInt(form.comptant_installments || 1, 10),
        commission_rate: (() => {
          if (form.commission_type === "evolutive_ca") {
            // iter118 : fallback robuste — si l'input a été chargé sans state (défauts),
            // on garantit que le seuil et les taux ne sont jamais undefined.
            const amt = parseFloat(form.amount) || 0;
            const share = form.is_de ? 0.5 : 1.0;
            const projectedCA = (parseFloat(commercialMonthCA) || 0) + amt * share;
            const threshold = parseFloat(form.evolutive_ca_threshold ?? 30000) || 30000;
            return projectedCA >= threshold ? parseFloat(form.evolutive_rate_above ?? 0.13) : parseFloat(form.evolutive_rate_below ?? 0.10);
          }
          return parseFloat(form.commission_rate);
        })(),
        commission_rate_2: !form.is_de ? null : form.commission_type_2 === "evolutive_ca" ? parseFloat(form.evolutive_rate_below ?? 0.10) : (form.commission_rate_2 != null ? parseFloat(form.commission_rate_2) : parseFloat(form.commission_rate) || 0),
        commission_type: form.commission_type || "fixed",
        commission_type_2: form.is_de ? (form.commission_type_2 || "fixed") : null,
        evolutive_ca_threshold: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? (parseFloat(form.evolutive_ca_threshold ?? 30000) || 30000) : null,
        evolutive_rate_below: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? (parseFloat(form.evolutive_rate_below ?? 0.10) || 0.10) : null,
        evolutive_rate_above: (form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) ? (parseFloat(form.evolutive_rate_above ?? 0.13) || 0.13) : null,
        discount_percent: null,
        commercial: form.commercial,
        commercial_2: form.is_de ? form.commercial_2 : "",
        is_de: !!form.is_de,
        commercial_share: form.is_de ? parseFloat(form.commercial_share ?? 0.5) : 1.0,
        source: form.source,
        // iter214 : force null si vide (voir EditSaleSheet)
        sale_date: form.sale_date || null,
        desired_intervention_date: form.desired_intervention_date || null,
        status: form.status,
        notes: form.notes,
        ...prospecteurPayload(form),
      };
      if (clientMode === "existing") {
        if (!selectedClientId) throw new Error("Sélectionnez un client");
        payload.client_id = selectedClientId;
      } else {
        if (!newClient.name) throw new Error("Nom du client requis");
        payload.client = newClient;
      }
      await api.post("/sales", payload);
      toast.success("Vente créée" + (form.status !== "annule" && form.status !== "litige" ? " · chantier ajouté au planning" : ""));
      onOpenChange(false);
      onCreated?.();
    } catch (err) {
      toast.error(formatApiError(err) || err.message);
    } finally { setSaving(false); }
  };

  const selectedClient = clients.find((c) => c.id === selectedClientId);
  const showInstallments = form.payment_method === "cheque";
  const showFinancement = form.payment_method === "financement";
  const showComptantInstallments = form.payment_method && !["financement"].includes(form.payment_method) && form.payment_method !== "cheque";
  const total = parseFloat(form.amount || 0);
  const fin = parseFloat(form.financement_amount || 0);
  const comptantPart = Math.max(0, total - (showFinancement ? fin : 0));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-xl overflow-y-auto" data-testid="new-sale-sheet">
        <SheetHeader>
          <SheetTitle className="font-display text-2xl">Nouvelle vente</SheetTitle>
          <SheetDescription>Le chantier est ajouté automatiquement au planning (sauf si annulé ou en litige).</SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Date</Label>
              <Input type="date" value={form.sale_date} onChange={(e) => setForm({ ...form, sale_date: e.target.value })} data-testid="sale-date" />
            </div>
            <div className="space-y-1.5"><Label>BDC</Label>
              <Input value={form.bdc} onChange={(e) => setForm({ ...form, bdc: e.target.value })} placeholder="N° bon de commande" data-testid="sale-bdc" />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Nom / Prénom</Label>
            <div className="flex gap-2 text-xs">
              <button type="button" onClick={() => setClientMode("existing")} data-testid="client-mode-existing" className={`px-3 py-1 rounded-md border ${clientMode === "existing" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600"}`}>Client existant</button>
              <button type="button" onClick={() => setClientMode("new")} data-testid="client-mode-new" className={`px-3 py-1 rounded-md border ${clientMode === "new" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600"}`}>Nouveau client</button>
            </div>
            {clientMode === "existing" ? (
              <Popover open={comboOpen} onOpenChange={setComboOpen}>
                <PopoverTrigger asChild>
                  <Button variant="outline" role="combobox" className="w-full justify-between" data-testid="client-select-trigger">
                    {selectedClient ? selectedClient.name : "Rechercher un client…"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="p-0 w-[420px]">
                  <Command>
                    <CommandInput placeholder="Chercher par nom, téléphone…" />
                    <CommandList>
                      <CommandEmpty>Aucun client.</CommandEmpty>
                      <CommandGroup>
                        {clients.map((c) => (
                          <CommandItem key={c.id} value={`${c.name} ${c.phone} ${c.address} ${c.city}`} onSelect={() => { setSelectedClientId(c.id); setComboOpen(false); }} data-testid={`client-option-${c.id}`}>
                            <div>
                              <div className="font-medium">{c.name}</div>
                              <div className="text-xs text-slate-500">{c.phone} · {c.postal_code} {c.city}</div>
                            </div>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            ) : (
              <div className="space-y-2">
                <Input placeholder="Nom / Prénom" value={newClient.name} onChange={(e) => setNewClient({ ...newClient, name: e.target.value })} data-testid="new-client-name" />
                <Input placeholder="Téléphone" value={newClient.phone} onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })} data-testid="new-client-phone" />
                <Input placeholder="Adresse" value={newClient.address} onChange={(e) => setNewClient({ ...newClient, address: e.target.value })} data-testid="new-client-address" />
                <div className="grid grid-cols-[110px_1fr] gap-2">
                  <Input placeholder="Code postal" value={newClient.postal_code} onChange={(e) => setNewClient({ ...newClient, postal_code: e.target.value })} data-testid="new-client-postal" />
                  <Input placeholder="Ville" value={newClient.city} onChange={(e) => setNewClient({ ...newClient, city: e.target.value })} data-testid="new-client-city" />
                </div>
                <Input placeholder="Email (optionnel)" value={newClient.email} onChange={(e) => setNewClient({ ...newClient, email: e.target.value })} />
              </div>
            )}
          </div>

          <div className="space-y-1.5"><Label>Produits</Label>
            <Textarea rows={2} value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} placeholder="Ex : PAC air/eau + ballon thermodynamique" data-testid="sale-service" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Montant HT (€)</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="sale-amount" />
            </div>
            <div className="space-y-1.5"><Label>Règlement</Label>
              <Select value={form.payment_method} onValueChange={(v) => setForm({ ...form, payment_method: v, payment_installments: v === "cheque" ? form.payment_installments || 1 : 1 })}>
                <SelectTrigger data-testid="sale-payment"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  {PAYMENT_OPTIONS.map((o) => (<SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {showInstallments && (
            <div className="space-y-1.5">
              <Label>Chèque en combien de fois ?</Label>
              <ChequeInstallmentsSelect testid="sale-installments" value={form.payment_installments} onChange={(v) => setForm({ ...form, payment_installments: v })} />
              {total > 0 && form.payment_installments > 1 && (
                <p className="text-xs text-slate-500">Soit {(total / form.payment_installments).toFixed(2)} € par chèque × {form.payment_installments}</p>
              )}
            </div>
          )}

          {showFinancement && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 space-y-2" data-testid="sale-financement-block">
              <Label className="text-xs">Montant financé (€)</Label>
              <Input type="number" step="0.01" min="0" max={total || undefined}
                value={form.financement_amount}
                onChange={(e) => setForm({ ...form, financement_amount: e.target.value })}
                placeholder="Ex: 10000"
                data-testid="sale-financement-amount" />
              {total > 0 && (
                <div className="text-xs text-slate-700 space-y-0.5" data-testid="sale-financement-summary">
                  <p>Montant total : <span className="font-semibold">{total.toFixed(2)} €</span></p>
                  <p>Financement : <span className="font-semibold">{(fin || 0).toFixed(2)} €</span></p>
                  <p className="text-emerald-800">Part au comptant : <span className="font-semibold">{comptantPart.toFixed(2)} €</span></p>
                </div>
              )}
              {comptantPart > 0 && (
                <div className="pt-2">
                  <Label className="text-xs">Part comptant en combien de fois ?</Label>
                  <Select value={String(form.comptant_installments)} onValueChange={(v) => setForm({ ...form, comptant_installments: parseInt(v, 10) })}>
                    <SelectTrigger className="h-8" data-testid="sale-comptant-installments"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[1,2,3,4,6,12].map((n) => (<SelectItem key={n} value={String(n)}>{n === 1 ? "En 1 fois" : `${n} fois`} · {(comptantPart / n).toFixed(2)} € / échéance</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}

          {showComptantInstallments && (
            <div className="space-y-1.5">
              <Label>Réglement en combien de fois ?</Label>
              <Select value={String(form.comptant_installments)} onValueChange={(v) => setForm({ ...form, comptant_installments: parseInt(v, 10) })}>
                <SelectTrigger data-testid="sale-comptant-installments"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[1,2,3,4,6,12].map((n) => (<SelectItem key={n} value={String(n)}>{n === 1 ? "En 1 fois" : `${n} fois`}{total > 0 ? ` · ${(total / n).toFixed(2)} € / échéance` : ""}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Type de commission{form.is_de ? " commercial 1" : ""}</Label>
              <Select value={form.commission_type || "fixed"} onValueChange={(v) => setForm({ ...form, commission_type: v })}>
                <SelectTrigger data-testid="sale-commission-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="fixed">Fixe</SelectItem>
                  <SelectItem value="evolutive_ca">Évolutive selon CA</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {(form.commission_type === "evolutive_ca" || (form.is_de && form.commission_type_2 === "evolutive_ca")) && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 space-y-3" data-testid="sale-evolutive-block">
              <p className="text-xs text-indigo-900 font-semibold">Palier de bascule automatique</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1"><Label className="text-xs">Seuil CA (€)</Label>
                  <Input type="number" min="0" step="1000" value={form.evolutive_ca_threshold ?? 30000}
                    onChange={(e) => setForm({ ...form, evolutive_ca_threshold: parseFloat(e.target.value) || 0 })}
                    data-testid="sale-evolutive-threshold" placeholder="30000" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Taux en dessous</Label>
                  <Select value={String(form.evolutive_rate_below ?? 0.10)} onValueChange={(v) => setForm({ ...form, evolutive_rate_below: parseFloat(v) })}>
                    <SelectTrigger data-testid="sale-evolutive-rate-below"><SelectValue /></SelectTrigger>
                    <SelectContent>{commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">Taux au-dessus</Label>
                  <Select value={String(form.evolutive_rate_above ?? 0.13)} onValueChange={(v) => setForm({ ...form, evolutive_rate_above: parseFloat(v) })}>
                    <SelectTrigger data-testid="sale-evolutive-rate-above"><SelectValue /></SelectTrigger>
                    <SelectContent>{commissionRates.map((r) => (<SelectItem key={r} value={String(r)}>{formatRate(r)}</SelectItem>))}</SelectContent>
                  </Select>
                </div>
              </div>
              {form.commission_type === "evolutive_ca" && <p className="text-[11px] text-indigo-800">
                {(() => {
                  const amt = parseFloat(form.amount) || 0;
                  const share = form.is_de ? 0.5 : 1.0;
                  const projectedCA = (parseFloat(commercialMonthCA) || 0) + amt * share;
                  const threshold = parseFloat(form.evolutive_ca_threshold ?? 30000) || 30000;
                  const rate = projectedCA >= threshold ? (form.evolutive_rate_above ?? 0.13) : (form.evolutive_rate_below ?? 0.10);
                  const cmpSign = projectedCA >= threshold ? "≥" : "<";
                  return (
                    <>
                      Taux appliqué : <b>{formatRate(rate)}</b> — <b>CA mensuel projeté du commercial</b> : {projectedCA.toFixed(0)} € {cmpSign} seuil {threshold.toFixed(0)} €
                      <br/>
                      <span className="text-indigo-600/80">(déjà cumulé ce mois : {(parseFloat(commercialMonthCA) || 0).toFixed(0)} € + cette vente : {(amt * share).toFixed(0)} €{form.is_de ? " × 50% DE" : ""})</span>
                    </>
                  );
                })()}
              </p>}
            </div>
          )}

          {(!form.commission_type || form.commission_type === "fixed") && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>{form.is_de ? "Commission commercial 1" : "Commission"}</Label>
              <Select value={String(form.commission_rate)} onValueChange={(v) => setForm({ ...form, commission_rate: parseFloat(v) })}>
                <SelectTrigger data-testid="sale-commission"><SelectValue /></SelectTrigger>
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
                <SelectTrigger data-testid="sale-commercial"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {commerciaux.map((c) => (<SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Source</Label>
              <Select value={form.source || "__none"} onValueChange={(v) => setForm({ ...form, source: v === "__none" ? "" : v })}>
                <SelectTrigger data-testid="sale-source"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">—</SelectItem>
                  {SOURCES.map((s) => (<SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <label className="flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/40 px-3 py-2 cursor-pointer" data-testid="sale-de-toggle">
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
                  <SelectTrigger data-testid="sale-commercial-2"><SelectValue placeholder="Choisir…" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">—</SelectItem>
                    {commerciaux.filter((c) => c.name !== form.commercial).map((c) => (<SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Type de commission commercial 2</Label>
                <Select value={form.commission_type_2 || "fixed"} onValueChange={(v) => setForm({ ...form, commission_type_2: v })}>
                  <SelectTrigger data-testid="sale-commission-type-2"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fixed">Fixe</SelectItem>
                    <SelectItem value="evolutive_ca">Évolutive selon CA</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Commission commercial 2</Label>
                {form.commission_type_2 === "evolutive_ca" ? (
                  <p className="h-10 flex items-center text-xs text-indigo-800 rounded-md border border-indigo-100 bg-indigo-50/60 px-3" data-testid="sale-commission-2-evolutive">Évolutive selon son propre CA du mois</p>
                ) : (
                <Select value={String(form.commission_rate_2 ?? form.commission_rate ?? 0.10)} onValueChange={(v) => setForm({ ...form, commission_rate_2: parseFloat(v) })}>
                  <SelectTrigger data-testid="sale-commission-2"><SelectValue /></SelectTrigger>
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

          <ProspecteurField form={form} setForm={setForm} testPrefix="sale" />

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Statut</Label>
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger data-testid="sale-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {statuses.map((s) => (<SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Date d’intervention souhaitée</Label>
              <Input type="date" value={form.desired_intervention_date && !["attente_financement","attente_14j"].includes(form.desired_intervention_date) ? form.desired_intervention_date : ""} onChange={(e) => setForm({ ...form, desired_intervention_date: e.target.value })} disabled={["attente_financement","attente_14j"].includes(form.desired_intervention_date)} data-testid="sale-intervention-date" />
              <Select value={["attente_financement","attente_14j"].includes(form.desired_intervention_date) ? form.desired_intervention_date : "__date"} onValueChange={(v) => setForm({ ...form, desired_intervention_date: v === "__date" ? "" : v })}>
                <SelectTrigger className="mt-1.5 h-8" data-testid="sale-intervention-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__date">Date précise</SelectItem>
                  <SelectItem value="attente_financement">En attente d'acceptation financement</SelectItem>
                  <SelectItem value="attente_14j">En attente délai de 14 jours</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5"><Label>Notes</Label>
            <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
        </div>

        <SheetFooter className="mt-6">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button onClick={submit} disabled={saving} data-testid="sale-submit-btn">
            {saving ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
