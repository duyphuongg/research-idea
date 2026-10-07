import Link from "next/link";
import type { ReactNode } from "react";
import { HalftoneMeter, ImageZoom, StatusBadge } from "@/components/ui";
import type { SignalItem, SignalStatus } from "@/lib/api";
import { formatNumber, formatPrice } from "@/lib/format";

export const STATUS_LABEL: Record<SignalStatus, string> = {
  super_breakout: "Super Breakout",
  steady_grower: "Steady Grower",
  graduated: "Graduated",
  calibrating: "Calibrating",
  normal: "Bình thường",
  gone: "Đã gỡ",
};

/* ── Shared product-card system (used by SignalCard and ProductCard) ── */

export const CARD_CLASS =
  "group flex min-w-0 flex-col overflow-hidden rounded-md border border-rule bg-sheet shadow-card transition-colors hover:border-ink-2";

/** 4:5 product image on paper (click to zoom), with optional overlays in the corners. */
export function CardImage({
  src,
  alt,
  href,
  topLeft,
  topRight,
}: {
  src: string | null;
  alt: string;
  href?: string;
  topLeft?: ReactNode;
  topRight?: ReactNode;
}) {
  return (
    <div className="relative aspect-[4/5] border-b border-rule bg-paper">
      {src ? (
        <ImageZoom src={src} alt={alt} href={href} className="relative z-10 h-full w-full">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={alt} className="h-full w-full object-cover" loading="lazy" />
        </ImageZoom>
      ) : (
        <div className="flex h-full items-center justify-center text-xs text-ink-2">Không có ảnh</div>
      )}
      {topLeft && <div className="pointer-events-none absolute left-2 top-2 z-20 flex flex-wrap gap-1">{topLeft}</div>}
      {topRight && <div className="pointer-events-none absolute right-2 top-2 z-20">{topRight}</div>}
    </div>
  );
}

/** One cell of the spec row: eyebrow label, mono value, optional sub line. */
export function SpecCell({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow text-[10px] leading-4 text-ink-2">{label}</p>
      <p className="truncate font-mono text-[13px] font-medium leading-5 text-ink">{value}</p>
      {sub && <p className="truncate font-mono text-[11px] leading-4">{sub}</p>}
    </div>
  );
}

/** Per-day change, mono: +n/ngày in go, −n/ngày in stop, — otherwise. */
export function PerDay({ delta, unit = "/ngày" }: { delta: number | null; unit?: string }) {
  if (delta === null) return <span className="text-ink-2">—</span>;
  if (delta === 0) return <span className="text-ink-2">0{unit}</span>;
  const abs = Math.abs(delta);
  const text = abs < 10 ? abs.toFixed(1) : String(Math.round(abs));
  return (
    <span className={delta > 0 ? "text-go" : "text-stop"}>
      {delta > 0 ? "+" : "−"}
      {text}
      {unit}
    </span>
  );
}

/** Copyright warning: magenta outline, ink text for contrast. */
export function LicensedTag() {
  return (
    <span className="inline-flex items-start gap-1.5 rounded-md border border-magenta bg-sheet px-2 py-0.5 text-[11px] font-medium leading-4 text-ink">
      <span aria-hidden="true" className="mt-[5px] size-1.5 shrink-0 rounded-full bg-magenta" />
      Có thể có bản quyền — đừng sao chép
    </span>
  );
}

export const TAG_CHIP =
  "inline-flex max-w-full items-center truncate rounded-full border border-rule bg-sheet px-2 py-0.5 text-[11px] leading-4 text-ink-2";

function formatDsr(dsr: number | null): string {
  return dsr === null ? "—" : `${(dsr * 100).toFixed(1)}%`;
}

export default function SignalCard({ item }: { item: SignalItem }) {
  return (
    <article className={CARD_CLASS}>
      <CardImage
        src={item.image_url}
        alt={item.title}
        href={item.url}
        topLeft={
          <span className="inline-flex rounded-full bg-sheet">
            <StatusBadge kind="signal" status={item.status} />
          </span>
        }
      />
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center justify-between gap-2 font-mono text-xs">
          <span className="text-ink-2">{item.age_days !== null ? `${item.age_days} ngày tuổi` : "—"}</span>
          <span className="text-[13px] font-medium text-ink">{formatPrice(item.price, item.currency)}</span>
        </div>
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="line-clamp-2 min-h-10 text-sm font-medium leading-5 text-ink hover:underline"
        >
          {item.title}
        </a>
        <p className="truncate text-xs text-ink-2">
          {item.shop_name ?? "—"}
          {item.shop_sold_count !== null && (
            <>
              {" · đã bán "}
              <span className="font-mono">{formatNumber(item.shop_sold_count)}</span>
            </>
          )}
        </p>
        <div className="grid grid-cols-3 gap-2 border-t border-rule pt-2">
          <SpecCell label="Views" value={formatNumber(item.views)} sub={<PerDay delta={item.delta_views} />} />
          <SpecCell label="Lưu" value={formatNumber(item.saves)} sub={<PerDay delta={item.delta_saves} />} />
          <SpecCell
            label="DSR"
            value={formatDsr(item.dsr)}
            sub={
              item.dsr !== null ? (
                <HalftoneMeter value={Math.min(item.dsr * 10, 1)} size="sm" className="mt-1 flex w-full max-w-[88px] [&_svg]:h-auto [&_svg]:w-full" />
              ) : undefined
            }
          />
        </div>
        {item.tags.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {item.tags.slice(0, 4).map((t) =>
              t.keyword_id !== null ? (
                <Link
                  key={t.tag}
                  href={`/trends/${t.keyword_id}`}
                  className={`${TAG_CHIP} text-ink hover:border-ink-2`}
                >
                  <span aria-hidden="true" className="mr-1 size-1.5 shrink-0 rounded-full bg-cyan" />
                  {t.tag}
                </Link>
              ) : (
                <span key={t.tag} className={TAG_CHIP}>
                  {t.tag}
                </span>
              ),
            )}
          </div>
        )}
      </div>
    </article>
  );
}
