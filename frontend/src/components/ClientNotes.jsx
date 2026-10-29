import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { StickyNote, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export const ClientNotes = ({ clientId }) => {
  const { user } = useAuth();
  const [notes, setNotes] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const isManager = ["admin", "responsable"].includes(user?.role);

  useEffect(() => {
    if (!clientId) return;
    api.get(`/clients/${clientId}/notes`).then((r) => setNotes(r.data || [])).catch(() => {});
  }, [clientId]);

  const add = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await api.post(`/clients/${clientId}/notes`, { text: text.trim() });
      setNotes((n) => [r.data, ...n]);
      setText("");
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };
  const remove = async (id) => {
    try {
      await api.delete(`/client-notes/${id}`);
      setNotes((n) => n.filter((x) => x.id !== id));
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="mt-6" data-testid="client-notes">
      <p className="overline flex items-center gap-1.5 mb-3"><StickyNote size={12} className="text-amber-600" /> Notes</p>
      <div className="flex gap-2 items-start">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="Ajouter une note sur ce client…"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) add(); }}
          className="resize-none" data-testid="client-note-input" />
        <Button onClick={add} disabled={busy || !text.trim()} className="shrink-0" data-testid="client-note-add-btn">
          {busy ? <Loader2 size={14} className="animate-spin" /> : "Ajouter"}
        </Button>
      </div>
      {notes.length === 0 && <p className="text-sm text-slate-500 py-4 text-center border border-dashed border-slate-200 rounded-lg mt-3">Aucune note.</p>}
      <div className="space-y-2 mt-3">
        {notes.map((n) => (
          <div key={n.id} className="group border border-amber-100 bg-amber-50/40 rounded-lg p-3" data-testid={`client-note-${n.id}`}>
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-slate-800 whitespace-pre-wrap break-words min-w-0">{n.text}</p>
              {(isManager || n.author_id === user?.id) && (
                <button type="button" onClick={() => remove(n.id)} className="text-slate-400 hover:text-red-600 transition-colors shrink-0" data-testid={`client-note-delete-${n.id}`} title="Supprimer"><Trash2 size={14} /></button>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">{n.author_name || "—"} · {new Date(n.created_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</p>
          </div>
        ))}
      </div>
    </div>
  );
};
