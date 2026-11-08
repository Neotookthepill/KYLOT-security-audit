import React, { useMemo, useState } from "react";
import { OfflineBar } from "@/components/OfflineBar";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { APP_VERSION } from "@/version";
import { useSettings } from "@/contexts/SettingsContext";
import {
  LayoutDashboard, ShoppingBag, Kanban as KanbanIcon, CalendarDays,
  Users as UsersIcon, Shield, Percent, LogOut, Settings as SettingsIcon, Star,
  BarChart3, Clock, Building2, Menu, History, Boxes, TrendingUp, Search,
  UserSearch, Map as MapIcon, Plus, ChevronsLeft, ChevronsRight, Sparkles,
} from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import GlobalSearchDialog from "@/components/GlobalSearchDialog";
import OnboardingDialog from "@/components/OnboardingDialog";
import MfaRequiredNotice from "@/components/MfaRequiredNotice";
import NewSaleSheet from "@/components/NewSaleSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";
import useAccessibleLabels from "@/hooks/useAccessibleLabels";

const allNav = [
  { to: "/", label: "Tableau de bord", short: "Accueil", icon: LayoutDashboard, end: true, tid: "nav-dashboard", perm: ["sales", "view", "own"], group: "Pilotage" },
  { to: "/ventes", label: "Ventes", icon: ShoppingBag, tid: "nav-sales", perm: ["sales", "view", "own"], group: "Pilotage" },
  { to: "/rapport", label: "Rapport mensuel", icon: BarChart3, tid: "nav-report", perm: ["reports", "view"], group: "Pilotage" },
  { to: "/progression", label: "Progression annuelle", icon: TrendingUp, tid: "nav-progression", perm: ["sales", "view", "own"], group: "Pilotage" },
  { to: "/commissions", label: "Commissions", icon: Percent, tid: "nav-commissions", perm: ["commissions", "view", "own"], group: "Commercial" },
  { to: "/clients", label: "Clients", icon: UsersIcon, tid: "nav-clients", perm: ["clients", "view", "own"], group: "Commercial" },
  { to: "/prospecteur", label: "Prospection", icon: UserSearch, tid: "nav-prospecteur", roles: ["admin", "responsable", "responsable_prospecteur", "prospecteur"], group: "Commercial" },
  { to: "/chantiers", label: "Chantiers", icon: KanbanIcon, tid: "nav-kanban", perm: ["projects", "view", "own"], denyRoles: ["technicien", "sous_traitant"], group: "Terrain" },
  { to: "/planning", label: "Planning", icon: CalendarDays, tid: "nav-calendar", perm: ["planning", "view", "own"], group: "Terrain" },
  { to: "/heures-sup", label: "Heures sup", icon: Clock, tid: "nav-overtime", perm: ["overtime", "view", "own"], techAllow: true, group: "Terrain" },
  { to: "/stock", label: "Stock", icon: Boxes, tid: "nav-stock", perm: ["stock", "view"], group: "Terrain" },
  { to: "/carte", label: "Carte", icon: MapIcon, tid: "nav-map", perm: ["clients", "view", "own"], group: "Terrain" },
  { to: "/utilisateurs", label: "Utilisateurs", icon: Shield, tid: "nav-users", perm: ["users", "manage"], group: "Administration" },
  { to: "/journal", label: "Journal d'activité", icon: History, tid: "nav-journal", perm: ["users", "manage"], group: "Administration" },
  { to: "/entreprises", label: "Entreprises", icon: Building2, tid: "nav-companies", superOnly: true, group: "Administration" },
];
const GROUP_ORDER = ["Pilotage", "Commercial", "Terrain", "Administration"];

function initials(name) {
  return String(name || "?")
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase()).join("");
}

export default function Layout() {
  useAccessibleLabels();
  const { user, logout, can } = useAuth();
  const { settings } = useSettings();
  const navigate = useNavigate();
  const location = useLocation();
  React.useEffect(() => {
    // Évite d'arriver au milieu d'une page longue après un changement de route.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [location.pathname]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [newSaleOpen, setNewSaleOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("qylot-sidebar-collapsed") === "1"; } catch (_) { return false; }
  });
  const isSuper = user?.role === "super_admin";

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

  const toggleCollapsed = () => setCollapsed((v) => {
    const next = !v;
    try { localStorage.setItem("qylot-sidebar-collapsed", next ? "1" : "0"); } catch (_) {}
    return next;
  });

  const nav = useMemo(() => allNav.filter((n) => {
    if (n.superOnly) return isSuper;
    if (isSuper) return false;
    if (n.denyRoles && n.denyRoles.includes(user?.role)) return false;
    if (n.roles) return n.roles.includes(user?.role);
    if (n.to === "/planning" && ["prospecteur", "responsable_prospecteur"].includes(user?.role)) return true;
    if (!n.perm) return true;
    const [r, a, s] = n.perm;
    if (can(r, a, s)) return true;
    if (n.techAllow && user?.role === "technicien" && can("overtime", "declare")) return true;
    return false;
  }), [user, isSuper, can]);

  const groups = useMemo(() => {
    const map = new Map();
    for (const item of nav) {
      if (!map.has(item.group)) map.set(item.group, []);
      map.get(item.group).push(item);
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => [g, map.get(g)]);
  }, [nav]);

  const current = nav.find((n) => n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to));
  const currentTitle = current?.label || (location.pathname === "/abonnement" ? "Abonnement" : location.pathname === "/parametres" ? "Paramètres" : "Qylot");
  const brand = settings.theme_primary || "#0b1220";
  const appName = settings.app_name || "Qylot";
  const canSettings = can("settings", "modify");
  const canCreateSale = can("sales", "create");
  const mobileNav = nav.filter((n) => ["/", "/ventes", "/planning", "/clients"].includes(n.to)).slice(0, 4);
  const today = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(new Date());

  const closeMobile = () => setMobileOpen(false);

  const NavItem = ({ item, compact = false }) => {
    const Icon = item.icon;
    return (
      <NavLink
        to={item.to}
        end={item.end}
        data-testid={item.tid}
        onClick={closeMobile}
        title={compact ? item.label : undefined}
        className={({ isActive }) => cn("qy-nav-item", isActive && "is-active", compact && "justify-center px-0")}
      >
        <Icon size={17} strokeWidth={1.9} className="shrink-0" />
        {!compact && <span className="truncate">{item.label}</span>}
      </NavLink>
    );
  };

  const SidebarContent = ({ compact = false, inDrawer = false }) => (
    <aside
      className={cn("qy-sidebar flex h-full flex-col shrink-0 transition-[width] duration-200", compact ? "w-[78px]" : "w-[240px]")}
      style={{ background: brand }}
      data-testid="sidebar"
    >
      <div className={cn("flex items-center border-b border-white/[.08]", compact ? "justify-center px-2 py-5" : "gap-3 px-4 pt-6 pb-5")}>
        <div className="qy-brand-mark shrink-0">
          {settings.logo ? <img src={settings.logo} alt="logo" className="h-full w-full object-contain p-1.5" /> : <img src="/brand/qylot-mark-light.svg?v=2" alt="Qylot" className="h-full w-full object-contain" />}
        </div>
        {!compact && (
          <div className="min-w-0">
            <div className="font-display text-[19px] font-semibold leading-none tracking-[-.02em] text-white">{appName}</div>
            <div className="mt-1.5 text-[9px] uppercase tracking-[.2em] text-white/65">Chantiers & croissance</div>
          </div>
        )}
        {!inDrawer && !compact && (
          <button type="button" onClick={toggleCollapsed} className="ml-auto grid h-7 w-7 place-items-center rounded-md text-white/65 hover:bg-white/10 hover:text-white" aria-label="Replier le menu" title="Replier le menu">
            <ChevronsLeft size={15} />
          </button>
        )}
        {!inDrawer && compact && (
          <button type="button" onClick={toggleCollapsed} className="absolute left-[62px] top-7 z-10 grid h-6 w-6 place-items-center rounded-full border border-white/10 bg-[#111a29] text-white/60 shadow hover:text-white" aria-label="Déplier le menu" title="Déplier le menu">
            <ChevronsRight size={13} />
          </button>
        )}
      </div>

      {!isSuper && (
        <div className={cn("px-3 pt-3", compact && "px-2")}>
          {canCreateSale && (
            <button
              type="button"
              onClick={() => { closeMobile(); setNewSaleOpen(true); }}
              data-testid="sidebar-quick-create"
              className={cn("qy-quick-create flex w-full items-center justify-center gap-2 rounded-[10px] px-3 py-2.5 text-[13px] font-semibold", compact && "px-0")}
              title="Nouvelle vente"
            >
              <Plus size={16} strokeWidth={2.2} />
              {!compact && "Nouvelle vente"}
            </button>
          )}
          {!compact && (
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              data-testid="sidebar-search"
              className="mt-2 flex w-full items-center gap-2 rounded-[10px] border border-white/[.08] bg-white/[.035] px-3 py-2 text-left text-[12px] text-white/65 hover:border-white/15 hover:text-white/75"
            >
              <Search size={14} />
              <span className="flex-1">Rechercher…</span>
              <kbd className="rounded border border-white/10 px-1 py-0.5 text-[9px] text-white/60">⌘K</kbd>
            </button>
          )}
        </div>
      )}

      <nav className={cn("qy-sidebar-nav flex-1 overflow-y-auto pb-4", compact ? "px-2 pt-3" : "px-3 pt-2")} aria-label="Navigation principale" data-testid="sidebar-nav">
        {groups.map(([group, items]) => (
          <div key={group}>
            {!compact && <div className="qy-nav-group-label">{group}</div>}
            <div className="space-y-0.5">
              {items.map((item) => <NavItem key={item.to} item={item} compact={compact} />)}
            </div>
          </div>
        ))}
      </nav>

      <div className={cn("border-t border-white/[.08] pb-3", compact ? "px-2 pt-2" : "px-3 pt-2")}>
        {compact && (
          <button type="button" onClick={toggleCollapsed} title="Déplier le menu" aria-label="Déplier le menu" className="qy-nav-item mb-1 w-full justify-center px-0">
            <ChevronsRight size={17} />
          </button>
        )}
        {!isSuper && (
          <NavLink to="/abonnement" data-testid="nav-subscription" onClick={closeMobile} title={compact ? "Abonnement" : undefined} className={({ isActive }) => cn("qy-nav-item", isActive && "is-active", compact && "justify-center px-0")}>
            <Star size={17} strokeWidth={1.9} />
            {!compact && <span>Abonnement</span>}
          </NavLink>
        )}
        {canSettings && !isSuper && (
          <NavLink to="/parametres" data-testid="nav-settings" onClick={closeMobile} title={compact ? "Paramètres" : undefined} className={({ isActive }) => cn("qy-nav-item", isActive && "is-active", compact && "justify-center px-0")}>
            <SettingsIcon size={17} strokeWidth={1.9} />
            {!compact && <span>Paramètres</span>}
          </NavLink>
        )}
        {!isSuper && (
          <button
            type="button"
            onClick={() => { closeMobile(); setTimeout(() => window.dispatchEvent(new Event("kylot:open-ai")), 120); }}
            title={compact ? "Assistant Qylot" : undefined}
            className={cn("qy-nav-item w-full", compact && "justify-center px-0")}
            aria-label="Ouvrir l’assistant IA"
          >
            <Sparkles size={17} strokeWidth={1.9} />
            {!compact && <span>Assistant Qylot</span>}
          </button>
        )}
        <div className={cn("mt-2 flex items-center gap-2 border-t border-white/[.08] pt-3", compact && "justify-center")}>
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#0b1220] text-[11px] font-semibold text-[#f7f3e9] ring-1 ring-white/20" title={user?.name}>
            {initials(user?.name)}
          </div>
          {!compact && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-medium text-white/90">{user?.name}</div>
              <div className="text-[9px] uppercase tracking-[.13em] text-white/60">{user?.role}</div>
            </div>
          )}
          <button type="button" onClick={async () => { await logout(); navigate("/login"); }} data-testid="logout-btn" aria-label="Se déconnecter" className="grid h-8 w-8 place-items-center rounded-md text-white/55 hover:bg-white/10 hover:text-white" title="Se déconnecter">
            <LogOut size={15} />
          </button>
        </div>
        {!compact && (
          <p className="mt-2 px-1 text-[9px] uppercase tracking-[.18em] text-white/50" data-testid="sidebar-app-version">v · {APP_VERSION}</p>
        )}
      </div>
    </aside>
  );

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <div className="sticky top-0 hidden h-screen shrink-0 md:block">
        {SidebarContent({ compact: collapsed })}
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden" data-testid="mobile-drawer">
          <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={closeMobile} />
          <div className="absolute left-0 top-0 bottom-0 shadow-2xl">
            {SidebarContent({ inDrawer: true })}
          </div>
        </div>
      )}

      <main className="min-w-0 flex-1 pb-24 md:pb-0">
        {/* Mobile top bar */}
        <div className="qy-topbar sticky top-0 z-30 flex items-center gap-2 px-3 py-2 md:hidden">
          <button type="button" onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu" data-testid="mobile-menu-btn" className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
            <Menu size={20} />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            {settings.logo ? <img src={settings.logo} alt="logo" className="qy-brand-mark h-7 w-7 rounded-lg object-contain p-0.5" /> : <img src="/brand/qylot-mark-light.svg?v=2" alt="Qylot" className="qy-brand-mark h-7 w-7 rounded-lg object-contain" />}
            <div className="min-w-0 leading-tight">
              <div className="truncate font-display text-[15px] font-semibold tracking-[-.02em]">{appName}</div>
              <div className="truncate text-[9px] font-medium text-muted-foreground">{currentTitle}</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-1">
            {!isSuper && (
              <button type="button" onClick={() => setSearchOpen(true)} data-testid="global-search-btn-mobile" aria-label="Recherche globale" className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
                <Search size={18} />
              </button>
            )}
            <ThemeToggle compact />
            {!isSuper && <NotificationBell tone="light" />}
            <button type="button" onClick={async () => { await logout(); navigate("/login"); }} aria-label="Se déconnecter" className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
              <LogOut size={16} />
            </button>
          </div>
        </div>

        {/* Desktop top bar */}
        <div className="qy-topbar sticky top-0 z-30 hidden items-center gap-4 px-6 py-3 md:flex">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>{appName}</span><span className="text-border">/</span><span className="font-medium text-foreground">{currentTitle}</span>
            </div>
            <div className="mt-0.5 truncate text-[11px] capitalize text-muted-foreground">{today}</div>
          </div>
          {!isSuper && (
            <button type="button" onClick={() => setSearchOpen(true)} data-testid="global-search-btn" className="flex h-9 w-[240px] items-center gap-2 rounded-lg border border-border bg-card px-3 text-left text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground xl:w-[300px]">
              <Search size={14} />
              <span className="flex-1">Rechercher un client, une vente…</span>
              <kbd className="rounded border border-border px-1 py-0.5 text-[9px]">⌘K</kbd>
            </button>
          )}
          <ThemeToggle />
          {!isSuper && <NotificationBell tone="light" />}
          <div className="flex items-center gap-2 border-l border-border pl-3">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">{initials(user?.name)}</div>
            <div className="hidden min-w-0 xl:block">
              <div className="max-w-[140px] truncate text-xs font-semibold">{user?.name}</div>
              <div className="text-[9px] uppercase tracking-[.14em] text-muted-foreground">{user?.role}</div>
            </div>
          </div>
        </div>

        <OfflineBar />
        <MfaRequiredNotice />
        <div className="qy-page">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom nav */}
      {!isSuper && mobileNav.length > 0 && (
        <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden" aria-label="Navigation mobile">
          <div className="grid" style={{ gridTemplateColumns: `repeat(${mobileNav.length + 1}, minmax(0, 1fr))` }}>
            {mobileNav.map((item) => {
              const Icon = item.icon;
              const active = item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
              return (
                <NavLink key={item.to} to={item.to} className={cn("flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium", active ? "text-primary" : "text-muted-foreground")} data-testid={`mobile-${item.tid}`}>
                  <Icon size={19} strokeWidth={active ? 2.2 : 1.8} />
                  {item.short || item.label.split(" ")[0]}
                </NavLink>
              );
            })}
            <button type="button" onClick={() => setMobileOpen(true)} className="flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium text-muted-foreground" aria-label="Plus de navigation">
              <Menu size={19} strokeWidth={1.8} />
              Plus
            </button>
          </div>
        </nav>
      )}

      {!isSuper && <GlobalSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />}
      {!isSuper && <OnboardingDialog />}
      {canCreateSale && <NewSaleSheet open={newSaleOpen} onOpenChange={setNewSaleOpen} onCreated={() => window.dispatchEvent(new Event("kylot:sales-updated"))} />}
    </div>
  );
}
