import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Phone, MapPin, Camera, X, Loader2, MapPin as MapPinIcon, Image as ImageIcon, UserCircle, Users2, CheckCheck, ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut, RotateCcw, Plus } from "lucide-react";
import { toast } from "sonner";
import useTeam from "@/lib/useTeam";
import { useAuth } from "@/contexts/AuthContext";
import TechNotesSection from "@/components/TechNotesSection";

function fileToBase64(file, maxW = 1600) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new window.Image();
      img.onload = () => {
        const scale = Math.min(1, maxW / img.width);
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.8));
      };
      img.onerror = reject;
      img.src = e.target.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function getCurrentPosition(timeout = 8000) {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout, maximumAge: 60000 },
    );
  });
}

// A photo entry may be a legacy string (base64) or a rich object { src, lat, lng, taken_at, added_by, added_by_id, created_at }
const safeImageSrc = (value) => {
  if (typeof value !== "string") return "";
  return /^(?:https:\/\/|data:image\/(?:jpeg|jpg|png|webp);base64,)/i.test(value) ? value : "";
};
const photoSrc = (p) => safeImageSrc(typeof p === "string" ? p : p?.src);
const photoGps = (p) => (typeof p === "object" && p?.lat != null ? { lat: p.lat, lng: p.lng } : null);
const photoTakenAt = (p) => (typeof p === "object" ? p?.taken_at : null);
const photoAddedBy = (p) => (typeof p === "object" ? p?.added_by : null);
const photoCreatedAt = (p) => (typeof p === "object" ? (p?.created_at || p?.taken_at) : null);
const fmtDateTime = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (_) { return ""; }
};

// Normalize assigned_to (may be string, array, or nested array in legacy data)
const toList = (v) => {
  if (Array.isArray(v)) {
    // Flatten one level (defends against nested [[...]])
    const flat = v.flat(Infinity);
    return flat.filter((n) => typeof n === "string" && n.trim() !== "");
  }
  return v && typeof v === "string" ? [v] : [];
};

export default function ProjectDialog({ project, onClose, onSaved, contextDate = null }) {
  const { techniciens, sousTraitants } = useTeam();
  const { user, can } = useAuth();
  const role = user?.role;
  const isTech = role === "technicien" || role === "sous_traitant";
  // iter140 : liste combinée pour l'assignation (techniciens + sous-traitants), dédupliquée par nom.
  const assignables = React.useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const t of techniciens) {
      const k = (t.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...t, _kind: "technicien" }); }
    }
    for (const s of sousTraitants) {
      const k = (s.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...s, _kind: "sous_traitant" }); }
    }
    return out;
  }, [techniciens, sousTraitants]);
  const canEditPlan = role === "admin" || role === "responsable" || role === "super_admin";
  const canAddPhotos = can("photos", "add");
  const canViewPhotos = can("photos", "view");
  const [form, setForm] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [completeNote, setCompleteNote] = useState("");
  const [completeDay, setCompleteDay] = useState(null);
  const [completing, setCompleting] = useState(false);
  // iter153 : lightbox photo — index de la photo affichée en grand, ou null pour fermer.
  const [lightboxIndex, setLightboxIndex] = useState(null);
  // iter201 : état de zoom du lightbox (échelle + translation)
  const [zoomScale, setZoomScale] = useState(1);
  const [zoomTx, setZoomTx] = useState(0);
  const [zoomTy, setZoomTy] = useState(0);
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);
  // iter206b : refs pour pinch/drag mobile du lightbox photo — DÉCLARÉS au niveau
  // du composant (les hooks ne peuvent pas vivre dans le callback de createPortal
  // — ESLint react-hooks/rules-of-hooks bloque le build sinon).
  const pinchStateRef = useRef({ startDist: 0, startScale: 1 });
  const dragStateRef = useRef({ dragging: false, x0: 0, y0: 0, sx: 0, sy: 0 });

  // iter153 : Escape ferme, ← / → navigue entre photos
  useEffect(() => {
    if (lightboxIndex === null) return;
    const onKey = (e) => {
      const total = (form?.photos || []).length;
      if (e.key === "Escape") setLightboxIndex(null);
      else if (e.key === "ArrowRight") setLightboxIndex((i) => (i === null ? null : (i + 1) % total));
      else if (e.key === "ArrowLeft") setLightboxIndex((i) => (i === null ? null : (i - 1 + total) % total));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightboxIndex, form?.photos]);

  useEffect(() => {
    if (!project) { setForm(null); return; }
    // iter220 — payload léger reçu de la liste : on hydrate immédiatement l'UI
    // avec ce qu'on a (métadonnées + statut) puis on recharge en arrière-plan la
    // fiche complète (photos pleines) via GET /projects/{id}. L'UX s'affiche
    // instantanément et les photos arrivent dès qu'elles sont prêtes.
    setForm({ ...project, photos: project.photos || [], assigned_to: toList(project.assigned_to), day_exclusions: project.day_exclusions || {}, extra_dates: Array.isArray(project.extra_dates) ? [...project.extra_dates] : [] });
    (async () => {
      try {
        const full = (await api.get(`/projects/${project.id}`)).data;
        if (full && full.id === project.id) {
          setForm((prev) => prev && prev.id === project.id ? { ...prev, ...full, photos: full.photos || [], assigned_to: toList(full.assigned_to), day_exclusions: full.day_exclusions || prev.day_exclusions || {}, extra_dates: Array.isArray(full.extra_dates) ? [...full.extra_dates] : (prev.extra_dates || []) } : prev);
        }
      } catch (_) { /* keep slim payload if full fetch fails */ }
    })();
  }, [project]);

  // iter211 : dialogue « retirer ce jour / tout le chantier » quand on décoche
  // un technicien sur un chantier multi-jours ouvert depuis une case précise.
  const [removeChoiceOpen, setRemoveChoiceOpen] = useState(null); // { name } | null
  // iter213 : jours supplémentaires non consécutifs — hook DÉCLARÉ AVANT
  // l'early return `if (!project || !form) return null;` pour respecter
  // `react-hooks/rules-of-hooks`.
  const [newExtraDate, setNewExtraDate] = useState("");

  // Hooks MUST be called before any early return — compute derived data safely with fallbacks.
  const assignedList = toList(form?.assigned_to);
  const withYouOthers = React.useMemo(() => {
    // iter206 : match accent-insensible + tokens partagés — cohérent avec _matchAssigned
    const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    const toks = (s) => norm(s).split(/[\s_\-.]+/).filter(Boolean);
    const meN = norm(user?.name || "");
    const meT = new Set(toks(user?.name || ""));
    const isMe = (n) => {
      const nN = norm(n);
      if (!meN || !nN) return false;
      if (meN === nN) return true;
      const t = new Set(toks(n));
      for (const x of meT) if (t.has(x)) return true;
      return false;
    };
    return assignedList.filter((n) => !isMe(n));
  }, [assignedList, user]);

  if (!project || !form) return null;

  const projectDays = (() => {
    const keys = [];
    if (form.scheduled_date && /^\d{4}-\d{2}-\d{2}$/.test(form.scheduled_date)) {
      const start = new Date(form.scheduled_date + "T00:00:00");
      for (let i = 0; i < Math.max(1, Number(form.duration_days) || 1); i++) {
        const d = new Date(start);
        d.setDate(d.getDate() + i);
        keys.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
      }
    }
    for (const k of (form.extra_dates || [])) if (/^\d{4}-\d{2}-\d{2}$/.test(k) && !keys.includes(k)) keys.push(k);
    return keys.sort();
  })();
  const fmtDay = (k) => new Date(k + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "2-digit", month: "long" });

  const toggleTech = (name) => {
    const list = toList(form.assigned_to);
    const excl = form.day_exclusions || {};
    const excludedToday = contextDate ? (excl[contextDate] || []).includes(name) : false;
    const isAssigned = list.includes(name);
    // Cas 1 : la personne est actuellement invisible ce jour (exclusion) → on la restaure ce jour
    if (contextDate && excludedToday) {
      const nextExcl = { ...excl, [contextDate]: (excl[contextDate] || []).filter((n) => n !== name) };
      if (!nextExcl[contextDate].length) delete nextExcl[contextDate];
      setForm({ ...form, day_exclusions: nextExcl, assigned_to: isAssigned ? list : [...list, name] });
      return;
    }
    // Cas 2 : ajout → toujours cocher globalement
    if (!isAssigned) {
      setForm({ ...form, assigned_to: [...list, name] });
      return;
    }
    // Cas 3 : retrait — chantier sur plusieurs jours (consécutifs ou non) → on demande systématiquement le périmètre
    if (projectDays.length > 1) {
      setRemoveChoiceOpen({ name, day: projectDays.includes(contextDate) ? contextDate : projectDays[0] });
      return;
    }
    // Sinon retrait global direct
    setForm({ ...form, assigned_to: list.filter((n) => n !== name) });
  };

  const removeForWholeProject = () => {
    if (!removeChoiceOpen) return;
    const name = removeChoiceOpen.name;
    const list = toList(form.assigned_to).filter((n) => n !== name);
    // Nettoie aussi les exclusions résiduelles de ce nom
    const cleaned = {};
    for (const [d, arr] of Object.entries(form.day_exclusions || {})) {
      const kept = (arr || []).filter((n) => n !== name);
      if (kept.length) cleaned[d] = kept;
    }
    setForm({ ...form, assigned_to: list, day_exclusions: cleaned });
    setRemoveChoiceOpen(null);
  };
  const removeForThisDayOnly = () => {
    if (!removeChoiceOpen?.day) return;
    const { name, day } = removeChoiceOpen;
    const excl = { ...(form.day_exclusions || {}) };
    const cur = new Set(excl[day] || []);
    cur.add(name);
    excl[day] = Array.from(cur);
    setForm({ ...form, day_exclusions: excl });
    setRemoveChoiceOpen(null);
  };

  const save = async () => {
    try {
      await api.put(`/projects/${project.id}`, {
        status: form.status,
        priority: form.priority,
        scheduled_date: form.scheduled_date || null,
        assigned_to: toList(form.assigned_to),
        duration_days: Number(form.duration_days) || 1,
        notes: form.notes,
        photos: form.photos,
        day_exclusions: form.day_exclusions || {},
        extra_dates: Array.isArray(form.extra_dates) ? form.extra_dates.filter(Boolean) : [],
      });
      toast.success("Chantier mis à jour");
      // iter216 : broadcast Kanban ↔ Planning sync
      try { window.dispatchEvent(new CustomEvent("kylot:project-updated", { detail: { id: project.id, status: form.status } })); } catch (_) {}
      onSaved?.();
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter213 : gestion des jours supplémentaires (non consécutifs).
  // Le `useState` correspondant est déclaré plus haut, AVANT l'early return.
  const addExtraDate = () => {
    if (!newExtraDate || !/^\d{4}-\d{2}-\d{2}$/.test(newExtraDate)) return;
    // Refuse si la date est déjà dans la plage consécutive ou déjà présente
    const base = form.scheduled_date || "";
    const dur = Math.max(1, Number(form.duration_days) || 1);
    if (base) {
      const start = new Date(base + "T00:00:00");
      for (let i = 0; i < dur; i++) {
        const d = new Date(start); d.setDate(d.getDate() + i);
        const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        if (k === newExtraDate) { toast.error("Ce jour est déjà couvert par la durée du chantier."); return; }
      }
    }
    const cur = Array.isArray(form.extra_dates) ? form.extra_dates : [];
    if (cur.includes(newExtraDate)) { toast.error("Ce jour est déjà ajouté."); return; }
    setForm({ ...form, extra_dates: [...cur, newExtraDate].sort() });
    setNewExtraDate("");
  };
  const removeExtraDate = (d) => {
    const cur = Array.isArray(form.extra_dates) ? form.extra_dates : [];
    setForm({ ...form, extra_dates: cur.filter((x) => x !== d) });
  };

  const addPhotos = async (files) => {
    if (!canAddPhotos) {
      toast.error("Vous n'avez pas la permission d'ajouter des photos.");
      return;
    }
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const arr = Array.from(files).slice(0, 10);
      const gps = await getCurrentPosition();
      const b64s = await Promise.all(arr.map((f) => fileToBase64(f)));
      const takenAt = new Date().toISOString();
      const rich = b64s.map((src) => ({
        src,
        taken_at: takenAt,
        added_by: user?.name || user?.email || "?",
        added_by_id: user?.id,
        created_at: takenAt,
        ...(gps ? { lat: gps.lat, lng: gps.lng, accuracy: gps.accuracy } : {}),
      }));
      const next = [...(form.photos || []), ...rich];
      setForm({ ...form, photos: next });
      await api.put(`/projects/${project.id}`, { photos: next });
      toast.success(`${rich.length} photo(s) ajoutée(s)${gps ? " · position enregistrée" : ""}`);
    } catch (err) { toast.error(formatApiError(err) || "Erreur upload"); }
    finally {
      setUploading(false);
      if (cameraRef.current) cameraRef.current.value = "";
      if (galleryRef.current) galleryRef.current.value = "";
    }
  };

  const removePhoto = async (idx) => {
    if (!canAddPhotos) {
      toast.error("Vous n'avez pas la permission de modifier les photos.");
      return;
    }
    const next = form.photos.filter((_, i) => i !== idx);
    setForm({ ...form, photos: next });
    try { await api.put(`/projects/${project.id}`, { photos: next }); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  // Chantier terminé workflow (iter37) — plain consts (no hook after early return)
  // iter206 : matching accent-insensible (Sébastien vs sebastien) + tokens partagés
  // (Sébastien Martin vs Sébastien) pour que le bouton apparaisse bien côté technicien.
  const _norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const _toks = (s) => _norm(s).split(/[\s_\-.]+/).filter(Boolean);
  const _matchAssigned = (me, target) => {
    const a = _norm(me), b = _norm(target);
    if (!a || !b) return false;
    if (a === b) return true;
    const ta = new Set(_toks(me)), tb = new Set(_toks(target));
    for (const t of ta) if (tb.has(t)) return true;
    return false;
  };
  const isAssignedTech = !!user?.name && assignedList.some((n) => _matchAssigned(user.name, n));
  const canCompleteChantier = (isTech && isAssignedTech) || canEditPlan;
  // iter217 : admin/responsable/super_admin peuvent DÉCLENCHER « Chantier terminé »
  // systématiquement, même si le chantier est déjà en `termine` (renotification aux
  // commerciaux). Seul `encaisse` (argent récupéré, cycle clos) masque le bouton.
  // iter218 : idem si la vente liée est `argent_recupere` → cycle clos, on masque aussi.
  const isAdminLike = ["admin", "responsable", "super_admin"].includes(user?.role);
  const saleClosed = form.sale_status === "argent_recupere";
  const alreadyDone = isAdminLike
    ? (form.status === "encaisse" || saleClosed)
    : (form.status === "termine" || form.status === "encaisse" || saleClosed);
  const completeBtnLabel = form.status === "termine" ? "Renotifier commercial" : (projectDays.length > 1 ? "Valider une journée" : "Chantier terminé");
  const todayIso = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; })();
  const daysDone = form.days_done || project.days_done || {};
  const doneCount = projectDays.filter((d) => daysDone[d]).length;
  const defaultCompleteDay = (() => {
    if (projectDays.length <= 1) return null;
    if (contextDate && projectDays.includes(contextDate) && !daysDone[contextDate] && contextDate <= todayIso) return contextDate;
    const past = projectDays.filter((d) => !daysDone[d] && d <= todayIso);
    return past.length ? past[past.length - 1] : null;
  })();
  const chosenDay = completeDay || defaultCompleteDay;

  const completeChantier = async () => {
    const photos = form.photos || [];
    if (photos.length === 0) {
      toast.error("Ajoutez au moins une photo du chantier terminé avant de valider.");
      return;
    }
    if (projectDays.length > 1 && form.status !== "termine" && !chosenDay) {
      toast.error("Choisissez la journée d'intervention à valider.");
      return;
    }
    setCompleting(true);
    try {
      const r = await api.post(`/projects/${project.id}/complete`, {
        photos: photos.map((p) => (typeof p === "string" ? p : p.src)).filter(Boolean).slice(-5),
        note: completeNote.trim(),
        ...(projectDays.length > 1 && chosenDay ? { day: chosenDay } : {}),
      });
      if (r.data?.partial) {
        toast.success(`Journée du ${new Date(r.data.day + "T00:00:00").toLocaleDateString("fr-FR")} validée — ${r.data.remaining.length} intervention(s) restante(s). Le chantier reste en cours.`);
        try { window.dispatchEvent(new CustomEvent("kylot:project-updated", { detail: { id: project.id } })); } catch (_) {}
        setCompleteOpen(false);
        setCompleteNote("");
        setCompleteDay(null);
        onSaved?.();
        onClose();
        return;
      }
      toast.success(r.data?.notified > 0
        ? `Chantier validé. ${r.data.notified} commercial(aux) notifié(s).`
        : "Chantier validé.");
      // iter216 : broadcast Kanban ↔ Planning sync (statut passe à `termine`)
      try { window.dispatchEvent(new CustomEvent("kylot:project-updated", { detail: { id: project.id, status: "termine" } })); } catch (_) {}
      setCompleteOpen(false);
      setCompleteNote("");
      onSaved?.();
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setCompleting(false); }
  };

  const teamNames = new Set(assignables.map((t) => (t.name || "").toLowerCase()));
  const orphanAssignees = assignedList.filter((n) => !teamNames.has((n || "").toLowerCase()));

  const removeOrphan = (name) => {
    const next = assignedList.filter((n) => n !== name);
    setForm({ ...form, assigned_to: next });
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="project-dialog">
        <DialogHeader>
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <DialogTitle className="font-display text-2xl">{project.client_name}</DialogTitle>
              <p className="text-sm text-slate-500">{project.service}</p>
            </div>
            {/* iter159 v3 : la pastille "Confirmé" est visible pour TOUS les rôles qui accèdent
                à la fiche (technicien, sous-traitant, commercial, admin). Seuls admin/responsable/
                commercial peuvent CLIQUER pour basculer l'état ; les tech/sous-traitants voient
                un badge en lecture seule (identique visuel). */}
            {(() => {
              const canToggleConfirm = user?.role !== "technicien" && user?.role !== "sous_traitant";
              // Si le chantier n'est pas confirmé ET que le rôle ne peut pas confirmer, rien à afficher
              if (!form.confirmed && !canToggleConfirm) return null;
              const common = `shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-semibold border transition ${form.confirmed ? "bg-emerald-600 text-white border-emerald-600" : "bg-white text-slate-700 border-slate-300"}`;
              const title = form.confirmed ? `Confirmé${form.confirmed_by ? " par " + form.confirmed_by : ""}` : "Confirmer le chantier";
              if (!canToggleConfirm) {
                return (
                  <span className={common} data-testid="project-confirm-badge" title={title}>
                    <CheckCheck size={13} /> Confirmé
                  </span>
                );
              }
              return (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const { data } = await api.post(`/projects/${project.id}/confirm`);
                      setForm((f) => ({ ...f, confirmed: data.confirmed, confirmed_at: data.confirmed_at, confirmed_by: data.confirmed_by }));
                      toast.success(data.confirmed ? "Chantier confirmé" : "Confirmation retirée");
                      onSaved?.();
                    } catch (err) { toast.error(formatApiError(err)); }
                  }}
                  className={`${common} ${form.confirmed ? "hover:bg-emerald-700" : "hover:border-emerald-500 hover:text-emerald-700"}`}
                  data-testid="project-confirm-btn"
                  title={title}
                >
                  <CheckCheck size={13} />
                  {form.confirmed ? "Confirmé" : "Confirmer"}
                </button>
              );
            })()}
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-500 pt-2">
            {project.client_phone && <span className="flex items-center gap-1"><Phone size={11}/> {project.client_phone}</span>}
            {project.client_address && <span className="flex items-center gap-1"><MapPin size={11}/> {project.client_address} {project.client_postal_code} {project.client_city}</span>}
          </div>
          {/* Commercial(s) : always visible (comes from the sale) */}
          {(project.commercial || project.commercial_2) && (
            <div className="flex flex-wrap items-center gap-2 pt-2" data-testid="project-commercial">
              <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-500"><UserCircle size={12} /> {project.is_de ? "Commerciaux" : "Commercial"}</span>
              {project.commercial && (
                <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-800 text-xs px-2 py-0.5 font-medium">{project.commercial}</span>
              )}
              {project.is_de && project.commercial_2 && (
                <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-800 text-xs px-2 py-0.5 font-medium">{project.commercial_2}</span>
              )}
            </div>
          )}
          {/* "Avec vous sur ce chantier" — only when >= 2 people involved */}
          {assignedList.length > 1 && withYouOthers.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-2" data-testid="project-with-you">
              <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wider text-indigo-700"><Users2 size={12} /> {isTech ? "Avec vous sur ce chantier" : "Équipe sur ce chantier"}</span>
              {withYouOthers.map((n) => (
                <span key={n} className="inline-flex items-center rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200 text-xs px-2 py-0.5 font-medium" data-testid={`project-with-badge-${n}`}>
                  {n}
                </span>
              ))}
            </div>
          )}
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Statut</Label>
            <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
              <SelectTrigger data-testid="project-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="a_planifier">À planifier</SelectItem>
                <SelectItem value="en_cours">PROG</SelectItem>
                <SelectItem value="termine">À encaisser</SelectItem>
                <SelectItem value="encaisse">Terminé</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="min-w-0">
              <Label>Date de début</Label>
              <Input type="date" value={form.scheduled_date || ""} onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })} data-testid="project-scheduled-date" className="w-full" />
            </div>
            <div className="min-w-0">
              <Label>Durée (jours consécutifs)</Label>
              <Input type="number" min={1} value={form.duration_days || 1} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} data-testid="project-duration" />
              <p className="text-[11px] text-slate-500 mt-1">Nombre de jours d'affilée à partir de la date de début.</p>
            </div>
          </div>
          {/* iter213 : jours supplémentaires non consécutifs (pause dans le chantier) */}
          {canEditPlan && (
            <div className="rounded-md border border-slate-200 p-3 bg-slate-50/40" data-testid="project-extra-dates">
              <Label className="text-sm">Jours supplémentaires (non consécutifs)</Label>
              <p className="text-[11px] text-slate-500 mt-0.5 mb-2">Ajoutez ici les jours isolés qui font partie du chantier mais qui ne se suivent pas (ex : chantier lundi + mercredi + vendredi).</p>
              <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                <Input type="date" value={newExtraDate} onChange={(e) => setNewExtraDate(e.target.value)} data-testid="project-extra-date-input" className="w-full sm:max-w-[200px]" />
                <Button type="button" onClick={addExtraDate} disabled={!newExtraDate} size="sm" data-testid="project-extra-date-add" className="bg-slate-900 hover:bg-slate-800 text-white h-10 sm:h-9">
                  <Plus size={13} className="mr-1" /> Ajouter
                </Button>
              </div>
              {Array.isArray(form.extra_dates) && form.extra_dates.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {form.extra_dates.map((d) => (
                    <span key={d} className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-300 text-slate-800 text-xs px-2 py-1" data-testid={`project-extra-date-chip-${d}`}>
                      {new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "2-digit", month: "short" })}
                      <button type="button" onClick={() => removeExtraDate(d)} className="text-slate-400 hover:text-red-600" aria-label={`Retirer ${d}`} data-testid={`project-extra-date-remove-${d}`}>
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <div>
            <Label>Techniciens & sous-traitants assignés {assignedList.length > 0 && <span className="text-xs text-slate-500 ml-1">({assignedList.length} sélectionné{assignedList.length > 1 ? "s" : ""})</span>}</Label>
            {orphanAssignees.length > 0 && canEditPlan && (
              <div className="mt-1.5 mb-1.5 p-2 rounded-md bg-amber-50 border border-amber-200 flex flex-wrap gap-1.5" data-testid="project-tech-orphans">
                <span className="text-[11px] text-amber-800 font-medium mr-1">Anciens techniciens :</span>
                {orphanAssignees.map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => removeOrphan(n)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-amber-300 text-amber-900 text-xs hover:bg-amber-100"
                    title="Cliquer pour retirer"
                    data-testid={`project-tech-orphan-remove-${n}`}
                  >
                    {n}
                    <X size={11} />
                  </button>
                ))}
              </div>
            )}
            {canEditPlan ? (
              <div className="mt-1.5 border border-slate-200 rounded-md p-3 max-h-56 overflow-y-auto space-y-1.5">
                {assignables.length === 0 && <p className="text-xs text-slate-500 italic">Aucun technicien / sous-traitant. Ajoutez-en dans Utilisateurs → Équipe.</p>}
                {assignables.map((t) => {
                  const isAssigned = assignedList.includes(t.name);
                  const excludedToday = contextDate && ((form.day_exclusions || {})[contextDate] || []).includes(t.name);
                  const effectivelyChecked = isAssigned && !excludedToday;
                  return (
                    <label key={t.id} className="flex items-center gap-2.5 cursor-pointer hover:bg-slate-50 rounded px-2 py-1" data-testid={`project-tech-${t.id}`}>
                      <Checkbox checked={effectivelyChecked} onCheckedChange={() => toggleTech(t.name)} data-testid={`project-tech-checkbox-${t.id}`} />
                      <span className={`text-sm ${excludedToday ? "line-through text-slate-400" : ""}`}>{t.name}</span>
                      {excludedToday && contextDate && (
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5" title={`Retiré uniquement le ${contextDate}`}>Retiré ce jour</span>
                      )}
                      {isAssigned && Object.entries(form.day_exclusions || {}).filter(([d, arr]) => d !== contextDate && (arr || []).includes(t.name)).map(([d]) => (
                        <button key={d} type="button" title="Cliquer pour le remettre ce jour-là" data-testid={`project-tech-excl-${t.id}-${d}`}
                          onClick={(e) => { e.preventDefault(); const nx = { ...form.day_exclusions, [d]: form.day_exclusions[d].filter((n) => n !== t.name) }; if (!nx[d].length) delete nx[d]; setForm({ ...form, day_exclusions: nx }); }}
                          className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 hover:bg-amber-100">
                          Retiré le {new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })} <X size={10} />
                        </button>
                      ))}
                      {t._kind === "sous_traitant" && (
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-700 bg-violet-50 border border-violet-200 rounded px-1.5 py-0.5">S/T</span>
                      )}
                    </label>
                  );
                })}
              </div>
            ) : (
              <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="project-tech-readonly">
                {assignedList.length === 0 && <p className="text-xs text-slate-500 italic">Aucun technicien assigné.</p>}
                {assignedList.map((n) => (
                  <span key={n} className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5">{n}</span>
                ))}
              </div>
            )}
            {canEditPlan && <p className="text-[11px] text-slate-500 mt-1">Cochez plusieurs personnes pour une double intervention. Les sous-traitants (S/T) sont assignables même sans compte email.</p>}
          </div>
          {/* Per-technician notes (private) */}
          <TechNotesSection projectId={project.id} assignedList={assignedList} />
          {canEditPlan ? (
            <div>
              <Label>Notes générales du chantier</Label>
              <Textarea rows={3} value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="project-general-notes" />
              <p className="text-[11px] text-slate-500 mt-1">Notes visibles par l'ensemble de l'équipe (contrairement aux notes individuelles ci-dessus).</p>
            </div>
          ) : (form.notes && form.notes.trim() ? (
            <div>
              <Label>Notes générales du chantier</Label>
              <div className="mt-1 rounded-md border border-slate-200 bg-slate-50 p-2.5 text-sm text-slate-700 whitespace-pre-wrap" data-testid="project-general-notes-readonly">
                {form.notes}
              </div>
              <p className="text-[11px] text-slate-500 mt-1">Note laissée par l'équipe / la direction pour ce chantier.</p>
            </div>
          ) : null)}

          <div>
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <Label className="flex items-center gap-1.5"><Camera size={14} /> Photos du chantier ({form.photos?.length || 0})</Label>
              {/* Two hidden inputs: camera (with capture) + gallery (no capture) */}
              <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                multiple
                capture="environment"
                className="hidden"
                onChange={(e) => { addPhotos(e.target.files); e.target.value = ""; }}
                data-testid="project-photo-camera-input"
              />
              <input
                ref={galleryRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => { addPhotos(e.target.files); e.target.value = ""; }}
                data-testid="project-photo-gallery-input"
              />
              {canAddPhotos && (
                <div className="flex items-center gap-2" data-testid="project-photo-actions">
                  <Button variant="outline" size="sm" onClick={() => cameraRef.current?.click()} disabled={uploading} data-testid="project-photo-camera-btn">
                    {uploading ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Camera size={14} className="mr-1" />}
                    Appareil photo
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => galleryRef.current?.click()} disabled={uploading} data-testid="project-photo-gallery-btn">
                    <ImageIcon size={14} className="mr-1" />
                    Galerie
                  </Button>
                </div>
              )}
              {!canAddPhotos && (
                <span className="text-[11px] text-slate-400 italic" data-testid="project-photo-readonly-hint">Lecture seule</span>
              )}
            </div>
            {!canViewPhotos ? (
              <p className="text-xs text-slate-500 italic border border-dashed border-slate-200 rounded-md p-3 text-center" data-testid="project-photo-hidden">Vous n'avez pas accès aux photos de ce chantier.</p>
            ) : form.photos && form.photos.length > 0 ? (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {form.photos.map((p, idx) => {
                  const src = photoSrc(p);
                  if (!src) return null;
                  const gps = photoGps(p);
                  const addedBy = photoAddedBy(p);
                  const createdAt = photoCreatedAt(p);
                  return (
                    <div key={idx} className="relative group rounded-lg overflow-hidden border border-slate-200 bg-slate-50 flex flex-col" data-testid={`project-photo-item-${idx}`}>
                      <div className="relative aspect-square">
                        <img src={src} alt={`Photo ${idx + 1}`} loading="lazy" decoding="async" className="absolute inset-0 w-full h-full object-cover cursor-pointer" onClick={() => setLightboxIndex(idx)} data-testid={`project-photo-${idx}`} />
                        {gps && (
                          <a
                            href={`https://www.google.com/maps?q=${gps.lat},${gps.lng}`}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="absolute bottom-1 left-1 bg-white/90 hover:bg-white rounded-full px-1.5 py-0.5 shadow-sm text-[10px] font-medium text-slate-700 flex items-center gap-0.5"
                            title={`GPS ${gps.lat.toFixed(5)}, ${gps.lng.toFixed(5)} — voir sur Google Maps`}
                            data-testid={`project-photo-${idx}-gps`}
                          >
                            <MapPinIcon size={9} className="text-emerald-600" />GPS
                          </a>
                        )}
                        {canAddPhotos && (
                          <button onClick={() => removePhoto(idx)} className="absolute top-1 right-1 bg-white/90 hover:bg-red-100 rounded-full p-1 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`project-photo-${idx}-remove`}><X size={12} className="text-red-600" /></button>
                        )}
                      </div>
                      {(addedBy || createdAt) && (
                        <div className="px-1.5 py-1 text-[10px] leading-tight text-slate-600 bg-white/95 border-t border-slate-100" data-testid={`project-photo-${idx}-meta`}>
                          {addedBy && <span className="font-medium text-slate-800 truncate block" title={addedBy}>{addedBy}</span>}
                          {createdAt && <span className="text-slate-400" title={createdAt}>{fmtDateTime(createdAt)}</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic border border-dashed border-slate-200 rounded-md p-3 text-center">Aucune photo. {canAddPhotos ? "Prenez ou choisissez des photos du chantier — la position GPS est enregistrée automatiquement." : "Les techniciens et administrateurs pourront en ajouter."}</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fermer</Button>
          {!alreadyDone && canCompleteChantier && (
            <Button
              onClick={() => setCompleteOpen(true)}
              variant="secondary"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
              data-testid="project-complete-btn"
              disabled={(form.photos || []).length === 0}
              title={(form.photos || []).length === 0 ? "Ajoutez au moins une photo avant de valider" : "Marquer ce chantier comme terminé"}
            >
              <CheckCheck size={14} className="mr-1.5" /> {completeBtnLabel}
            </Button>
          )}
          <Button onClick={save} data-testid="project-save-btn">Enregistrer</Button>
        </DialogFooter>
      </DialogContent>

      {/* iter211 : sous-dialog "Retirer ce jour / tout le chantier" */}
      <Dialog open={!!removeChoiceOpen} onOpenChange={(v) => { if (!v) setRemoveChoiceOpen(null); }}>
        <DialogContent className="sm:max-w-md" data-testid="project-remove-choice-dialog">
          <DialogHeader>
            <DialogTitle>Retirer {removeChoiceOpen?.name || "cette personne"} du chantier</DialogTitle>
            <p className="text-sm text-slate-500">
              Ce chantier s'étale sur {projectDays.length} jours. Voulez-vous retirer <b>{removeChoiceOpen?.name}</b> uniquement pour un jour, ou pour l'intégralité du chantier ?
            </p>
          </DialogHeader>
          <div className="flex flex-wrap gap-1.5" data-testid="project-remove-day-picker">
            {projectDays.map((k) => {
              const already = ((form?.day_exclusions || {})[k] || []).includes(removeChoiceOpen?.name);
              const sel = removeChoiceOpen?.day === k;
              return (
                <button key={k} type="button" disabled={already} data-testid={`project-remove-day-${k}`}
                  onClick={() => setRemoveChoiceOpen((s) => ({ ...s, day: k }))}
                  className={`text-xs px-2.5 py-1.5 rounded-md border transition-colors ${sel ? "bg-amber-500 text-white border-amber-500" : "border-slate-200 hover:bg-amber-50"} ${already ? "opacity-40 line-through cursor-not-allowed" : ""}`}>
                  {fmtDay(k)}
                </button>
              );
            })}
          </div>
          <DialogFooter className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
            <Button variant="outline" onClick={() => setRemoveChoiceOpen(null)} data-testid="project-remove-cancel">Annuler</Button>
            <Button variant="outline" onClick={removeForThisDayOnly} data-testid="project-remove-this-day-btn" className="border-amber-300 text-amber-800 hover:bg-amber-50">Uniquement le {removeChoiceOpen?.day ? new Date(removeChoiceOpen.day + "T00:00:00").toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) : "jour"}</Button>
            <Button onClick={removeForWholeProject} data-testid="project-remove-whole-btn" className="bg-red-600 hover:bg-red-700 text-white">Tout le chantier</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Sous-dialog : confirmation "Chantier terminé" */}
      <Dialog open={completeOpen} onOpenChange={(v) => { if (!completing) setCompleteOpen(v); }}>        <DialogContent className="sm:max-w-md" data-testid="project-complete-dialog">
          <DialogHeader>
            <DialogTitle>Valider la fin du chantier</DialogTitle>
            <p className="text-sm text-slate-500">
              Le commercial en charge sera automatiquement notifié (in-app + email). Les photos et l'historique sont conservés.
            </p>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-xs text-slate-600 flex items-center gap-2">
              <ImageIcon size={13} className="text-slate-400" />
              <span>{(form.photos || []).length} photo(s) attachée(s) au chantier.</span>
            </div>
            <div>
              <Label>Note de fin de chantier (facultatif)</Label>
              <Textarea
                value={completeNote}
                onChange={(e) => setCompleteNote(e.target.value)}
                placeholder="Ex : Installation terminée, tests OK. Le client a signé le PV."
                rows={3}
                data-testid="project-complete-note"
              />
            </div>
            {projectDays.length > 1 && form.status !== "termine" && (
              <div data-testid="project-complete-day-picker">
                <Label>Journée d'intervention à valider ({doneCount}/{projectDays.length} déjà terminée{doneCount > 1 ? "s" : ""})</Label>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {projectDays.map((d) => {
                    const done = !!daysDone[d];
                    const future = d > todayIso;
                    const sel = chosenDay === d;
                    return (
                      <button key={d} type="button" disabled={done || future} onClick={() => setCompleteDay(d)} data-testid={`project-complete-day-${d}`}
                        title={done ? "Déjà validée" : future ? "Intervention à venir" : ""}
                        className={`text-xs px-2.5 py-1.5 rounded-md border transition-colors ${done ? "bg-emerald-50 border-emerald-200 text-emerald-700 cursor-default" : future ? "opacity-40 cursor-not-allowed border-slate-200" : sel ? "bg-emerald-600 text-white border-emerald-600" : "border-slate-200 hover:bg-emerald-50"}`}>
                        {done ? "✓ " : ""}{fmtDay(d)}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[11px] text-slate-500 mt-1.5">Le chantier passera en « terminé » uniquement quand toutes les journées seront validées.</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompleteOpen(false)} disabled={completing}>Annuler</Button>
            <Button onClick={completeChantier} disabled={completing} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="project-complete-confirm-btn">
              {completing ? (<><Loader2 size={13} className="mr-1.5 animate-spin" /> Envoi…</>) : (<><CheckCheck size={13} className="mr-1.5" /> Valider et notifier</>)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* iter153/155/201 : lightbox plein écran avec ZOOM (roulette, double-clic, pinch),
          monté via portal pour NE PAS être enfant du <Dialog> Radix — évite que les clics
          chevrons/backdrop bullent jusqu'au dialog parent (qui interprétait comme
          "outside click" et fermait la fiche chantier). */}
      {lightboxIndex !== null && form.photos && form.photos[lightboxIndex] && createPortal((() => {
        const total = form.photos.length;
        const p = form.photos[lightboxIndex];
        const src = photoSrc(p);
        if (!src) return null;
        const gps = photoGps(p);
        const addedBy = photoAddedBy(p);
        const createdAt = photoCreatedAt(p);
        const go = (delta) => { setZoomScale(1); setZoomTx(0); setZoomTy(0); setLightboxIndex((i) => ((i + delta) % total + total) % total); };
        const close = (e) => { e?.stopPropagation?.(); setLightboxIndex(null); setZoomScale(1); setZoomTx(0); setZoomTy(0); };
        const clampScale = (s) => Math.max(1, Math.min(6, s));
        const zoomIn = () => setZoomScale((s) => clampScale(s * 1.4));
        const zoomOut = () => setZoomScale((s) => {
          const next = clampScale(s / 1.4);
          if (next === 1) { setZoomTx(0); setZoomTy(0); }
          return next;
        });
        const resetZoom = () => { setZoomScale(1); setZoomTx(0); setZoomTy(0); };
        const onWheel = (e) => { e.preventDefault(); setZoomScale((s) => {
          const next = clampScale(s * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
          if (next === 1) { setZoomTx(0); setZoomTy(0); }
          return next;
        }); };
        const onDoubleClick = (e) => { e.stopPropagation(); setZoomScale((s) => s === 1 ? 2.5 : (setZoomTx(0), setZoomTy(0), 1)); };
        const onImgMouseDown = (e) => {
          if (zoomScale <= 1) return;
          e.stopPropagation();
          const sx = zoomTx, sy = zoomTy, x0 = e.clientX, y0 = e.clientY;
          const mv = (ev) => { setZoomTx(sx + (ev.clientX - x0)); setZoomTy(sy + (ev.clientY - y0)); };
          const up = () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); };
          window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
        };
        // iter206 : PINCH mobile (2 doigts) + DRAG mobile (1 doigt quand zoomé).
        // Fixe le bug « impossible de zoomer sur les photos » côté technicien mobile.
        // iter206b : refs déclarés au niveau composant (rules-of-hooks) — voir plus haut.
        const dist2 = (t1, t2) => Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        const onImgTouchStart = (e) => {
          e.stopPropagation();
          if (e.touches.length === 2) {
            pinchStateRef.current = { startDist: dist2(e.touches[0], e.touches[1]), startScale: zoomScale };
          } else if (e.touches.length === 1 && zoomScale > 1) {
            const t = e.touches[0];
            dragStateRef.current = { dragging: true, x0: t.clientX, y0: t.clientY, sx: zoomTx, sy: zoomTy };
          }
        };
        const onImgTouchMove = (e) => {
          if (e.touches.length === 2) {
            e.preventDefault(); e.stopPropagation();
            const d = dist2(e.touches[0], e.touches[1]);
            const ratio = d / (pinchStateRef.current.startDist || 1);
            const next = clampScale(pinchStateRef.current.startScale * ratio);
            setZoomScale(next);
            if (next === 1) { setZoomTx(0); setZoomTy(0); }
          } else if (e.touches.length === 1 && dragStateRef.current.dragging) {
            e.preventDefault(); e.stopPropagation();
            const t = e.touches[0];
            setZoomTx(dragStateRef.current.sx + (t.clientX - dragStateRef.current.x0));
            setZoomTy(dragStateRef.current.sy + (t.clientY - dragStateRef.current.y0));
          }
        };
        const onImgTouchEnd = () => { dragStateRef.current.dragging = false; };
        return (
          <div
            className="fixed inset-0 z-[9999] bg-black/90 flex flex-col items-center justify-center backdrop-blur-sm"
            style={{ pointerEvents: "auto" }}
            onClick={close}
            onPointerDown={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            onWheel={onWheel}
            data-testid="project-photo-lightbox"
          >
            <div className="absolute top-3 left-3 right-3 flex items-center justify-between text-white text-xs z-10">
              <div className="bg-black/40 rounded-full px-3 py-1 backdrop-blur-md">
                {lightboxIndex + 1} / {total}
                {addedBy && <span className="opacity-70"> · {addedBy}</span>}
                {createdAt && <span className="opacity-50"> · {fmtDateTime(createdAt)}</span>}
              </div>
              <div className="flex items-center gap-1.5">
                {gps && (
                  <a
                    href={`https://www.google.com/maps?q=${gps.lat},${gps.lng}`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="bg-white/95 hover:bg-white text-slate-900 rounded-full px-2.5 py-1 font-medium flex items-center gap-1"
                    title={`GPS ${gps.lat.toFixed(5)}, ${gps.lng.toFixed(5)}`}
                    data-testid="project-photo-lightbox-gps"
                  ><MapPinIcon size={11} className="text-emerald-600" /> GPS</a>
                )}
                <a
                  href={src}
                  download={`chantier-photo-${lightboxIndex + 1}.jpg`}
                  onClick={(e) => e.stopPropagation()}
                  className="bg-white/95 hover:bg-white text-slate-900 rounded-full px-2.5 py-1 font-medium flex items-center gap-1"
                  title="Télécharger"
                  data-testid="project-photo-lightbox-download"
                ><Download size={11} /></a>
                <button
                  onClick={close}
                  className="bg-white/95 hover:bg-white text-slate-900 rounded-full p-1.5"
                  aria-label="Fermer"
                  data-testid="project-photo-lightbox-close"
                ><X size={14} /></button>
              </div>
            </div>
            {total > 1 && zoomScale === 1 && (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); go(-1); }}
                  className="absolute left-3 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-slate-900 rounded-full p-2 shadow-lg z-10"
                  aria-label="Photo précédente"
                  data-testid="project-photo-lightbox-prev"
                ><ChevronLeft size={20} /></button>
                <button
                  onClick={(e) => { e.stopPropagation(); go(1); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-slate-900 rounded-full p-2 shadow-lg z-10"
                  aria-label="Photo suivante"
                  data-testid="project-photo-lightbox-next"
                ><ChevronRight size={20} /></button>
              </>
            )}
            <img
              src={src}
              alt={`Photo ${lightboxIndex + 1}`}
              onClick={(e) => e.stopPropagation()}
              onDoubleClick={onDoubleClick}
              onMouseDown={onImgMouseDown}
              onTouchStart={onImgTouchStart}
              onTouchMove={onImgTouchMove}
              onTouchEnd={onImgTouchEnd}
              draggable={false}
              style={{
                transform: `translate(${zoomTx}px, ${zoomTy}px) scale(${zoomScale})`,
                transition: "transform 0.12s ease-out",
                cursor: zoomScale > 1 ? "grab" : "zoom-in",
                touchAction: "none",
              }}
              className="max-w-[92vw] max-h-[86vh] object-contain shadow-2xl rounded select-none"
              data-testid="project-photo-lightbox-img"
            />
            {/* Contrôles zoom */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-white/95 rounded-full px-2 py-1.5 shadow-xl z-10" onClick={(e) => e.stopPropagation()}>
              <button onClick={zoomOut} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Dézoomer" data-testid="project-photo-lightbox-zoomout"><ZoomOut size={16} /></button>
              <span className="text-xs tabular-nums text-slate-700 min-w-[42px] text-center">{Math.round(zoomScale * 100)}%</span>
              <button onClick={zoomIn} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Zoomer" data-testid="project-photo-lightbox-zoomin"><ZoomIn size={16} /></button>
              <div className="w-px h-4 bg-slate-200 mx-1" />
              <button onClick={resetZoom} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Réinitialiser" data-testid="project-photo-lightbox-zoomreset"><RotateCcw size={14} /></button>
            </div>
          </div>
        );
      })(), document.body)}
    </Dialog>
  );
}
