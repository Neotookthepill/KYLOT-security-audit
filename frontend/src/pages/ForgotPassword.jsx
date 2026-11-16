import React, { useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle2, ShieldCheck } from "lucide-react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) { setError(formatApiError(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#F5F7FA] px-5 py-10 text-[#111827]">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-[430px] flex-col justify-center">
        <Link to="/login" className="mb-8 flex items-center gap-2.5 text-sm font-medium text-[#667085] hover:text-[#111827]">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#5271FF] font-display text-lg font-bold text-white">Q</span>
          <span className="font-display text-lg font-semibold text-[#111827]">Qylot</span>
        </Link>
        <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#5271FF]">Compte</p>
        <h1 className="mt-3 font-display text-[34px] font-semibold leading-tight tracking-[-.04em]">Mot de passe oublié.</h1>
        <p className="mt-3 text-sm leading-relaxed text-[#667085]">Indiquez votre email professionnel. Si un compte existe, vous recevrez un lien valable 30 minutes.</p>

        {sent ? (
          <div className="mt-8 rounded-2xl border border-[#DDE3EC] bg-white p-5">
            <CheckCircle2 size={22} className="text-[#1f6b57]" />
            <p className="mt-3 font-medium">Demande envoyée.</p>
            <p className="mt-1 text-sm text-[#667085]">Consultez votre boîte mail. Le lien est valable 30 minutes et ne peut être utilisé qu’une fois.</p>
            <Link to="/login" className="mt-5 inline-block text-sm font-semibold text-[#5271FF] underline underline-offset-4">Retour à la connexion</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-5" data-testid="forgot-password-form">
            <div className="space-y-1.5">
              <Label htmlFor="forgot-email" className="text-[12px] font-medium text-[#344054]">Email professionnel</Label>
              <Input id="forgot-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="forgot-email-input" placeholder="vous@entreprise.fr" className="qy-login-field h-12 rounded-xl border-[#DDE3EC] bg-white text-[15px] shadow-none focus-visible:ring-[#5271FF]" />
            </div>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700" role="alert">{error}</div>}
            <Button type="submit" disabled={loading} className="h-12 w-full rounded-xl bg-[#5271FF] text-[14px] font-semibold text-white hover:bg-[#3B56D9]" data-testid="forgot-submit-btn">
              {loading ? "Envoi…" : "Envoyer le lien"}
            </Button>
            <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#98a2b3]"><ShieldCheck size={12} /> Réponse identique même si l’adresse n’existe pas.</p>
          </form>
        )}
        <Link to="/login" className="mt-8 text-center text-xs text-[#667085] underline underline-offset-4 hover:text-[#111827]">Revenir à la connexion</Link>
      </div>
    </div>
  );
}
