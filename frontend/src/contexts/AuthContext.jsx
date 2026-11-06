import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { syncOffline } from "@/lib/api";
import { prepareOfflineSession, clearSensitiveClientState, setOfflineIdentity } from "@/lib/offline";
import { canPerm, permScope } from "@/lib/permissions";
import { toast } from "sonner";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const r = await api.get("/auth/me");
      setOfflineIdentity(r.data?.id);
      // Ne pas remplacer l'objet utilisateur à chaque poll : cela provoque des
      // re-rendus inutiles et des sauts de mise en page en arrière-plan.
      setUser((prev) => (JSON.stringify(prev) === JSON.stringify(r.data) ? prev : r.data));
      syncOffline();
    } catch (error) {
      // A temporary network/provider failure must not impersonate a logout.
      // Only an explicit authentication refusal clears the confirmed identity;
      // the API interceptor also purges sensitive IndexedDB/session data on 401.
      if (error?.response?.status === 401) {
        setOfflineIdentity(null);
        setUser(null);
      }
    }
  }, []);

  useEffect(() => {
    // Remove legacy JavaScript-readable sessions. Authentication now relies on
    // an HttpOnly cookie that cannot be exfiltrated by frontend JavaScript.
    localStorage.removeItem("pylot_token");
    localStorage.removeItem("chantierpro_token");
    let cancelled = false;
    const bootstrap = async () => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const r = await api.get("/auth/me");
          if (cancelled) return;
          setOfflineIdentity(r.data?.id);
          setUser(r.data);
          syncOffline();
          return;
        } catch (error) {
          if (cancelled) return;
          if (error?.response?.status === 401) setOfflineIdentity(null);
          if (attempt < 2) {
            await new Promise((resolve) => setTimeout(resolve, 450));
            continue;
          }
          setOfflineIdentity(null);
          setUser(null);
        }
      }
    };
    bootstrap().finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Live-refresh the current user's profile (permissions, role, name) every 20s
  // so that admin-side changes (e.g. granting/revoking overtime access) are
  // reflected without requiring the user to log out and back in.
  useEffect(() => {
    if (!user) return;
    const id = setInterval(() => { refreshUser(); }, 60_000);
    const onFocus = () => refreshUser();
    // iter96 : refresh instantané quand l'admin bascule l'horloge Heures sup
    // ou modifie l'équipe (event dispatché depuis TeamSection / Users.jsx).
    const onTeamUpdated = () => refreshUser();
    window.addEventListener("focus", onFocus);
    window.addEventListener("kylot:team-updated", onTeamUpdated);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("kylot:team-updated", onTeamUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, refreshUser]);

  const establishSession = async (data) => {
    await prepareOfflineSession(data.user?.id);
    setUser(data.user);
    syncOffline();
    return data.user;
  };

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data?.mfa_required) {
      // Le cookie de session n'est pas encore posé : on garde uniquement le
      // défi signé, à court terme, le temps de saisir le code TOTP.
      return { mfa_required: true, challenge: data.challenge };
    }
    return establishSession(data);
  };

  const verifyMfa = async (challenge, code) => {
    const { data } = await api.post("/auth/mfa/verify", { challenge, code });
    return establishSession(data);
  };

  const register = async (name, email, password) => {
    const { data } = await api.post("/auth/register", { name, email, password });
    return establishSession(data);
  };

  const logout = async () => {
    let serverConfirmed = true;
    try {
      await api.post("/auth/logout");
    } catch (e) {
      // Le cookie est HttpOnly : si l'appel échoue, le navigateur ne peut pas
      // l'effacer lui-même. On purge quand même l'état local, mais on prévient
      // l'utilisateur que la session serveur peut rester active.
      serverConfirmed = false;
    }
    await clearSensitiveClientState(); // clears IndexedDB and kylot_ai_draft_v1 / kylot_prefill_sale
    setUser(null);
    if (!serverConfirmed) {
      toast.warning("Déconnexion locale effectuée, mais le serveur n'a pas confirmé. Fermez le navigateur sur un appareil partagé.");
    }
  };

  const can = useCallback((resource, action, minScope = "own") => canPerm(user, resource, action, minScope), [user]);
  const scope = useCallback((resource, action) => permScope(user, resource, action), [user]);

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyMfa, register, logout, can, scope, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
