import type { SelectHTMLAttributes } from "react";

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> & { label?: string; size?: "sm" | "md" };

/** Native select styled as a sheet field. Pass `label` for a visible eyebrow label. */
export default function Select({ label, size = "md", className = "", children, ...rest }: Props) {
  const select = (
    <span className="relative inline-flex">
      <select
        className={`appearance-none rounded-md border border-rule bg-sheet pl-2.5 pr-7 text-ink hover:border-ink-2 disabled:opacity-50 ${size === "sm" ? "h-7 text-xs" : "h-9 text-sm"} ${className}`}
        {...rest}
      >
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 10 6"
        className="pointer-events-none absolute right-2.5 top-1/2 h-1.5 w-2.5 -translate-y-1/2 text-ink-2"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path d="M1 1l4 4 4-4" />
      </svg>
    </span>
  );
  if (!label) return select;
  return (
    <label className="inline-flex flex-col gap-1">
      <span className="eyebrow text-ink-2">{label}</span>
      {select}
    </label>
  );
}
