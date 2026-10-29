import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { MapPin, Phone, Loader2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";

const HEX = { indigo: "#4f46e5", sky: "#0ea5e9", orange: "#f97316", red: "#dc2626", emerald: "#10b981", slate: "#64748b", yellow: "#eab308", violet: "#8b5cf6" };
const hexFor = (color) => HEX[color] || HEX.slate;

function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) map.fitBounds(points.map((p) => [p.geo_lat, p.geo_lng]), { padding: [40, 40], maxZoom: 12 });
  }, [points.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], 12, { duration: 1.2 });
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function CitySearch({ onFound }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q.trim())}&type=municipality&limit=1`);
      const f = ((await r.json()).features || [])[0];
      if (!f) { toast.error("Ville introuvable"); return; }
      const [lng, lat] = f.geometry.coordinates;
      onFound({ lat, lng, label: f.properties.city || f.properties.label });
    } catch { toast.error("Recherche impossible"); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={go} className="relative w-full sm:w-72" data-testid="map-city-search-form">
      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Aller à une ville…" className="pl-9 pr-9" data-testid="map-city-search-input" />
      {busy && <Loader2 size={15} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-slate-400" />}
    </form>
  );
}

function ClientPopup({ c, catByKey, onOpen }) {
  return (
    <div className="min-w-[200px]" data-testid={`map-popup-${c.id}`}>
      <p className="font-semibold text-sm text-slate-900">{c.name}</p>
      <p className="text-xs text-slate-600 mt-1 flex gap-1"><MapPin size={12} className="mt-0.5 shrink-0" />{[c.address, c.postal_code, c.city].filter(Boolean).join(", ")}</p>
      {c.phone && <a href={`tel:${c.phone}`} className="text-xs text-slate-600 mt-1 flex gap-1 items-center"><Phone size={12} />{c.phone}</a>}
      <div className="flex flex-wrap gap-1 mt-2">
        {(c.categories || []).map((cc) => {
          const cat = catByKey[cc.category_key];
          if (!cat) return null;
          const sub = (cat.sub_statuses || []).find((s) => s.key === cc.sub_status_key);
          return <span key={cc.category_key} className="text-[10px] font-medium px-1.5 py-0.5 rounded text-white" style={{ background: hexFor(cat.color) }}>{cat.label}{sub ? ` · ${sub.label}` : ""}</span>;
        })}
      </div>
      <button type="button" onClick={() => onOpen(c.id)} className="mt-2 w-full text-xs font-medium rounded-md bg-slate-900 text-white py-1.5 hover:bg-slate-700 transition-colors" data-testid={`map-open-client-${c.id}`}>Ouvrir la fiche client</button>
    </div>
  );
}

export default function MapPage() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [categories, setCategories] = useState([]);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState("all");
  const [target, setTarget] = useState(null);

  const load = async () => {
    try {
      const [m, cats] = await Promise.all([api.get("/clients/map"), api.get("/client-categories").catch(() => ({ data: [] }))]);
      setClients(m.data.clients || []);
      setPending(m.data.pending || 0);
      setCategories(cats.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!pending) return undefined;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [pending, clients.length]);

  const catByKey = useMemo(() => Object.fromEntries(categories.map((c) => [c.key, c])), [categories]);
  const located = clients.filter((c) => c.geo_lat != null && c.geo_lng != null);
  const visible = located.filter((c) => active === "all" || (c.categories || []).some((cc) => cc.category_key === active));
  const colorOf = (c) => {
    const list = c.categories || [];
    const pick = (active !== "all" && list.find((cc) => cc.category_key === active)) || list[0];
    return pick && catByKey[pick.category_key] ? hexFor(catByKey[pick.category_key].color) : "#94a3b8";
  };
  const countFor = (key) => located.filter((c) => (c.categories || []).some((cc) => cc.category_key === key)).length;

  return (
    <div className="p-4 md:p-8 max-w-[1600px] space-y-4" data-testid="map-page">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
        <div>
          <p className="overline">Clients</p>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Carte</h1>
            <CitySearch onFound={setTarget} />
          </div>
        </div>
        <p className="text-sm text-slate-500" data-testid="map-count">
          {located.length} client{located.length > 1 ? "s" : ""} localisé{located.length > 1 ? "s" : ""} sur {clients.length}
          {pending > 0 && <span className="ml-2 inline-flex items-center gap-1 text-amber-700"><Loader2 size={13} className="animate-spin" /> {pending} en cours de localisation…</span>}
        </p>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="map-legend">
        <button type="button" onClick={() => setActive("all")} data-testid="map-filter-all"
          className={`h-8 px-3 rounded-full text-xs font-medium border transition-colors ${active === "all" ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}>
          Tous ({located.length})
        </button>
        {categories.map((c) => (
          <button key={c.key} type="button" onClick={() => setActive(c.key)} data-testid={`map-filter-${c.key}`}
            className={`h-8 px-3 rounded-full text-xs font-medium border inline-flex items-center gap-1.5 transition-colors ${active === c.key ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: hexFor(c.color) }} />
            {c.label} ({countFor(c.key)})
          </button>
        ))}
      </div>

      <div className="rounded-xl overflow-hidden border border-slate-200 shadow-sm h-[calc(100vh-260px)] min-h-[420px] relative z-0" data-testid="map-container">
        {loading ? (
          <div className="h-full grid place-items-center text-slate-500"><Loader2 className="animate-spin" /></div>
        ) : (
          <MapContainer center={[46.6, 2.4]} zoom={6} scrollWheelZoom className="h-full w-full">
            <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <FitBounds points={located} />
            <FlyTo target={target} />
            {visible.map((c) => (
              <CircleMarker key={c.id} center={[c.geo_lat, c.geo_lng]} radius={8}
                pathOptions={{ color: "#fff", weight: 2, fillColor: colorOf(c), fillOpacity: 0.95 }}>
                <Popup><ClientPopup c={c} catByKey={catByKey} onOpen={(id) => navigate(`/clients?open=${id}`)} /></Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        )}
      </div>
    </div>
  );
}
