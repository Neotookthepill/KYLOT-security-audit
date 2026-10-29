import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * Reusable inline-editable cell. Types: `text`, `number`, `date`, `select`.
 * - `value`  : current value (string / number / iso date)
 * - `type`   : field type
 * - `options`: for select — [{ value, label }]
 * - `display`: optional custom rendered element for read-only state
 * - `onSave` : async (nextValue) => void — throws on error, cell rolls back
 * - `disabled`, `placeholder`, `testId`, `wrapperClass`, `inputWidth`
 * The cell stops event propagation so clicks on it don't trigger parent row handlers.
 */
export default function InlineCell({
  value,
  type = "text",
  options,
  onSave,
  display,
  disabled,
  placeholder = "—",
  testId,
  wrapperClass = "",
  inputWidth = 120,
}) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(value ?? "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (!editing) setVal(value ?? ""); }, [value, editing]);

  const commit = async (nv) => {
    const finalVal = nv === undefined ? val : nv;
    if ((finalVal ?? "") === (value ?? "")) { setEditing(false); return; }
    setSaving(true);
    try {
      await onSave(finalVal);
      setEditing(false);
    } catch (_) {
      setVal(value ?? "");
      setEditing(false);
    } finally { setSaving(false); }
  };
  const cancel = () => { setVal(value ?? ""); setEditing(false); };

  if (disabled) {
    return <span className={wrapperClass}>{display ?? (value || <span className="text-slate-400">{placeholder}</span>)}</span>;
  }

  if (editing) {
    const stop = (e) => e.stopPropagation();
    const baseCls = "h-8 px-2 text-xs border border-slate-400 rounded focus:outline-none focus:ring-1 focus:ring-slate-900 bg-white";
    if (type === "date") {
      return (
        <input type="date" autoFocus value={val || ""}
          onClick={stop} onMouseDown={stop}
          onChange={(e) => setVal(e.target.value)}
          onBlur={() => commit()}
          onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") cancel(); }}
          className={`${baseCls} w-[140px]`}
          data-testid={testId ? `${testId}-input` : undefined} />
      );
    }
    if (type === "select") {
      return (
        <select autoFocus value={val ?? ""}
          onClick={stop} onMouseDown={stop}
          onChange={(e) => { setVal(e.target.value); commit(e.target.value); }}
          onBlur={cancel}
          onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          className={`${baseCls} max-w-[220px]`}
          data-testid={testId ? `${testId}-select` : undefined}>
          <option value="">—</option>
          {(options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    if (type === "number") {
      return (
        <input type="number" autoFocus value={val ?? ""}
          onClick={stop} onMouseDown={stop}
          onChange={(e) => setVal(e.target.value)}
          onBlur={() => commit()}
          onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") cancel(); }}
          className={`${baseCls} text-right`}
          style={{ width: inputWidth }}
          data-testid={testId ? `${testId}-input` : undefined} />
      );
    }
    return (
      <input type="text" autoFocus value={val ?? ""}
        onClick={stop} onMouseDown={stop}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => commit()}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") cancel(); }}
        className={baseCls}
        style={{ width: inputWidth }}
        data-testid={testId ? `${testId}-input` : undefined} />
    );
  }

  return (
    <button type="button"
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
      className={`text-left rounded px-1.5 py-0.5 hover:bg-slate-100 hover:ring-1 hover:ring-slate-300 cursor-pointer transition inline-flex items-center gap-1 ${wrapperClass}`}
      title="Cliquer pour modifier"
      data-testid={testId}
    >
      {saving ? <Loader2 size={11} className="animate-spin text-slate-400" /> : (display ?? (value ? value : <span className="text-slate-400 italic">{placeholder}</span>))}
    </button>
  );
}
