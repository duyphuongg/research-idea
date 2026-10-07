import { sourceInk, sourceLabel } from "@/lib/sources";
import InkDot from "./InkDot";

/** Data source chip: ink dot + label. */
export default function SourceChip({ source, className = "" }: { source: string; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-rule bg-sheet px-2 py-0.5 text-xs text-ink ${className}`}
    >
      <InkDot ink={sourceInk(source)} size={7} />
      {sourceLabel(source)}
    </span>
  );
}
