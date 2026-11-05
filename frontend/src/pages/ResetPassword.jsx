import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle2, ShieldCheck } from "lucide-react";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = useMemo(() => params.get("token") || "", [params]);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password.length < 12) return setError("Le mot de passe doit contenir au moins 12 caractères.");
    if (password !== confirm) return setError("Les deux mots de passe ne correspondent pas.");
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password });
      setDone(true);
    } catch (err) { setError(formatApiError(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#f7f3e9] px-5 py-10 text-[#0b1220]">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-[430px] flex-col justify-center">
        <Link to="/login" className="mb-8 flex items-center gap-2.5 text-sm font-medium text-[#667085] hover:text-[#0b1220]">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#0b1220] font-display text-lg font-bold text-[#f7f3e9]">Q</span>
          <span className="font-display text-lg font-semibold text-[#0b1220]">Qylot</span>
        </Link>
        <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#a9552b]">Compte</p>
        <h1 className="mt-3 font-display text-[34px] font-semibold leading-tight tracking-[-.04em]">Nouveau mot de passe.</h1>
        <p className="mt-3 text-sm leading-relaxed text-[#667085]">Choisissez un mot de passe de 12 caractères minimum. Toutes les sessions existantes seront déconnectées.</p>

        {done ? (
          <div className="mt-8 rounded-2xl border border-[#d8d0c0] bg-white p-5">
            <CheckCircle2 size={22} className="text-[#1f6b57]" />
            <p className="mt-3 font-medium">Mot de passe mis à jour.</p>
            <Link to="/login" className="mt-5 inline-block text-sm font-semibold text-[#a9552b] underline underline-offset-4">Se connecter</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-5" data-testid="reset-password-form">
            {!token && <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700">Lien incomplet. Demandez un nouvel email.</div>}
            <div className="space-y-1.5">
              <Label htmlFor="reset-password" className="text-[12px] font-medium text-[#344054]">Nouveau mot de passe</Label>
              <Input id="reset-password" type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} data-testid="reset-password-input" className="qy-login-field h-12 rounded-xl border-[#d8d0c0] bg-white text-[15px] shadow-none focus-visible:ring-[#a9552b]" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="reset-confirm" className="text-[12px] font-medium text-[#344054]">Confirmer</Label>
              <Input id="reset-confirm" type="password" autoComplete="new-password" required minLength={12} value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="reset-confirm-input" className="qy-login-field h-12 rounded-xl border-[#d8d0c0] bg-white text-[15px] shadow-none focus-visible:ring-[#a9552b]" />
            </div>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700" role="alert">{error}</div>}
            <Button type="submit" disabled={loading || !token} className="h-12 w-full rounded-xl bg-[#0b1220] text-[14px] font-semibold text-[#f7f3e9] hover:bg-[#1d2939]" data-testid="reset-submit-btn">
              {loading ? "Mise à jour…" : "Changer le mot de passe"}
            </Button>
            <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#98a2b3]"><ShieldCheck size={12} /> Lien à usage unique.</p>
          </form>
        )}
        <Link to="/login" className="mt-8 text-center text-xs text-[#667085] underline underline-offset-4 hover:text-[#0b1220]">Revenir à la connexion</Link>
      </div>
    </div>
  );
}
