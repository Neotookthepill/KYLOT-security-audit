import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ArrowUpRight, Check, Compass, ShieldCheck } from "lucide-react";

const PROOF = [
  "Vos ventes et commissions, au même endroit",
  "Le planning et les chantiers, sans double saisie",
  "Une vision claire pour le bureau comme pour le terrain",
];

export default function Login() {
  const { login, verifyMfa } = useAuth();
  const { settings } = useSettings();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      if (p.get("expired") === "1") return "Votre session a expiré. Merci de vous reconnecter.";
    } catch (_) {}
    return "";
  });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result?.mfa_required) {
        setMfaChallenge(result.challenge);
        setMfaCode("");
        toast.info("Saisissez le code de votre application d'authentification.");
        return;
      }
      toast.success("Bienvenue !");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const submitMfa = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyMfa(mfaChallenge, mfaCode);
      toast.success("Bienvenue !");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const appName = settings.app_name || "Qylot";

  return (
    <div className="min-h-screen bg-[#f7f3e9] text-[#0b1220]" data-testid="login-page">
      <div className="grid min-h-screen lg:grid-cols-[1.08fr_.92fr]">
        {/* Brand panel */}
        <section className="relative hidden overflow-hidden bg-[#0b1220] px-12 py-12 text-[#f7f3e9] lg:flex lg:flex-col xl:px-20">
          <div className="pointer-events-none absolute inset-0 opacity-[.16]" style={{ backgroundImage: "linear-gradient(rgba(247,243,233,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(247,243,233,.22) 1px, transparent 1px)", backgroundSize: "72px 72px" }} />
          <div className="pointer-events-none absolute -right-40 top-1/3 h-[540px] w-[540px] rounded-full border border-[#c8784e]/25" />
          <div className="pointer-events-none absolute -right-24 top-1/3 h-[380px] w-[380px] rounded-full border border-[#c8784e]/15" />

          <div className="relative flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#f7f3e9] font-display text-2xl font-bold text-[#0b1220]" data-testid="login-logo">
              {settings.logo ? <img src={settings.logo} alt="logo" className="h-full w-full rounded-xl object-contain p-1" /> : "Q"}
            </div>
            <div>
              <div className="font-display text-[22px] font-semibold leading-none tracking-[-.02em]">{appName}</div>
              <div className="mt-1 text-[9px] uppercase tracking-[.22em] text-white/40">Chantiers & croissance</div>
            </div>
          </div>

          <div className="relative my-auto max-w-[570px] py-12">
            <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#d98b61]">Le logiciel des entreprises qui construisent</p>
            <h1 className="mt-5 font-display text-[46px] font-semibold leading-[.98] tracking-[-.055em] xl:text-[58px]">
              Le chantier.<br />Les clients.<br /><span className="text-[#d98b61]">La croissance.</span>
            </h1>
            <p className="mt-7 max-w-[430px] text-[15px] leading-relaxed text-white/60">
              Qylot réunit le commercial, le terrain et le pilotage dans un seul espace lisible. Pas un tableau de bord de plus : un outil de travail.
            </p>
            <ul className="mt-9 space-y-3.5">
              {PROOF.map((item) => (
                <li key={item} className="flex items-start gap-3 text-[13px] text-white/75">
                  <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#c8784e]/15 text-[#d98b61]"><Check size={12} strokeWidth={2.5} /></span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="relative flex items-center justify-between border-t border-white/10 pt-5 text-[10px] uppercase tracking-[.16em] text-white/30">
            <span>Préproduction · 2026</span>
            <span className="flex items-center gap-1.5"><ShieldCheck size={12} /> Accès sécurisé</span>
          </div>
        </section>

        {/* Form panel */}
        <section className="flex min-h-screen flex-col items-center justify-center px-5 py-10 sm:px-10 lg:px-14 xl:px-20">
          <div className="mb-10 flex items-center gap-2.5 lg:hidden">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-[#0b1220] font-display text-lg font-bold text-[#f7f3e9]">Q</div>
            <span className="font-display text-lg font-semibold tracking-[-.02em]">{appName}</span>
          </div>

          <div className="w-full max-w-[430px]">
            <div className="mb-8">
              <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#a9552b]">{mfaChallenge ? "Vérification" : "Connexion"}</p>
              <h2 className="mt-3 font-display text-[32px] font-semibold leading-tight tracking-[-.04em] text-[#0b1220] sm:text-[38px]">
                {mfaChallenge ? "Un dernier contrôle." : "Bon retour."}
              </h2>
              <p className="mt-3 text-[13px] leading-relaxed text-[#667085]">
                {mfaChallenge ? "Ouvrez votre application d'authentification et saisissez le code à 6 chiffres." : "Entrez vos identifiants pour retrouver votre espace de travail."}
              </p>
            </div>

            {mfaChallenge ? (
              <form onSubmit={submitMfa} className="space-y-5" data-testid="login-mfa-form">
                <div className="space-y-1.5">
                  <Label htmlFor="mfa-code" className="text-[12px] font-medium text-[#344054]">Code d'authentification</Label>
                  <Input
                    id="mfa-code"
                    inputMode="text"
                    autoComplete="one-time-code"
                    autoFocus
                    required
                    minLength={6}
                    maxLength={32}
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value)}
                    data-testid="login-mfa-code-input"
                    placeholder="123456 ou code de secours"
                    className="qy-login-field h-12 rounded-xl border-[#d8d0c0] bg-white text-[15px] shadow-none focus-visible:ring-[#a9552b]"
                  />
                </div>
                {error && <ErrorBox error={error} />}
                <Button type="submit" disabled={loading} className="h-12 w-full rounded-xl bg-[#0b1220] text-[14px] font-semibold text-[#f7f3e9] hover:bg-[#1d2939]" data-testid="login-mfa-submit-btn">
                  {loading ? "Vérification…" : "Valider le code"}
                </Button>
                <button type="button" className="w-full text-xs font-medium text-[#667085] underline underline-offset-4 hover:text-[#0b1220]" onClick={() => { setMfaChallenge(""); setMfaCode(""); setError(""); }}>
                  Revenir à la connexion
                </button>
              </form>
            ) : (
              <form onSubmit={submit} className="space-y-5" data-testid="login-form">
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-[12px] font-medium text-[#344054]">Email professionnel</Label>
                  <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" placeholder="vous@entreprise.fr" className="qy-login-field h-12 rounded-xl border-[#d8d0c0] bg-white text-[15px] shadow-none focus-visible:ring-[#a9552b]" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password" className="text-[12px] font-medium text-[#344054]">Mot de passe</Label>
                  <Input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" placeholder="••••••••" className="qy-login-field h-12 rounded-xl border-[#d8d0c0] bg-white text-[15px] shadow-none focus-visible:ring-[#a9552b]" />
                </div>
                {error && <ErrorBox error={error} />}
                <Button type="submit" disabled={loading} className="h-12 w-full rounded-xl bg-[#0b1220] text-[14px] font-semibold text-[#f7f3e9] hover:bg-[#1d2939]" data-testid="login-submit-btn">
                  {loading ? "Connexion…" : <span className="flex items-center gap-2">Se connecter <ArrowUpRight size={16} /></span>}
                </Button>
              </form>
            )}

            <div className="mt-8 flex items-start gap-3 rounded-xl border border-[#e2dbcd] bg-white/50 p-4">
              <Compass size={17} className="mt-0.5 shrink-0 text-[#a9552b]" />
              <p className="text-[11px] leading-relaxed text-[#667085]">
                Un problème d’accès ? Contactez votre administrateur. Vos données restent isolées par entreprise.
              </p>
            </div>
          </div>

          <div className="mt-10 flex items-center justify-between text-[10px] text-[#98a2b3] lg:mt-auto">
            <span>© 2026 {appName}</span>
            <span>Connexion sécurisée</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function ErrorBox({ error }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700" data-testid="login-error" role="alert">
      {error}
    </div>
  );
}
