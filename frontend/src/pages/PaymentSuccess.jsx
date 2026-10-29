import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("polling");
  const [tries, setTries] = useState(0);
  const [plan, setPlan] = useState(null);

  useEffect(() => {
    if (!sessionId) { setStatus("error"); return; }
    let cancelled = false;
    const poll = async () => {
      for (let i = 0; i < 30; i++) {
        if (cancelled) return;
        try {
          const { data } = await api.get(`/payments/status/${sessionId}`);
          setTries(i + 1);
          if (data.entitled === true || data.payment_status === "paid") {
            setPlan(data.lookup_key);
            setStatus("paid");
            return;
          }
          if (data.status === "failed" || data.status === "expired") {
            setStatus("failed");
            return;
          }
        } catch (e) { /* keep polling */ }
        await new Promise((r) => setTimeout(r, 2000));
      }
      setStatus("timeout");
    };
    poll();
    return () => { cancelled = true; };
  }, [sessionId]);

  return (
    <div className="min-h-screen grid place-items-center bg-slate-50 p-6">
      <Card className="p-10 max-w-md w-full text-center border-slate-200 shadow-sm" data-testid="payment-success-card">
        {status === "polling" && (
          <>
            <Loader2 size={48} className="mx-auto animate-spin text-slate-400" />
            <h1 className="font-display text-2xl font-semibold mt-4">Confirmation du paiement…</h1>
            <p className="text-sm text-slate-500 mt-2">Merci, on vérifie votre paiement auprès de Stripe.</p>
            <p className="text-xs text-slate-400 mt-3">Tentative {tries}/30</p>
          </>
        )}
        {status === "paid" && (
          <>
            <div className="mx-auto h-16 w-16 rounded-full bg-emerald-100 grid place-items-center">
              <CheckCircle2 size={32} className="text-emerald-600" />
            </div>
            <h1 className="font-display text-2xl font-semibold mt-4">Abonnement activé 🎉</h1>
            <p className="text-sm text-slate-500 mt-2">Votre plan est actif. Vous pouvez utiliser toutes les fonctionnalités.</p>
            {plan && <div className="mt-3 text-xs uppercase tracking-widest text-slate-500">Plan : {plan}</div>}
            <Button className="mt-6 w-full" onClick={() => nav("/")} data-testid="payment-back-btn">Retour au tableau de bord</Button>
          </>
        )}
        {(status === "failed" || status === "timeout" || status === "error") && (
          <>
            <div className="mx-auto h-16 w-16 rounded-full bg-red-100 grid place-items-center">
              <XCircle size={32} className="text-red-600" />
            </div>
            <h1 className="font-display text-2xl font-semibold mt-4">
              {status === "timeout" ? "Confirmation en attente" : "Paiement non finalisé"}
            </h1>
            <p className="text-sm text-slate-500 mt-2">
              {status === "timeout"
                ? "Stripe met plus de temps que prévu. Vérifiez votre boîte mail ou rechargez cette page."
                : "Le paiement n'a pas abouti. Aucun montant n'a été prélevé."}
            </p>
            <Button className="mt-6 w-full" onClick={() => nav("/abonnement")} data-testid="payment-retry-btn">Réessayer</Button>
          </>
        )}
      </Card>
    </div>
  );
}
