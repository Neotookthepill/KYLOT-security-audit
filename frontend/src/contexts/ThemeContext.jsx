import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

const ThemeContext = createContext({ theme: "light", resolved: "light", setTheme: () => {} });
const STORAGE_KEY = "qylot-theme";

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored === "dark" ? "dark" : "light";
    } catch (_) { return "light"; }
  });
  const resolved = theme;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark");
    root.dataset.theme = resolved;
    root.style.colorScheme = resolved;
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) {}
  }, [resolved, theme]);

  const setTheme = (next) => {
    if (!["light", "dark"].includes(next)) return;
    setThemeState(next);
  };

  const value = useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
