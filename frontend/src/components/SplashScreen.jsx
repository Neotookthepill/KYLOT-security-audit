import React, { useEffect, useState } from "react";

/**
 * QYLOT launch splash — shown once when the app truly boots (fresh page load).
 * Desktop ≈ 1.25s. Mobile is slower and smoother (≈ 1.9s) so the intro
 * doesn't feel rushed on small screens.
 */
export default function SplashScreen({ onDone }) {
  const [phase, setPhase] = useState("in"); // in → hold → out → done

  useEffect(() => {
    const isMobile = typeof window !== "undefined" && window.innerWidth <= 640;
    const timings = isMobile
      ? { hold: 900, out: 1500, done: 2000 }   // slower, more premium on phones
      : { hold: 500, out: 900,  done: 1250 };  // desktop unchanged

    const t1 = setTimeout(() => setPhase("hold"), timings.hold);
    const t2 = setTimeout(() => setPhase("out"),  timings.out);
    const t3 = setTimeout(() => { setPhase("done"); onDone?.(); }, timings.done);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [onDone]);

  if (phase === "done") return null;

  return (
    <div
      className={`kylot-splash ${phase === "out" ? "kylot-splash--out" : ""}`}
      data-testid="qylot-splash"
      aria-hidden="true"
    >
      <div className="kylot-splash__glow" />
      <div className="kylot-splash__logo">
        <svg viewBox="0 0 512 512" width="140" height="140" className="kylot-splash__svg">
          {/* iter184 — Logo QYLOT officiel : anneau argenté brossé + accent diagonal métallique */}
          <defs>
            <linearGradient id="qy-ring" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#F8FAFC" />
              <stop offset="55%" stopColor="#CBD5E1" />
              <stop offset="100%" stopColor="#64748B" />
            </linearGradient>
            <linearGradient id="qy-tail" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#94A3B8" />
              <stop offset="60%" stopColor="#475569" />
              <stop offset="100%" stopColor="#1E293B" />
            </linearGradient>
          </defs>
          {/* Anneau du Q */}
          <circle cx="256" cy="256" r="150" fill="none" stroke="url(#qy-ring)" strokeWidth="30" className="kylot-splash__k" />
          {/* Queue diagonale (arrête plate, traverse le Q vers l'extérieur) */}
          <line x1="280" y1="280" x2="436" y2="436" stroke="url(#qy-tail)" strokeWidth="36" strokeLinecap="butt" className="kylot-splash__accent" />
        </svg>
        <div className="kylot-splash__wordmark">QYLOT</div>
      </div>
    </div>
  );
}
