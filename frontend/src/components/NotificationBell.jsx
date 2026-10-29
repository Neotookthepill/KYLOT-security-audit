import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Bell, Check, Trash2, CheckCheck } from "lucide-react";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent } from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const s = Math.max(1, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `il y a ${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `il y a ${h} h`;
  const d = Math.round(h / 24);
  return `il y a ${d} j`;
}

export default function NotificationBell({ tone = "dark" }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications");
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch (_) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000); // refresh every minute
    return () => clearInterval(t);
  }, [load]);

  const markRead = async (n) => {
    if (n.is_read) return;
    try {
      await api.put(`/notifications/${n.id}/read`);
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const markAll = async () => {
    try {
      await api.post("/notifications/read-all");
      setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
      setUnread(0);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/notifications/${id}`);
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const buttonCls = tone === "light"
    ? "relative h-9 w-9 grid place-items-center rounded-md text-slate-600 hover:bg-slate-100"
    : "relative h-9 w-9 grid place-items-center rounded-md text-white/80 hover:bg-white/10 hover:text-white";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button className={buttonCls} data-testid="notif-bell-btn" aria-label="Notifications">
          <Bell size={18} />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold grid place-items-center" data-testid="notif-badge">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[340px] max-h-[70vh] overflow-y-auto p-0" data-testid="notif-dropdown">
        <div className="flex items-center justify-between p-3 border-b border-slate-100">
          <p className="font-display text-sm font-semibold">Notifications</p>
          {items.some((n) => !n.is_read) && (
            <button onClick={markAll} className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1" data-testid="notif-read-all">
              <CheckCheck size={12} /> Tout marquer lu
            </button>
          )}
        </div>
        {items.length === 0 && (
          <div className="p-6 text-center text-sm text-slate-500">Aucune notification.</div>
        )}
        <div>
          {items.map((n) => (
            <div key={n.id} className={`p-3 border-b border-slate-100 last:border-0 flex gap-2 items-start ${!n.is_read ? "bg-indigo-50/40" : ""}`} data-testid={`notif-item-${n.id}`}>
              <div className="flex-1 min-w-0">
                {n.link_url ? (
                  <Link to={n.link_url} onClick={() => { markRead(n); setOpen(false); }} className="block">
                    <p className={`text-sm ${!n.is_read ? "font-semibold" : "font-medium"} text-slate-900`}>{n.title}</p>
                    <p className="text-xs text-slate-600 mt-0.5">{n.message}</p>
                  </Link>
                ) : (
                  <button onClick={() => markRead(n)} className="text-left w-full">
                    <p className={`text-sm ${!n.is_read ? "font-semibold" : "font-medium"} text-slate-900`}>{n.title}</p>
                    <p className="text-xs text-slate-600 mt-0.5">{n.message}</p>
                  </button>
                )}
                <p className="text-[10px] text-slate-400 mt-1">{timeAgo(n.created_at)}</p>
              </div>
              <div className="flex flex-col gap-1">
                {!n.is_read && (
                  <button onClick={() => markRead(n)} className="text-slate-400 hover:text-emerald-700" aria-label="Marquer lu"><Check size={12} /></button>
                )}
                <button onClick={() => remove(n.id)} className="text-slate-400 hover:text-red-600" aria-label="Supprimer"><Trash2 size={12} /></button>
              </div>
            </div>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
