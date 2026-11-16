import React, { useEffect, useState } from "react";
import { useTheme } from "@/contexts/ThemeContext";

const KEY = "qylot-intro-seen";

export default function IntroSplash() {
  const { resolved } = useTheme();
  const [visible, setVisible] = useState(true);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    let seen = false;
    try { seen = sessionStorage.getItem(KEY) === "1"; } catch (_) {}
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (seen || reduced) { setVisible(false); return; }
    const fade = window.setTimeout(() => setLeaving(true), 1350);
    const done = window.setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem(KEY, "1"); } catch (_) {}
    }, 1800);
    return () => { clearTimeout(fade); clearTimeout(done); };
  }, []);

  if (!visible) return null;

  return (
    <div
      className={`qy-intro ${leaving ? "is-leaving" : ""} ${resolved === "dark" ? "is-dark" : "is-light"}`}
      role="status"
      aria-label="Ouverture de Qylot"
      data-testid="qylot-intro"
    >
      <div className="qy-intro-inner">
        <img src="/brand/qylot-logo-nuit-azur.png" alt="Qylot" className="qy-intro-logo" />
        <div className="qy-intro-word">Qylot</div>
        <div className="qy-intro-line"><span /></div>
        <div className="qy-intro-caption">Vos ventes. Vos chantiers. Votre équipe.</div>
      </div>
    </div>
  );
}
