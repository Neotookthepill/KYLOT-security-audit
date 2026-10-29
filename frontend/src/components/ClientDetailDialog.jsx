import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Phone, Mail, MapPin, FileText, RefreshCw } from "lucide-react";
import { STATUS_MAP, formatPayment, formatRate } from "@/lib/saleConstants";
import ReinterventionDialog from "@/components/ReinterventionDialog";
import { ClientNotes } from "@/components/ClientNotes";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

export default function ClientDetailDialog({ client, open, onOpenChange }) {
  const [sales, setSales] = useState([]);
  const [reinters, setReinters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [reinterOpen, setReinterOpen] = useState(false);

  const loadReinters = async () => {
    if (!client) return;
    try { setReinters((await api.get(`/reinterventions?client_id=${client.id}`)).data || []); } catch (_) {}
  };

  useEffect(() => {
    if (!open || !client) return;
    setLoading(true);
    Promise.all([
      api.get("/sales").then((r) => setSales(r.data.filter((s) => s.client_id === client.id))),
      loadReinters(),
    ]).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, client]);

  if (!client) return null;

  const active = sales.filter((s) => s.status !== "annule" && s.status !== "litige");
  const totalCA = active.reduce((a, s) => a + (parseFloat(s.amount) || 0), 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="client-detail-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">{client.name}</DialogTitle>
          <div className="flex flex-wrap gap-4 text-sm text-slate-600 mt-2">
            {client.phone && <span className="flex items-center gap-1.5"><Phone size={13} /> {client.phone}</span>}
            {client.email && <span className="flex items-center gap-1.5"><Mail size={13} /> {client.email}</span>}
            {(client.address || client.city) && (
              <span className="flex items-center gap-1.5"><MapPin size={13} /> {client.address} {client.postal_code} {client.city}</span>
            )}
          </div>
          {client.notes && (
            <div className="mt-3 flex items-start gap-2 text-sm text-slate-600 bg-slate-50 rounded-md px-3 py-2 border border-slate-100">
              <FileText size={13} className="mt-0.5 shrink-0" />
              <span>{client.notes}</span>
            </div>
          )}
        </DialogHeader>

        <div className="mt-4">
          <div className="flex items-center justify-between mb-3">
            <p className="overline">Historique des ventes</p>
            <span className="text-xs text-slate-500">Total actif : <span className="font-semibold text-slate-900">{fmtEur(totalCA)}</span></span>
          </div>

          {loading && <p className="text-sm text-slate-500 py-6 text-center">Chargement…</p>}

          {!loading && sales.length === 0 && (
            <p className="text-sm text-slate-500 py-6 text-center border border-dashed border-slate-200 rounded-lg">Aucune vente enregistrée pour ce client.</p>
          )}

          <div className="space-y-2">
            {sales.map((s) => {
              const st = STATUS_MAP[s.status];
              return (
                <div key={s.id} className={`border border-slate-200 rounded-lg p-3 ${s.status === "annule" ? "opacity-60" : ""}`} data-testid={`client-sale-${s.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-slate-900">{s.sale_date}</span>
                        {s.bdc && <span className="text-xs font-mono text-slate-500">· {s.bdc}</span>}
                        {s.commercial && <span className="text-xs text-slate-500">· par {s.commercial}</span>}
                      </div>
                      <div className="text-sm text-slate-700 mt-1">{s.service}</div>
                      <div className="flex flex-wrap gap-3 text-xs text-slate-500 mt-2">
                        <span>Règlement : <span className="font-medium text-slate-700">{formatPayment(s.payment_method, s.payment_installments)}</span></span>
                        {s.desired_intervention_date && <span>Intervention : <span className="font-medium text-slate-700">{s.desired_intervention_date}</span></span>}
                        <span>Comm. : <span className="font-medium text-slate-700">{formatRate(s.commission_rate)}</span></span>
                      </div>
                      {s.notes && <div className="text-xs text-slate-500 mt-1.5 italic">« {s.notes} »</div>}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-display text-lg font-semibold">{fmtEur(s.amount)}</div>
                      <Badge className={`${st?.cls || "bg-slate-200 text-slate-700"} border-0 mt-1`}>{st?.label || s.status}</Badge>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-6">
          <div className="flex items-center justify-between mb-3">
            <p className="overline flex items-center gap-1.5"><RefreshCw size={12} className="text-orange-600" /> Réinterventions</p>
            <Button size="sm" variant="outline" onClick={() => setReinterOpen(true)} className="border-orange-200 text-orange-700 hover:bg-orange-50" data-testid="client-add-reinter">
              + Ajouter une réintervention
            </Button>
          </div>
          {reinters.length === 0 && (
            <p className="text-sm text-slate-500 py-4 text-center border border-dashed border-slate-200 rounded-lg">Aucune réintervention.</p>
          )}
          <div className="space-y-2">
            {reinters.map((r) => (
              <div key={r.id} className="border border-orange-100 bg-orange-50/30 rounded-lg p-3" data-testid={`client-reinter-${r.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={`border-0 ${r.status === "terminee" ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"}`}>
                        {r.status === "terminee" ? "Terminée" : "À faire"}
                      </Badge>
                      <span className="font-semibold text-slate-900">{r.scheduled_date}{r.scheduled_time ? ` · ${r.scheduled_time}` : ""}</span>
                      {r.technician_name && <span className="text-xs text-slate-500">→ {r.technician_name}</span>}
                    </div>
                    {r.note && <div className="text-sm text-slate-700 mt-1">{r.note}</div>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <ClientNotes clientId={client.id} />

        <ReinterventionDialog open={reinterOpen} onOpenChange={setReinterOpen} client={client} onChanged={loadReinters} />
      </DialogContent>
    </Dialog>
  );
}
