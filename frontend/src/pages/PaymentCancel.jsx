import React from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export default function PaymentCancel() {
  const nav = useNavigate();
  return (
    <div className="min-h-screen grid place-items-center bg-slate-50 p-6">
      <Card className="p-10 max-w-md w-full text-center border-slate-200 shadow-sm">
        <div className="mx-auto h-16 w-16 rounded-full bg-amber-100 grid place-items-center">
          <AlertCircle size={32} className="text-amber-600" />
        </div>
        <h1 className="font-display text-2xl font-semibold mt-4">Paiement annulé</h1>
        <p className="text-sm text-slate-500 mt-2">Vous pouvez reprendre l'abonnement à tout moment.</p>
        <div className="flex gap-2 mt-6">
          <Button variant="outline" className="flex-1" onClick={() => nav("/")}>Tableau de bord</Button>
          <Button className="flex-1" onClick={() => nav("/abonnement")}>Retour aux plans</Button>
        </div>
      </Card>
    </div>
  );
}
