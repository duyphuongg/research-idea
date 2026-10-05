export default function Sparkline({ values, width = 96, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="text-xs text-zinc-400">—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 1 - ((v - min) / span) * (height - 2)).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={points} fill="none" strokeWidth={1.5} className={rising ? "stroke-green-600" : "stroke-red-500"} />
    </svg>
  );
}
