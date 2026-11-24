import React from "react";

/** Décompte des 14 jours d'une vente en attente de programmation.
 *  Affiché uniquement tant que la vente est encore « En attente prog ».
 */
export default function Sale14DaysBadge({ sale, mobile = false }) {
  if (sale?.desired_intervention_date !== "attente_14j" || sale?.status !== "attente_prog") return null;
  try {
    const start = new Date(sale.sale_date + "T00:00:00");
    if (Number.isNaN(start.getTime())) return null;
    const days = 14 - Math.floor((new Date() - start) / 86400000);
    const suffix = mobile ? "mobile-" : "";
    if (days > 0) {
      const urgent = days <= 3;
      return (
        <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${urgent ? "bg-amber-200 text-amber-900 ring-1 ring-amber-400" : "bg-amber-100 text-amber-800"}`} data-testid={`sale-${suffix}14j-countdown-${sale.id}`}>
          {days === 1 ? "Il reste 1 j" : `Il reste ${days} j`}
        </span>
      );
    }
    if (days === 0) {
      return <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-500 animate-pulse ring-1 ring-red-600" data-testid={`sale-${suffix}14j-jourj-${sale.id}`}>Jour J</span>;
    }
    return <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-600 animate-pulse ring-1 ring-red-700" data-testid={`sale-${suffix}14j-overdue-${sale.id}`}>Délai dépassé +{Math.abs(days)} j</span>;
  } catch (_) { return null; }
}
