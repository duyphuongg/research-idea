/** Signed change: ▲ go / ▼ stop / — ink-2, always mono. `value` is a ratio unless unit is given. */
export default function Delta({
  value,
  unit = "%",
  ratio = true,
  className = "",
}: {
  value: number | null;
  /** Suffix, e.g. "%" or "" for ranks. */
  unit?: string;
  /** When true (default) value is a ratio (0.25 → 25%). Set false for raw numbers like rank moves. */
  ratio?: boolean;
  className?: string;
}) {
  if (value === null || Number.isNaN(value)) {
    return <span className={`font-mono text-ink-2 ${className}`}>—</span>;
  }
  const n = ratio ? Math.round(value * 100) : Math.round(value);
  if (n === 0) {
    return <span className={`font-mono text-ink-2 ${className}`}>— 0{unit}</span>;
  }
  const up = n > 0;
  return (
    <span className={`inline-flex items-center gap-0.5 whitespace-nowrap font-mono ${up ? "text-go" : "text-stop"} ${className}`}>
      <span aria-hidden="true" className="text-[0.8em]">
        {up ? "▲" : "▼"}
      </span>
      <span className="sr-only">{up ? "tăng" : "giảm"}</span>
      {up ? "+" : "−"}
      {Math.abs(n).toLocaleString("en-US")}
      {unit}
    </span>
  );
}
