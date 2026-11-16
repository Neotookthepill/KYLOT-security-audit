import React from "react";

export default function PageLoader({ label = "Chargement…", compact = false, testId = "page-loader" }) {
  return (
    <div className={`qy-page-loader ${compact ? "is-compact" : ""}`} role="status" aria-live="polite" data-testid={testId}>
      <div className="qy-page-loader-mark" aria-hidden="true">
        <img src="/brand/qylot-logo-nuit-azur.png" alt="" />
      </div>
      <div className="qy-page-loader-text">{label}</div>
      <div className="qy-page-loader-dots" aria-hidden="true"><span /><span /><span /></div>
    </div>
  );
}
