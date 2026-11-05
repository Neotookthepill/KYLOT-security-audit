import React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/lib/utils";

export default function ThemeToggle({ tone = "light", className = "", compact = false }) {
  const { theme, resolved, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : "light";
  const label = theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre";
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      data-testid="theme-toggle"
      aria-label={label}
      title={`${label} — cliquer pour changer`}
      className={cn(
        "inline-flex items-center justify-center rounded-lg transition-colors",
        compact ? "h-9 w-9" : "h-9 gap-2 px-2.5 text-xs font-medium",
        tone === "dark"
          ? "text-white/70 hover:bg-white/10 hover:text-white"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      <Icon size={16} />
      {!compact && <span className="hidden xl:inline">{theme === "dark" ? "Clair" : "Sombre"}</span>}
    </button>
  );
}
