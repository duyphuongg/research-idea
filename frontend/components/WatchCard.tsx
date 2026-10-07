import Link from "next/link";
import { TAG_CHIP } from "@/components/SignalCard";
import { Button, ButtonLink, Card, Delta, HalftoneMeter, ImageZoom, StatusBadge } from "@/components/ui";
import type { WatchItem } from "@/lib/api";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="eyebrow text-[10px] leading-4 text-ink-2">{label}</p>
      {children}
    </div>
  );
}

export default function WatchCard({ item, onRemove }: { item: WatchItem; onRemove: (item: WatchItem) => void }) {
  const { listings, thumbnails, children } = item;
  return (
    <Card className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <h2 className="min-w-0 break-words font-display font-wide text-lg font-extrabold leading-tight text-ink">
          {item.keyword}
        </h2>
        <div className="flex items-center gap-2">
          <HalftoneMeter value={item.score === null ? null : item.score / 100} size="sm" label={undefined} />
          <span className="font-mono text-sm font-medium text-ink">{item.score === null ? "—" : Math.round(item.score)}</span>
          <Delta value={item.growth} className="text-xs" />
        </div>
      </div>

      <Row label={`Ngách con (${item.children_total})`}>
        {children.length === 0 ? (
          <p className="text-sm text-ink-2">Chưa có — chờ lần quét kế tiếp</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {children.map((c) => (
              <Link key={c.keyword_id} href={`/trends/${c.keyword_id}`} className={`${TAG_CHIP} text-ink hover:border-ink-2`}>
                <span aria-hidden="true" className="mr-1 size-1.5 shrink-0 rounded-full bg-cyan" />
                {c.keyword}
                <span className="ml-1.5 font-mono text-ink-2">{Math.round(c.score)}</span>
              </Link>
            ))}
          </div>
        )}
      </Row>

      <Row label="Etsy bứt phá">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
          <span className="inline-flex items-center gap-1.5">
            <StatusBadge kind="signal" status="super_breakout" />
            <span className="font-mono text-ink">{listings.super_breakout}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <StatusBadge kind="signal" status="steady_grower" />
            <span className="font-mono text-ink">{listings.steady_grower}</span>
          </span>
        </div>
        {thumbnails.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {thumbnails.slice(0, 4).map((t) =>
              t.image_url ? (
                <ImageZoom
                  key={t.product_id}
                  src={t.image_url}
                  alt={t.title}
                  href={t.url}
                  className="size-16 overflow-hidden rounded-md border border-rule bg-paper"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={t.image_url} alt={t.title} className="size-full object-cover" loading="lazy" />
                </ImageZoom>
              ) : null,
            )}
          </div>
        )}
      </Row>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-rule pt-3">
        {item.keyword_id !== null && (
          <ButtonLink size="sm" href={`/trends/${item.keyword_id}`}>
            Xem chi tiết
          </ButtonLink>
        )}
        <ButtonLink size="sm" href={`/signals?keyword=${encodeURIComponent(item.keyword)}&status=all`}>
          Xem listing
        </ButtonLink>
        <Button size="sm" variant="ghost" onClick={() => onRemove(item)}>
          Bỏ theo dõi
        </Button>
        {item.alerts_7d > 0 && (
          <Link href="/alerts" className="ml-auto text-xs text-ink hover:underline">
            🔔 {item.alerts_7d} tin trong 7 ngày
          </Link>
        )}
      </div>
    </Card>
  );
}
