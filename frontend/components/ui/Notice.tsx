import type { ReactNode } from "react";

export type NoticeTone = "info" | "warn" | "error";

const TONE: Record<NoticeTone, { bar: string; bg: string; icon: string; role?: "alert" | "status" }> = {
  info: { bar: "border-l-cyan", bg: "bg-sheet", icon: "i", role: "status" },
  warn: { bar: "border-l-yellow", bg: "bg-yellow/10", icon: "!", role: "status" },
  error: { bar: "border-l-stop", bg: "bg-stop/5", icon: "✕", role: "alert" },
};

/** Inline notice: 1px rule + 3px tone bar on the left. Text stays ink for contrast. */
export default function Notice({
  tone = "info",
  title,
  children,
  action,
  className = "",
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const t = TONE[tone];
  return (
    <div
      role={t.role}
      className={`flex items-start gap-3 rounded-md border border-l-[3px] border-rule ${t.bar} ${t.bg} px-3 py-2.5 text-sm text-ink ${className}`}
    >
      <span
        aria-hidden="true"
        className="mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full border border-ink font-mono text-[10px] leading-none"
      >
        {t.icon}
      </span>
      <div className="min-w-0 flex-1 space-y-0.5">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-ink">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
