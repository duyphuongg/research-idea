"use client";

import { useState, type FormEvent } from "react";
import { Select } from "@/components/ui";
import type { WorkKind, WorkStatusValue } from "@/lib/api";
import { WORK_STATUS, WORK_STATUSES, clearWork, saveWork, useWorkItem } from "@/lib/work";

const CLEAR = "__clear";

const SET_CLASS: Record<WorkStatusValue, string> = {
  idea: "border-yellow/70! bg-yellow/10!",
  designing: "border-cyan/60! bg-cyan/10!",
  listed: "border-go/60! bg-go/10!",
  skipped: "bg-paper! text-ink-2!",
};

/**
 * Compact "where am I with this" control for a keyword or a product.
 * Reads the shared work list (one fetch per app load) and saves optimistically.
 */
export default function WorkStatus({
  kind,
  id,
  title,
  withNote = false,
  className = "",
}: {
  kind: WorkKind;
  id: number;
  /** Subject name, used as the accessible label. */
  title?: string;
  /** Show a short note next to the status (editable). */
  withNote?: boolean;
  className?: string;
}) {
  const item = useWorkItem(kind, id);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(String(err));
    }
  }

  function onSelect(value: string) {
    if (value === CLEAR) run(() => clearWork(kind, id));
    else if (value) run(() => saveWork(kind, id, value as WorkStatusValue, item?.note ?? null, title));
  }

  function saveNote(e?: FormEvent) {
    e?.preventDefault();
    setEditing(false);
    if (!item) return;
    const note = draft.trim() || null;
    if (note === (item.note ?? null)) return;
    run(() => saveWork(kind, id, item.status, note, title));
  }

  return (
    <div className={`relative z-10 flex min-w-0 flex-wrap items-center gap-1.5 ${className}`}>
      <Select
        size="sm"
        aria-label={title ? `Trạng thái việc: ${title}` : "Trạng thái việc"}
        value={item?.status ?? ""}
        onChange={(e) => onSelect(e.target.value)}
        className={item ? `font-medium ${SET_CLASS[item.status]}` : "text-ink-2"}
      >
        <option value="">+ Trạng thái</option>
        {WORK_STATUSES.map((s) => (
          <option key={s} value={s}>
            {WORK_STATUS[s].icon} {WORK_STATUS[s].label}
          </option>
        ))}
        {item && <option value={CLEAR}>✕ Bỏ trạng thái</option>}
      </Select>

      {withNote && item && !editing && (
        <button
          type="button"
          onClick={() => {
            setDraft(item.note ?? "");
            setEditing(true);
          }}
          className="min-w-0 max-w-full truncate rounded-md px-1.5 text-left text-xs leading-7 text-ink-2 hover:bg-ink/5 hover:text-ink"
          title={item.note ?? "Thêm ghi chú"}
        >
          {item.note ? <>📝 {item.note}</> : "+ Ghi chú"}
        </button>
      )}
      {withNote && item && editing && (
        <form onSubmit={saveNote} className="flex min-w-0 flex-1 basis-48">
          <input
            autoFocus
            value={draft}
            maxLength={500}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => saveNote()}
            onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
            placeholder="Ghi chú ngắn, Enter để lưu"
            aria-label="Ghi chú"
            className="h-7 min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 text-xs text-ink placeholder:text-ink-2/70 hover:border-ink-2"
          />
        </form>
      )}

      {error && (
        <span role="alert" title={error} className="text-xs text-stop">
          Chưa lưu được
        </span>
      )}
    </div>
  );
}
