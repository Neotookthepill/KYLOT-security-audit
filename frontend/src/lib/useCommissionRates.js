import { useEffect, useState } from "react";
import api from "@/lib/api";
import { COMMISSION_RATES as DEFAULT_RATES } from "@/lib/saleConstants";

// Simple in-memory cache so the sheets don't re-fetch on every open
let _cache = null;
let _cacheTs = 0;

export default function useCommissionRates() {
  const [rates, setRates] = useState(_cache || DEFAULT_RATES);

  useEffect(() => {
    // Refresh if cache older than 60s (or empty)
    if (_cache && Date.now() - _cacheTs < 60_000) return;
    api.get("/settings").then((r) => {
      const list = Array.isArray(r.data?.commission_rates) ? r.data.commission_rates : null;
      if (list && list.length) {
        _cache = list;
        _cacheTs = Date.now();
        setRates(list);
      }
    }).catch(() => {});
  }, []);

  return rates;
}

export const invalidateCommissionRatesCache = () => { _cache = null; _cacheTs = 0; };
