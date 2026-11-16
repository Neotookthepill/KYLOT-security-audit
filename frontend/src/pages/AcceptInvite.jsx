import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle2, ShieldCheck } from "lucide-react";

export default function AcceptInvite() {
  const { token = "" } = useParams();
  const [invite, setInvite] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(`/auth/invitation/${encodeURIComponent(token)}`)
      .then((r) => { if (!cancelled) setInvite(r.data); })
      .catch((err) => { if (!cancelled) setError(formatApiError(err)); });
    return () => { cancelled = true; };
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password.length < 12) return setError("Le mot de passe doit contenir au moins 12 caractères.");
    if (password !== confirm) return setError("Les deux mots de passe ne correspondent pas.");
    setLoading(true);
    try {
      await api.post("/auth/accept-invitation", { token, password });
      setDone(true);
    } catch (err) { setError(formatApiError(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#f7f3e9] px-5 py-10 text-[#0b1220]">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-[430px] flex-col justify-center">
        <Link to="/login" className="mb-8 flex items-center gap-2.5 text-sm font-medium text-[#667085] hover:text-[#0b1220]">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#0b1220] font-display text-lg font-bold text-[#f7f3e9]">Q</span>
          <span className="font-display text-lg font-semibold">Qylot</span>
        </Link>
        <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#a9552b]">Invitation</p>
        <h1 className="mt-3 font-display text-[34px] font-semibold leading-tight tracking-[-.04em]">Bienvenue sur Qylot.</h1>
        <p className="mt-3 text-sm leading-relaxed text-[#667085]">Choisissez votre mot de passe. Il doit contenir au moins 12 caractères.</p>

        {done ? (
          <div className="mt-8 rounded-2xl border border-[#d8d0c0] bg-white p-5">
            <CheckCircle2 size={22} className="text-[#1f6b57]" />
            <p className="mt-3 font-medium">Compte activé.</p>
            <Link to="/login" className="mt-5 inline-block text-sm font-semibold text-[#a9552b] underline underline-offset-4" data-testid="invite-go-login">Se connecter</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-5" data-testid="accept-invite-form">
            {invite && (
              <div className="rounded-xl border border-[#d8d0c0] bg-white px-4 py-3 text-sm">
                <div className="font-semibold">{invite.name}</div>
                <div className="text-[#667085]">{invite.email}</div>
              </div>
            )}
            {!invite && !error && <div className="text-sm text-[#667085]">Vérification du lien…</div>}
            {error && <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700" role="alert">{error}</div>}
            <div className="space-y-1.5">
              <Label htmlFor="invite-password">Mot de passe</Label>
              <Input id="invite-password" type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} data-testid="invite-password-input" className="h-12 rounded-xl" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-confirm">Confirmer</Label>
              <Input id="invite-confirm" type="password" autoComplete="new-password" required minLength={12} value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="invite-confirm-input" className="h-12 rounded-xl" />
            </div>
            <Button type="submit" disabled={loading || !invite} className="h-12 w-full rounded-xl" data-testid="invite-submit-btn">
              {loading ? "Activation…" : "Activer mon compte"}
            </Button>
            <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#98a2b3]"><ShieldCheck size={12} /> Lien à usage unique.</p>
          </form>
        )}
        <Link to="/login" className="mt-8 text-center text-xs text-[#667085] underline underline-offset-4">Revenir à la connexion</Link>
      </div>
    </div>
  );
}
