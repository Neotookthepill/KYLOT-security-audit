import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const SettingsContext = createContext(null);

const DEFAULTS = {
  objectif_ca: 100000,
  theme_primary: "#0f172a",
  theme_accent: "#6366f1",
  font_family: "Inter",
  logo: "",
  app_name: "QYLOT",
  overtime_alert_threshold: 30,
};

const FONT_URLS = {
  Inter: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
  Outfit: "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap",
  Poppins: "https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap",
  Manrope: "https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap",
  Playfair: "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&display=swap",
  "Space Grotesk": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap",
  Montserrat: "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap",
  "DM Sans": "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap",
};

export const AVAILABLE_FONTS = Object.keys(FONT_URLS);

function loadFont(name) {
  const url = FONT_URLS[name];
  if (!url) return;
  const id = `font-${name.replace(/\s+/g, "-")}`;
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = url;
  document.head.appendChild(link);
}

function applyToRoot(s) {
  const root = document.documentElement;
  root.style.setProperty("--brand", s.theme_primary);
  root.style.setProperty("--brand-accent", s.theme_accent);
  root.style.setProperty("--font-app", `"${s.font_family}", "Inter", sans-serif`);
  loadFont(s.font_family);
  document.body.style.fontFamily = `"${s.font_family}", "Inter", sans-serif`;
}

// Local cache so the logo / app_name survive logout → login on the same device.
// Company_id in the key ensures we don't leak across companies.
const CACHE_PREFIX = "kylot_settings_cache";
const loadCache = (companyId) => {
  try {
    const raw = localStorage.getItem(`${CACHE_PREFIX}:${companyId || "default"}`);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
};
const saveCache = (companyId, s) => {
  try {
    localStorage.setItem(`${CACHE_PREFIX}:${companyId || "default"}`, JSON.stringify({
      logo: s.logo, app_name: s.app_name, theme_primary: s.theme_primary,
      theme_accent: s.theme_accent, font_family: s.font_family,
    }));
  } catch (_) {}
};

export function SettingsProvider({ children }) {
  const { user } = useAuth();
  const initialCompany = user?.company_id;
  // Seed from cache if available so the logo does NOT flash to the default plane
  // during the split-second between mount and the /settings response.
  const cached = loadCache(initialCompany);
  const [settings, setSettings] = useState({ ...DEFAULTS, ...(cached || {}) });
  const [loaded, setLoaded] = useState(false);
  const lastCompanyRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/settings");
      const merged = { ...DEFAULTS, ...data };
      setSettings(merged);
      applyToRoot(merged);
      saveCache(data?.company_id || user?.company_id, merged);
    } catch (e) {
      // Keep any cached / previous values instead of clobbering with defaults.
      applyToRoot(settings);
    } finally {
      setLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.company_id]);

  // Refetch whenever the authenticated user (or their company) changes.
  useEffect(() => {
    if (!user) {
      setLoaded(true);
      return;
    }
    if (lastCompanyRef.current === user.company_id) return;
    lastCompanyRef.current = user.company_id;
    // Preload cache for this company so the sidebar shows the right logo immediately
    const c = loadCache(user.company_id);
    if (c) {
      setSettings((prev) => ({ ...prev, ...c }));
      applyToRoot({ ...DEFAULTS, ...c });
    }
    refresh();
  }, [user, refresh]);

  const update = async (patch) => {
    const { data } = await api.put("/settings", patch);
    const merged = { ...DEFAULTS, ...data };
    setSettings(merged);
    applyToRoot(merged);
    saveCache(user?.company_id, merged);
    return merged;
  };

  return (
    <SettingsContext.Provider value={{ settings, loaded, refresh, update }}>
      {children}
    </SettingsContext.Provider>
  );
}

export const useSettings = () => useContext(SettingsContext) || { settings: DEFAULTS, loaded: true, refresh: () => {}, update: async () => {} };
