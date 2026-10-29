import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

function QylotLogo({ size = 88 }) {
  // iter184 — Logo QYLOT officiel : tuile arrondie noire + anneau argenté brossé
  // + queue diagonale métallique. Identique au visuel de la maquette utilisateur.
  const uid = `qy-${size}`;
  return (
    <svg viewBox="0 0 512 512" width={size} height={size} aria-hidden="true">
      <defs>
        <linearGradient id={`${uid}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#111318" />
          <stop offset="100%" stopColor="#05070f" />
        </linearGradient>
        <linearGradient id={`${uid}-ring`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#F8FAFC" />
          <stop offset="55%" stopColor="#CBD5E1" />
          <stop offset="100%" stopColor="#64748B" />
        </linearGradient>
        <linearGradient id={`${uid}-tail`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#94A3B8" />
          <stop offset="60%" stopColor="#475569" />
          <stop offset="100%" stopColor="#1E293B" />
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="112" fill={`url(#${uid}-bg)`} />
      <circle cx="256" cy="256" r="150" fill="none" stroke={`url(#${uid}-ring)`} strokeWidth="30" />
      <line x1="280" y1="280" x2="436" y2="436" stroke={`url(#${uid}-tail)`} strokeWidth="36" strokeLinecap="butt" />
    </svg>
  );
}

export default function Login() {
  const { login } = useAuth();
  const { settings } = useSettings();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
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
      await login(email, password);
      toast.success("Bienvenue !");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const brand = settings.theme_primary || "#0f172a";

  return (
    <div className="qy-login flex items-center justify-center px-6 py-10" data-testid="login-page">
      {/* iter188 — Fond bleu nuit + arcs lumineux + carte glass, aligné à la maquette CPF */}
      <div className="qy-login__deco">
        <div className="qy-login__arc qy-login__arc--tl" />
        <div className="qy-login__arc qy-login__arc--r" />
        <div className="qy-login__arc qy-login__arc--br" />
      </div>
      <p className="qy-login__side qy-login__side--tr hidden sm:block">
        BÂTIR<br />AUJOURD'HUI<br />DEMAIN
      </p>
      <p className="qy-login__side qy-login__side--bl hidden sm:block">
        DES SOLUTIONS<br />POUR FAIRE GRANDIR<br />VOS AMBITIONS
      </p>

      <div className="w-full max-w-md qy-login__card px-7 py-8 sm:px-9 sm:py-10">
        {/* Logo hero */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="rounded-2xl shadow-[0_10px_40px_-12px_rgba(120,170,255,0.35)] overflow-hidden" data-testid="login-logo">
            {settings.logo ? (
              <img src={settings.logo} alt="logo" className="h-[80px] w-[80px] object-contain bg-white" />
            ) : (
              <QylotLogo size={80} />
            )}
          </div>
          <span className="font-display text-2xl font-semibold tracking-[0.28em] text-white mt-4">
            {settings.app_name || "QYLOT"}
          </span>
          <p className="text-sm text-slate-300/80 mt-2 max-w-xs">
            Vos chantiers. Vos clients. Votre croissance.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-5" data-testid="login-form">
          <div className="space-y-1 text-center">
            <p className="overline text-slate-300/70">Connexion</p>
            <h1 className="font-display text-xl font-semibold tracking-tight text-white">Bon retour parmi nous</h1>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" placeholder="vous@exemple.com" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Mot de passe</Label>
              <Input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" placeholder="••••••••" />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-100 bg-red-500/20 border border-red-400/40 rounded-md px-3 py-2" data-testid="login-error">
              {error}
            </div>
          )}

          <Button type="submit" disabled={loading} className="w-full h-11 bg-white text-slate-900 hover:bg-slate-100 shadow-lg" data-testid="login-submit-btn">
            {loading ? "Connexion…" : "Se connecter"}
          </Button>
        </form>
      </div>
    </div>
  );
}
