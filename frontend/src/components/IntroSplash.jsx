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
    const fade = window.setTimeout(() => setLeaving(true), 1900);
    const done = window.setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem(KEY, "1"); } catch (_) {}
    }, 2360);
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
      <div className="qy-intro-atmosphere" aria-hidden="true">
        <span className="qy-intro-glow qy-intro-glow-a" />
        <span className="qy-intro-glow qy-intro-glow-b" />
        <span className="qy-intro-grid" />
      </div>
      <div className="qy-intro-inner">
        <div className="qy-intro-kicker">QYLOT <span>·</span> ESPACE PROFESSIONNEL</div>
        <div className="qy-intro-mark-shell">
          <span className="qy-intro-orbit" aria-hidden="true" />
          <span className="qy-intro-halo" aria-hidden="true" />
          <img src="/brand/qylot-logo-nuit-azur.png" alt="Qylot" className="qy-intro-logo" />
        </div>
        <div className="qy-intro-word" aria-label="Qylot">
          {"Qylot".split("").map((letter, i) => (
            <span key={`${letter}-${i}`} style={{ animationDelay: `${0.42 + i * 0.055}s` }}>{letter}</span>
          ))}
        </div>
        <div className="qy-intro-caption">Vos ventes. Vos chantiers. Votre équipe.</div>
        <div className="qy-intro-line"><span /></div>
        <div className="qy-intro-meta">CHANTIERS &amp; CROISSANCE</div>
      </div>
    </div>
  );
}
