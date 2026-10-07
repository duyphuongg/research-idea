import type { CalendarPhase, ScanStatus, SignalStatus } from "@/lib/api";

type Tone = "go" | "stop" | "yellow" | "cyan" | "magenta" | "ink" | "muted";
type Fill = "solid" | "tint";

type Spec = { tone: Tone; fill: Fill; label: string; pulse?: boolean; strike?: boolean };

export const SCAN_BADGE: Record<ScanStatus, Spec> = {
  ok: { tone: "go", fill: "tint", label: "Thành công" },
  partial: { tone: "yellow", fill: "tint", label: "Một phần" },
  failed: { tone: "stop", fill: "solid", label: "Lỗi" },
  running: { tone: "cyan", fill: "tint", label: "Đang quét", pulse: true },
};

export const SIGNAL_BADGE: Record<SignalStatus, Spec> = {
  super_breakout: { tone: "ink", fill: "solid", label: "Super Breakout" },
  steady_grower: { tone: "go", fill: "tint", label: "Steady Grower" },
  graduated: { tone: "cyan", fill: "tint", label: "Graduated" },
  calibrating: { tone: "yellow", fill: "tint", label: "Calibrating" },
  normal: { tone: "muted", fill: "tint", label: "Bình thường" },
  gone: { tone: "muted", fill: "tint", label: "Đã gỡ", strike: true },
};

export const PHASE_BADGE: Record<CalendarPhase, Spec> = {
  upcoming: { tone: "muted", fill: "tint", label: "Sắp tới" },
  design: { tone: "cyan", fill: "tint", label: "Thiết kế" },
  launch: { tone: "yellow", fill: "tint", label: "Lên sản phẩm" },
  push: { tone: "go", fill: "solid", label: "Đẩy bán" },
  cutoff: { tone: "stop", fill: "tint", label: "Chốt đơn" },
  peak: { tone: "ink", fill: "solid", label: "Cao điểm" },
  after: { tone: "muted", fill: "tint", label: "Đã qua" },
};

// Text always stays ink (or white on dark solids) for AA contrast; the tone shows in the dot/tint.
const TINT: Record<Tone, string> = {
  go: "bg-go/10 border-go/40 text-ink",
  stop: "bg-stop/10 border-stop/40 text-ink",
  yellow: "bg-yellow/15 border-yellow/60 text-ink",
  cyan: "bg-cyan/10 border-cyan/40 text-ink",
  magenta: "bg-magenta/10 border-magenta/40 text-ink",
  ink: "bg-ink/5 border-ink/30 text-ink",
  muted: "bg-paper border-rule text-ink-2",
};
const SOLID: Record<Tone, string> = {
  go: "bg-go border-go text-white",
  stop: "bg-stop border-stop text-white",
  yellow: "bg-yellow border-yellow text-ink",
  cyan: "bg-cyan border-cyan text-ink",
  magenta: "bg-magenta border-magenta text-white",
  ink: "bg-ink border-ink text-white",
  muted: "bg-ink-2 border-ink-2 text-white",
};
const DOT: Record<Tone, string> = {
  go: "bg-go",
  stop: "bg-stop",
  yellow: "bg-yellow",
  cyan: "bg-cyan",
  magenta: "bg-magenta",
  ink: "bg-ink",
  muted: "bg-ink-2/60",
};

type Props =
  | { kind: "scan"; status: ScanStatus; label?: string; className?: string }
  | { kind: "signal"; status: SignalStatus; label?: string; className?: string }
  | { kind: "phase"; status: CalendarPhase; label?: string; className?: string };

export default function StatusBadge(props: Props) {
  const spec =
    props.kind === "scan"
      ? SCAN_BADGE[props.status]
      : props.kind === "signal"
        ? SIGNAL_BADGE[props.status]
        : PHASE_BADGE[props.status];
  const label = props.label ?? spec.label;
  const cls = spec.fill === "solid" ? SOLID[spec.tone] : TINT[spec.tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium leading-4 ${cls} ${spec.strike ? "line-through" : ""} ${props.className ?? ""}`}
    >
      {spec.fill === "tint" && (
        <span
          aria-hidden="true"
          className={`size-1.5 shrink-0 rounded-full ${DOT[spec.tone]} ${spec.pulse ? "motion-safe:animate-pulse" : ""}`}
        />
      )}
      {label}
    </span>
  );
}
