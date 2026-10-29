import React, { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus, Trash2, CheckCircle2, Circle, ListTodo } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

// iter178 — À faire aujourd'hui : liste de rappels personnels stockée localement par
// utilisateur. Ajout / suppression / cochage. Simple, rapide, sans backend pour l'MVP.
const KEY = (uid) => `kylot:todos:${uid || "anon"}`;

export default function TodayTodos() {
  const { user } = useAuth();
  const [todos, setTodos] = useState([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!user?.id) return;
    try { setTodos(JSON.parse(localStorage.getItem(KEY(user.id)) || "[]")); } catch (_) { setTodos([]); }
  }, [user?.id]);

  const persist = (list) => {
    setTodos(list);
    try { if (user?.id) localStorage.setItem(KEY(user.id), JSON.stringify(list)); } catch (_) {}
  };
  const add = () => {
    const t = draft.trim();
    if (!t) return;
    persist([{ id: `t_${Date.now()}`, text: t, done: false, at: new Date().toISOString() }, ...todos]);
    setDraft("");
  };
  const toggle = (id) => persist(todos.map((it) => it.id === id ? { ...it, done: !it.done } : it));
  const remove = (id) => persist(todos.filter((it) => it.id !== id));

  const openCount = todos.filter((t) => !t.done).length;

  return (
    <Card className="p-5 border-slate-200 shadow-sm fade-up" data-testid="today-todos">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="overline">À faire aujourd'hui</p>
          <p className="font-display text-3xl font-semibold tracking-tight mt-2">{openCount}</p>
          <p className="text-xs text-slate-500 mt-1">{openCount === 0 ? "Rien à faire — bravo !" : `${openCount} rappel${openCount > 1 ? "s" : ""} ouvert${openCount > 1 ? "s" : ""}`}</p>
        </div>
        <div className="h-10 w-10 rounded-lg grid place-items-center bg-slate-100 text-slate-700">
          <ListTodo size={18} />
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        <Input
          placeholder="Ajouter un rappel (rappeler client, docs manquants…)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          className="h-9 text-sm"
          data-testid="todo-input"
        />
        <Button size="sm" onClick={add} className="h-9 shrink-0" data-testid="todo-add-btn"><Plus size={14} className="mr-1" /> Ajouter</Button>
      </div>

      {todos.length === 0 ? (
        <p className="text-xs text-slate-400 py-2">Aucun rappel pour le moment.</p>
      ) : (
        <ul className="space-y-1 max-h-52 overflow-y-auto pr-1">
          {todos.map((t) => (
            <li key={t.id} className={`flex items-center gap-2 group px-2 py-1.5 rounded-md hover:bg-slate-50 ${t.done ? "opacity-60" : ""}`}>
              <button onClick={() => toggle(t.id)} className={t.done ? "text-emerald-600" : "text-slate-400 hover:text-slate-700"} title={t.done ? "Marquer comme non fait" : "Marquer comme fait"} data-testid={`todo-toggle-${t.id}`}>
                {t.done ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              </button>
              <span className={`flex-1 text-sm ${t.done ? "line-through text-slate-500" : "text-slate-800"}`}>{t.text}</span>
              <button onClick={() => remove(t.id)} className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition" title="Supprimer" data-testid={`todo-del-${t.id}`}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
