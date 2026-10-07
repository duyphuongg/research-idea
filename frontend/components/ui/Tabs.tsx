"use client";

import { useRef, type KeyboardEvent } from "react";

export type TabItem<T extends string> = { value: T; label: string; count?: number | null };

/**
 * Underlined tabs (2px ink). Controlled: pass `value` + `onChange`.
 * Arrow keys move between tabs (roving tabindex).
 */
export default function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className = "",
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Accessible name for the tab list. */
  label?: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % items.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    if (next < 0) return;
    e.preventDefault();
    refs.current[next]?.focus();
    onChange(items[next].value);
  }

  return (
    <div className={`overflow-x-auto border-b border-rule ${className}`}>
      <div role="tablist" aria-label={label} className="flex min-w-max gap-5">
        {items.map((item, i) => {
          const active = item.value === value;
          return (
            <button
              key={item.value}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(item.value)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 pb-2 pt-1 text-sm transition-colors ${
                active ? "border-ink font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"
              }`}
            >
              {item.label}
              {item.count !== undefined && item.count !== null && (
                <span className={`font-mono text-xs ${active ? "text-ink" : "text-ink-2"}`}>{item.count}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
