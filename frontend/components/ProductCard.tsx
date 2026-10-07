import { SourceChip } from "@/components/ui";
import type { Product } from "@/lib/api";
import { PRODUCT_TYPE_LABEL, formatNumber, formatPrice, timeAgo } from "@/lib/format";
import { CARD_CLASS, CardImage, LicensedTag, PerDay, SpecCell, TAG_CHIP } from "./SignalCard";

const METRIC_LABEL = { reviews: "Reviews", views: "Views", favorites: "Lưu" } as const;

export default function ProductCard({ product }: { product: Product }) {
  const metric =
    product.velocity_metric ?? (product.reviews !== null ? "reviews" : product.views !== null ? "views" : "favorites");
  const count = product[metric];
  const delta = product.delta_7d;

  return (
    <article className={`relative ${CARD_CLASS}`}>
      <CardImage
        src={product.image_url}
        alt={product.title}
        topLeft={
          product.hot ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-ink bg-ink px-2 py-0.5 text-xs font-medium leading-4 text-white">
              🔥 Hot
            </span>
          ) : undefined
        }
        topRight={<SourceChip source={product.source} />}
      />
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-ink-2">{PRODUCT_TYPE_LABEL[product.product_type]}</span>
          <span className="shrink-0 font-mono text-[13px] font-medium text-ink">
            {formatPrice(product.price, product.currency)}
          </span>
        </div>
        <a
          href={product.url}
          target="_blank"
          rel="noopener noreferrer"
          className="line-clamp-2 min-h-10 text-sm font-medium leading-5 text-ink after:absolute after:inset-0 hover:underline"
        >
          {product.title}
        </a>
        <p className="truncate text-xs text-ink-2">
          {product.shop_name ?? "—"}
          {product.shop_sold_count !== null && (
            <>
              {" · shop đã bán "}
              <span className="font-mono">{formatNumber(product.shop_sold_count)}</span>
            </>
          )}
        </p>
        <p className="-mt-1.5 text-xs text-ink-2">Đăng {timeAgo(product.listed_at)}</p>
        <div className="grid grid-cols-2 gap-2 border-t border-rule pt-2">
          <SpecCell
            label={METRIC_LABEL[metric]}
            value={formatNumber(count)}
            sub={delta !== null ? <PerDay delta={delta} unit="/7 ngày" /> : undefined}
          />
          {metric !== "favorites" && product.favorites !== null ? (
            <SpecCell label="Lưu" value={formatNumber(product.favorites)} />
          ) : product.rating !== null ? (
            <SpecCell label="Đánh giá" value={`★ ${product.rating}`} />
          ) : null}
        </div>
        {product.licensed && (
          <div>
            <LicensedTag />
          </div>
        )}
        {product.keywords.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {product.keywords.map((k) => (
              <span key={k} className={TAG_CHIP}>
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
