import React, { useState, useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Sales from "@/pages/Sales";
import MonthlyReport from "@/pages/MonthlyReport";
import HeuresSup from "@/pages/HeuresSup";
import Kanban from "@/pages/Kanban";
import CalendarPage from "@/pages/CalendarPage";
import Clients from "@/pages/Clients";
import Users from "@/pages/Users";
import Companies from "@/pages/Companies";
import Journal from "@/pages/Journal";
import Commissions from "@/pages/Commissions";
import Progression from "@/pages/Progression";
import Stock from "@/pages/Stock";
import Prospecteur from "@/pages/Prospecteur";
import MapPage from "@/pages/MapPage";
import Settings from "@/pages/Settings";
import Abonnement from "@/pages/Abonnement";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import AIHelper from "@/components/AIHelper";
import ErrorBoundary, { AppErrorFallback } from "@/components/ErrorBoundary";
import SplashScreen from "@/components/SplashScreen";
import { SettingsProvider } from "@/contexts/SettingsContext";
import useVersionPoll from "@/hooks/useVersionPoll";

const PROSPECT_ROLES = ["prospecteur", "responsable_prospecteur"];

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50" data-testid="app-loading">
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <div className="h-8 w-8 rounded-full border-2 border-slate-200 border-t-slate-900 animate-spin" />
        <p className="text-sm">Chargement…</p>
      </div>
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  return <ErrorBoundary fallback={AppErrorFallback}>{children}</ErrorBoundary>;
}

function PermRoute({ perm, minScope = "own", children, fallback = "/planning", superOnly = false, allowRoles = [] }) {
  const { user, can } = useAuth();
  if (superOnly) {
    if (user?.role !== "super_admin") return <Navigate to={fallback} replace />;
    return children;
  }
  if (!perm || allowRoles.includes(user?.role)) return children;
  const [r, a] = perm;
  if (!can(r, a, minScope)) return <Navigate to={PROSPECT_ROLES.includes(user?.role) ? "/prospecteur" : fallback} replace />;
  return children;
}

function HomeRedirect() {
  const { user, can } = useAuth();
  if (user?.role === "super_admin") return <Navigate to="/entreprises" replace />;
  // iter208 : techniciens/sous-traitants redirigés vers le Planning (Chantiers masqué)
  if (user?.role === "technicien" || user?.role === "sous_traitant") return <Navigate to="/planning" replace />;
  if (PROSPECT_ROLES.includes(user?.role)) return <Navigate to="/prospecteur" replace />;
  if (can("sales", "view", "own")) return <Dashboard />;
  if (can("commissions", "view", "own")) return <Navigate to="/commissions" replace />;
  if (can("projects", "view", "own")) return <Navigate to="/chantiers" replace />;
  return <Navigate to="/parametres" replace />;
}

function AppRoutes() {
  const { user } = useAuth();
  useVersionPoll();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/payment/success" element={<Protected><PaymentSuccess /></Protected>} />
      <Route path="/payment/cancel" element={<Protected><PaymentCancel /></Protected>} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route path="ventes" element={<PermRoute perm={["sales","view"]}><Sales /></PermRoute>} />
        <Route path="rapport" element={<PermRoute perm={["reports","view"]}><MonthlyReport /></PermRoute>} />
        <Route path="progression" element={<PermRoute perm={["sales","view"]}><Progression /></PermRoute>} />
        <Route path="heures-sup" element={<PermRoute perm={["overtime","view"]}><HeuresSup /></PermRoute>} />
        <Route path="chantiers" element={<PermRoute perm={["projects","view"]}><Kanban /></PermRoute>} />
        <Route path="planning" element={<PermRoute perm={["planning","view"]} allowRoles={PROSPECT_ROLES}><CalendarPage /></PermRoute>} />
        <Route path="clients" element={<PermRoute perm={["clients","view"]}><Clients /></PermRoute>} />
        <Route path="carte" element={<PermRoute perm={["clients","view"]}><MapPage /></PermRoute>} />
        <Route path="commissions" element={<PermRoute perm={["commissions","view"]}><Commissions /></PermRoute>} />
        <Route path="prospecteur" element={["admin", "responsable", ...PROSPECT_ROLES].includes(user?.role) ? <Prospecteur /> : <Navigate to="/" replace />} />
        <Route path="stock" element={<PermRoute perm={["stock","view"]}><Stock /></PermRoute>} />
        <Route path="utilisateurs" element={<PermRoute perm={["users","manage"]}><Users /></PermRoute>} />
        <Route path="journal" element={<PermRoute perm={["users","manage"]}><Journal /></PermRoute>} />
        <Route path="entreprises" element={<PermRoute superOnly><Companies /></PermRoute>} />
        <Route path="parametres" element={<PermRoute perm={["settings","modify"]}><Settings /></PermRoute>} />
        <Route path="abonnement" element={<PermRoute perm={["settings","modify"]}><Abonnement /></PermRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  const [splashDone, setSplashDone] = useState(false);
  // iter54: guards globaux — capturent les erreurs qui échappent aux ErrorBoundary
  // (Promise rejections, exceptions dans handlers async, etc.) et empêchent
  // l'écran blanc en surface visible via l'ErrorBoundary racine.
  useEffect(() => {
    const onUnhandled = (e) => {
      try {
        const msg = String((e && (e.reason?.message || e.reason || e.message)) || "");
        if (/ChunkLoadError|Loading chunk .* failed|Failed to fetch dynamically imported/i.test(msg)) {
          if (!sessionStorage.getItem("kylot_chunk_reloaded")) {
            sessionStorage.setItem("kylot_chunk_reloaded", "1");
            window.location.reload();
          }
        }
      } catch (_) {}
    };
    window.addEventListener("unhandledrejection", onUnhandled);
    window.addEventListener("error", onUnhandled);
    return () => {
      window.removeEventListener("unhandledrejection", onUnhandled);
      window.removeEventListener("error", onUnhandled);
    };
  }, []);
  return (
    <div className="App">
      {!splashDone && <SplashScreen onDone={() => setSplashDone(true)} />}
      <ErrorBoundary fallback={AppErrorFallback}>
        <AuthProvider>
          <SettingsProvider>
            <BrowserRouter>
              <ErrorBoundary fallback={AppErrorFallback}>
                <AppRoutes />
              </ErrorBoundary>
              <AuthedAIHelper />
            </BrowserRouter>
            <Toaster position="top-right" richColors />
          </SettingsProvider>
        </AuthProvider>
      </ErrorBoundary>
    </div>
  );
}

function AuthedAIHelper() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <ErrorBoundary>
      <AIHelper />
    </ErrorBoundary>
  );
}
