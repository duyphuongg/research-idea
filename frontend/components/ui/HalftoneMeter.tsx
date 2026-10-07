/**
 * Signature halftone meter: 10 dots growing left → right.
 * Filled count = round(value × 10); filled dots are ink, the rest are rule outlines.
 */
const SIZES = {
  sm: { min: 3.5, max: 7, gap: 2 },
  md: { min: 4, max: 10, gap: 3 },
};

export default function HalftoneMeter({
  value,
  size = "md",
  label,
  className = "",
}: {
  value: number | null;
  size?: "sm" | "md";
  label?: string;
  className?: string;
}) {
  if (value === null || Number.isNaN(value)) {
    return <span className={`font-mono text-ink-2 ${className}`}>—</span>;
  }
  const v = Math.min(Math.max(value, 0), 1);
  const filled = Math.round(v * 10);
  const s = SIZES[size];
  const box = s.max;
  const width = 10 * box + 9 * s.gap;
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg
        width={width}
        height={box}
        viewBox={`0 0 ${width} ${box}`}
        role="img"
        aria-label={`${label ? `${label}: ` : ""}${Math.round(v * 100)}/100`}
        className="shrink-0"
      >
        {Array.from({ length: 10 }, (_, i) => {
          const d = s.min + ((s.max - s.min) * i) / 9;
          const cx = i * (box + s.gap) + box / 2;
          const on = i < filled;
          return (
            <circle
              key={i}
              cx={cx}
              cy={box / 2}
              r={on ? d / 2 : d / 2 - 0.5}
              className={on ? "fill-ink" : "fill-none stroke-rule"}
              strokeWidth={on ? 0 : 1}
            />
          );
        })}
      </svg>
      {label !== undefined && <span className="font-mono text-xs text-ink">{label}</span>}
    </span>
  );
}
