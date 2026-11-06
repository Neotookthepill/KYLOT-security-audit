import React, { useEffect, useState } from "react";

/**
 * Qylot launch splash — shown once when the app truly boots (fresh page load).
 * Desktop ≈ 1.25s. Mobile is slower and smoother (≈ 1.9s) so the intro
 * doesn't feel rushed on small screens.
 */
export default function SplashScreen({ onDone }) {
  const [phase, setPhase] = useState("in"); // in → hold → out → done

  useEffect(() => {
    const isMobile = typeof window !== "undefined" && window.innerWidth <= 640;
    const timings = isMobile
      ? { hold: 140, out: 340, done: 430 }
      : { hold: 120, out: 280, done: 360 };

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
        <div className="h-[104px] w-[104px] overflow-hidden rounded-[26px] border border-white/10 bg-[#0b1220] shadow-2xl">
          <img src="/brand/qylot-mark-light.svg?v=2" alt="Qylot" className="h-full w-full object-contain" />
        </div>
        <div className="kylot-splash__wordmark">Qylot</div>
      </div>
    </div>
  );
}
