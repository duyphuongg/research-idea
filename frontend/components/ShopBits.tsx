import type { Shop, ShopDelta } from "@/lib/api";
import { formatInt } from "@/lib/format";

/** Shop icon (square, rounded) with an initial-letter fallback. */
export function ShopIcon({ shop, size = 28 }: { shop: Pick<Shop, "name" | "icon_url">; size?: number }) {
  const style = { width: size, height: size };
  if (shop.icon_url)
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={shop.icon_url}
        alt=""
        loading="lazy"
        style={style}
        className="shrink-0 rounded-md border border-rule bg-paper object-cover"
      />
    );
  return (
    <span
      aria-hidden="true"
      style={style}
      className="inline-flex shrink-0 items-center justify-center rounded-md border border-rule bg-paper font-display text-xs font-bold uppercase text-ink-2"
    >
      {shop.name.slice(0, 1)}
    </span>
  );
}

/**
 * Orders added over a window, mono: "+12", plus a small "(3 ngày)" when the history is shorter than the
 * window. Missing history is "—", never 0.
 */
export function SalesDelta({
  delta,
  window,
  className = "",
}: {
  delta: ShopDelta | null;
  window: number;
  className?: string;
}) {
  if (!delta) return <span className={`font-mono text-ink-2 ${className}`}>—</span>;
  const sign = delta.value > 0 ? "+" : delta.value < 0 ? "−" : "";
  return (
    <span className={`whitespace-nowrap font-mono ${className}`}>
      <span className={delta.value > 0 ? "text-ink" : "text-ink-2"}>
        {sign}
        {formatInt(Math.abs(delta.value))}
      </span>
      {delta.days < window && <span className="ml-1 text-[11px] text-ink-2">({delta.days} ngày)</span>}
    </span>
  );
}

/** ☆ / ★ toggle for watching a shop. */
export function WatchToggle({
  shop,
  busy = false,
  onToggle,
  withLabel = false,
}: {
  shop: Pick<Shop, "name" | "watched">;
  busy?: boolean;
  onToggle: () => void;
  withLabel?: boolean;
}) {
  // Static accessible name; the on/off state is conveyed by aria-pressed.
  const label = `Theo dõi ${shop.name}`;
  return (
    <button
      type="button"
      aria-pressed={shop.watched}
      aria-label={withLabel ? undefined : label}
      title={shop.watched ? `Đang theo dõi — bấm để bỏ theo dõi ${shop.name}` : label}
      disabled={busy}
      onClick={onToggle}
      className={`inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border text-sm transition-colors disabled:opacity-50 ${
        withLabel ? "px-3" : "w-8"
      } ${shop.watched ? "border-ink bg-ink text-yellow" : "border-rule bg-sheet text-ink-2 hover:border-ink-2 hover:text-ink"}`}
    >
      <span aria-hidden="true" className="text-base leading-none">
        {shop.watched ? "★" : "☆"}
      </span>
      {withLabel && <span className={shop.watched ? "text-white" : "text-ink"}>{shop.watched ? "Đang theo dõi" : "Theo dõi"}</span>}
    </button>
  );
}

/** Orders per listing: one decimal below 100, whole number above. */
export function formatSpl(n: number | null): string {
  if (n === null) return "—";
  const digits = n < 100 ? 1 : 0;
  return n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** "★ 4.9 (1,234)" or "—". */
export function formatRating(avg: number | null, count?: number | null): string {
  if (avg === null) return "—";
  const base = `★ ${avg.toFixed(1)}`;
  return count ? `${base} (${formatInt(count)})` : base;
}
