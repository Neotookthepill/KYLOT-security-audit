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
        <div className="grid h-[104px] w-[104px] place-items-center rounded-[26px] border border-white/10 bg-[#0b1220] shadow-2xl">
          <span className="font-display text-[58px] font-bold leading-none tracking-[-.06em] text-[#f7f3e9]">Q</span>
        </div>
        <div className="kylot-splash__wordmark">Qylot</div>
      </div>
    </div>
  );
}
