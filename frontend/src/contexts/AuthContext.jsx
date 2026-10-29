import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { syncOffline } from "@/lib/api";
import { clearOfflineData, clearSensitiveClientState, clearSensitiveSessionStorage, setOfflineIdentity } from "@/lib/offline";
import { canPerm, permScope } from "@/lib/permissions";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const r = await api.get("/auth/me");
      setOfflineIdentity(r.data?.id);
      setUser(r.data);
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
    api.get("/auth/me")
      .then((r) => {
        setOfflineIdentity(r.data?.id);
        setUser(r.data);
        syncOffline();
      })
      .catch(() => {
        setOfflineIdentity(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  // Live-refresh the current user's profile (permissions, role, name) every 20s
  // so that admin-side changes (e.g. granting/revoking overtime access) are
  // reflected without requiring the user to log out and back in.
  useEffect(() => {
    if (!user) return;
    const id = setInterval(() => { refreshUser(); }, 20_000);
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

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    await clearOfflineData();
    clearSensitiveSessionStorage();
    setOfflineIdentity(data.user?.id);
    setUser(data.user);
    return data.user;
  };

  const register = async (name, email, password) => {
    const { data } = await api.post("/auth/register", { name, email, password });
    await clearOfflineData();
    clearSensitiveSessionStorage();
    setOfflineIdentity(data.user?.id);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { /* ignore */ }
    await clearSensitiveClientState(); // clears IndexedDB and kylot_ai_draft_v1 / kylot_prefill_sale
    setUser(null);
  };

  const can = useCallback((resource, action, minScope = "own") => canPerm(user, resource, action, minScope), [user]);
  const scope = useCallback((resource, action) => permScope(user, resource, action), [user]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, can, scope, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
