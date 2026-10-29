import { useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * iter55 : détecte quand une nouvelle version de l'application a été publiée
 * et propose à l'utilisateur de recharger — évite qu'il reste sur un ancien
 * bundle et croise des bugs déjà corrigés.
 *
 * Poll `/api/version` toutes les 90 secondes.
 * Une seule notif par session (flag `sessionStorage.kylot_version_notified`).
 */
export default function useVersionPoll() {
  const initial = useRef(null);
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const check = async () => {
      try {
        const r = await api.get("/version");
        const v = r?.data?.version;
        if (cancelled || !v) return;
        if (initial.current == null) { initial.current = v; return; }
        if (v !== initial.current && !sessionStorage.getItem("kylot_version_notified")) {
          sessionStorage.setItem("kylot_version_notified", "1");
          toast.message("Nouvelle version disponible", {
            description: "Rechargez pour profiter des dernières améliorations.",
            duration: Infinity,
            action: {
              label: "Recharger",
              onClick: () => {
                try {
                  if (typeof caches !== "undefined") caches.keys().then((ks) => ks.forEach((k) => caches.delete(k)));
                } catch (_) {}
                window.location.reload();
              },
            },
          });
        }
      } catch (_) { /* offline / down → réessaye plus tard */ }
    };
    check();
    timer = setInterval(check, 90_000);
    const onFocus = () => check();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, []);
}
