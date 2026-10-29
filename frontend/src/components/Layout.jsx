import React, { useState } from "react";
import { OfflineBar } from "@/components/OfflineBar";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { APP_VERSION } from "@/version";
import { useSettings } from "@/contexts/SettingsContext";
import {
  LayoutDashboard, ShoppingBag, Kanban as KanbanIcon, CalendarDays,
  Users as UsersIcon, Shield, Percent, LogOut, Plane, Settings as SettingsIcon, Star, BarChart3, Clock, Building2, Menu, History, Boxes, TrendingUp, Search, UserSearch, Map as MapIcon,
} from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import GlobalSearchDialog from "@/components/GlobalSearchDialog";
import OnboardingDialog from "@/components/OnboardingDialog";

// Nav entries gated by permission check. `perm` = [resource, action, minScope]
const allNav = [
  { to: "/", label: "Tableau de bord", icon: LayoutDashboard, end: true, tid: "nav-dashboard", perm: ["sales", "view", "own"] },
  { to: "/ventes", label: "Ventes", icon: ShoppingBag, tid: "nav-sales", perm: ["sales", "view", "own"] },
  { to: "/rapport", label: "Rapport mensuel", icon: BarChart3, tid: "nav-report", perm: ["reports", "view"] },
  { to: "/progression", label: "Progression annuelle", icon: TrendingUp, tid: "nav-progression", perm: ["sales", "view", "own"] },
  // iter208 : masquer « Chantiers » pour techniciens/sous-traitants — ils n'utilisent
  // que le Planning. La page reste accessible pour admins/responsables/commerciaux.
  { to: "/chantiers", label: "Chantiers", icon: KanbanIcon, tid: "nav-kanban", perm: ["projects", "view", "own"], denyRoles: ["technicien", "sous_traitant"] },
  { to: "/planning", label: "Planning", icon: CalendarDays, tid: "nav-calendar", perm: ["planning", "view", "own"] },
  { to: "/heures-sup", label: "Heures sup", icon: Clock, tid: "nav-overtime", perm: ["overtime", "view", "own"], techAllow: true },
  { to: "/commissions", label: "Commissions", icon: Percent, tid: "nav-commissions", perm: ["commissions", "view", "own"] },
  { to: "/prospecteur", label: "Prospecteur", icon: UserSearch, tid: "nav-prospecteur", roles: ["admin", "responsable", "responsable_prospecteur", "prospecteur"] },
  { to: "/stock", label: "Stock", icon: Boxes, tid: "nav-stock", perm: ["stock", "view"] },
  { to: "/clients", label: "Clients", icon: UsersIcon, tid: "nav-clients", perm: ["clients", "view", "own"] },
  { to: "/carte", label: "Carte", icon: MapIcon, tid: "nav-map", perm: ["clients", "view", "own"] },
  { to: "/utilisateurs", label: "Utilisateurs", icon: Shield, tid: "nav-users", perm: ["users", "manage"] },
  { to: "/journal", label: "Journal d'activité", icon: History, tid: "nav-journal", perm: ["users", "manage"] },
  { to: "/entreprises", label: "Entreprises", icon: Building2, tid: "nav-companies", superOnly: true },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  const { settings } = useSettings();
  const nav_ = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const isSuper = user?.role === "super_admin";
  // iter169 : raccourci Cmd/Ctrl+K
  React.useEffect(() => {
    if (isSuper) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isSuper]);
  const nav = allNav.filter((n) => {
    if (n.superOnly) return isSuper;
    if (isSuper) return false; // super-admin only sees Entreprises + logout
    if (n.denyRoles && n.denyRoles.includes(user?.role)) return false;
    if (n.roles) return n.roles.includes(user?.role);
    if (n.to === "/planning" && ["prospecteur", "responsable_prospecteur"].includes(user?.role)) return true;
    if (!n.perm) return true;
    const [r, a, s] = n.perm;
    if (can(r, a, s)) return true;
    if (n.techAllow && user?.role === "technicien" && can("overtime", "declare")) return true;
    return false;
  });
  const brand = settings.theme_primary || "#0f172a";
  const accent = settings.theme_accent || "#6366f1";
  const appName = settings.app_name || "KEYLOT";
  const canSettings = can("settings", "modify");

  const Sidebar = (
    <aside className="w-64 shrink-0 flex flex-col text-white h-full" style={{ background: brand }}>
      <div className="pt-8 pb-6 px-5 flex flex-col items-center border-b border-white/10">
        <div className="h-24 w-24 rounded-full bg-white shadow-lg overflow-hidden grid place-items-center ring-4 ring-white/10">
          {settings.logo ? (
            <img src={settings.logo} alt="logo" className="h-full w-full object-contain p-2" />
          ) : (
            <Plane size={40} style={{ color: brand }} />
          )}
        </div>
        <div className="mt-3 text-center">
          <div className="font-display font-bold text-lg tracking-wider">{appName}</div>
          <div className="text-[10px] uppercase tracking-widest text-white/60 mt-0.5">Ventes & Planning</div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {nav.map(({ to, label, icon: Icon, end, tid }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            data-testid={tid}
            onClick={() => setMobileOpen(false)}
            style={({ isActive }) => isActive ? { background: "rgba(255,255,255,0.15)" } : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${isActive ? "text-white" : "text-white/75 hover:bg-white/10 hover:text-white"}`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-3 border-t border-white/10 space-y-1">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="h-9 w-9 rounded-full grid place-items-center text-white font-semibold text-sm" style={{ background: accent }}>
            {(user?.name || "?").charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-white truncate">{user?.name}</div>
            <div className="text-[10px] uppercase tracking-wider text-white/50">{user?.role}</div>
          </div>
          {!isSuper && (
            <button
              onClick={() => setSearchOpen(true)}
              data-testid="global-search-btn"
              aria-label="Recherche globale"
              title="Recherche globale (⌘K)"
              className="p-2 rounded-md text-white/70 hover:bg-white/10 hover:text-white transition-colors"
            >
              <Search size={16} />
            </button>
          )}
          {!isSuper && <NotificationBell tone="dark" />}
          <button
            onClick={async () => { await logout(); nav_("/login"); }}
            data-testid="logout-btn"
            aria-label="Se déconnecter"
            className="p-2 rounded-md text-white/70 hover:bg-white/10 hover:text-white transition-colors"
          >
            <LogOut size={16} />
          </button>
        </div>
        <p className="text-[9px] uppercase tracking-[0.2em] text-white/30 px-2 pt-1 select-none" data-testid="sidebar-app-version" title={`Build ${APP_VERSION}`}>
          v · {APP_VERSION}
        </p>
        {user?.role === "admin" && (
          <NavLink
            to="/abonnement"
            data-testid="nav-subscription"
            onClick={() => setMobileOpen(false)}
            style={({ isActive }) => isActive ? { background: "rgba(255,255,255,0.15)" } : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? "text-white" : "text-white/75 hover:bg-white/10 hover:text-white"}`
            }
          >
            <Star size={16} />
            Abonnement
          </NavLink>
        )}
        {canSettings && !isSuper && (
          <NavLink
            to="/parametres"
            data-testid="nav-settings"
            onClick={() => setMobileOpen(false)}
            style={({ isActive }) => isActive ? { background: "rgba(255,255,255,0.15)" } : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? "text-white" : "text-white/75 hover:bg-white/10 hover:text-white"}`
            }
          >
            <SettingsIcon size={16} />
            Paramètres
          </NavLink>
        )}
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen flex bg-[#F9FAFB]">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">{Sidebar}</div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden" data-testid="mobile-drawer">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 shadow-xl">{Sidebar}</div>
        </div>
      )}

      <main className="flex-1 min-w-0 pb-24 md:pb-0">
        {/* Mobile top bar */}
        <div className="md:hidden sticky top-0 z-30 flex items-center gap-3 px-3 py-2 border-b bg-white/95 backdrop-blur">
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Ouvrir le menu"
            data-testid="mobile-menu-btn"
            className="h-9 w-9 grid place-items-center rounded-md hover:bg-slate-100"
          >
            <Menu size={20} />
          </button>
          <div className="font-display font-semibold tracking-wide" style={{ color: brand }}>{appName}</div>
          <div className="ml-auto flex items-center gap-1">
            {!isSuper && (
              <button
                onClick={() => setSearchOpen(true)}
                data-testid="global-search-btn-mobile"
                aria-label="Recherche globale"
                className="h-9 w-9 grid place-items-center rounded-md hover:bg-slate-100 text-slate-500"
              >
                <Search size={18} />
              </button>
            )}
            {!isSuper && <NotificationBell tone="light" />}
            <button
              onClick={async () => { await logout(); nav_("/login"); }}
              aria-label="Se déconnecter"
              className="h-9 w-9 grid place-items-center rounded-md hover:bg-slate-100 text-slate-500"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <OfflineBar />
        <Outlet />
      </main>
      {!isSuper && <GlobalSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />}
      {!isSuper && <OnboardingDialog />}
    </div>
  );
}
