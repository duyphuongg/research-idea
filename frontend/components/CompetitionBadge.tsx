import type { CompetitionLevel } from "@/lib/api";

const LEVEL: Record<CompetitionLevel, { label: string; cls: string; dot: string }> = {
  low: { label: "Thấp", cls: "bg-go/10 border-go/40", dot: "bg-go" },
  medium: { label: "Vừa", cls: "bg-yellow/15 border-yellow/60", dot: "bg-yellow" },
  high: { label: "Cao", cls: "bg-stop/10 border-stop/40", dot: "bg-stop" },
};

/** Competition level (Etsy listing count for "<keyword> shirt"): Thấp < 10k ≤ Vừa < 50k ≤ Cao. */
export default function CompetitionBadge({ level, className = "" }: { level: CompetitionLevel; className?: string }) {
  const spec = LEVEL[level];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium leading-4 text-ink ${spec.cls} ${className}`}
    >
      <span aria-hidden="true" className={`size-1.5 shrink-0 rounded-full ${spec.dot}`} />
      {spec.label}
    </span>
  );
}
