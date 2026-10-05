import type { Product } from "@/lib/api";
import { PRODUCT_TYPE_LABEL, formatPrice, timeAgo } from "@/lib/format";

export default function ProductCard({ product }: { product: Product }) {
  const isReviews = product.reviews !== null;
  const count = isReviews ? product.reviews : product.favorites;
  const label = isReviews ? "reviews" : "favorites";
  const delta = product.delta_7d;

  return (
    <a
      href={product.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white hover:shadow-md"
    >
      <div className="relative aspect-square bg-zinc-100">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.title} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-400">Không có ảnh</div>
        )}
        {product.hot && (
          <span className="absolute left-2 top-2 rounded bg-orange-500 px-1.5 py-0.5 text-xs font-semibold text-white">
            🔥 Hot
          </span>
        )}
        <span className="absolute right-2 top-2 rounded bg-white/90 px-1.5 py-0.5 text-xs uppercase text-zinc-600">
          {product.source}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3 text-sm">
        <p className="line-clamp-2 font-medium group-hover:underline">{product.title}</p>
        <div className="flex items-center justify-between">
          <span className="font-semibold">{formatPrice(product.price, product.currency)}</span>
          <span className="text-xs text-zinc-500">{PRODUCT_TYPE_LABEL[product.product_type]}</span>
        </div>
        <p className="text-xs text-zinc-600">
          {count ?? "—"} {label}
          {delta !== null && (
            <span className={delta > 0 ? "ml-1 text-green-600" : "ml-1 text-zinc-400"}>
              ({delta > 0 ? "+" : ""}
              {Math.round(delta)} / 7 ngày)
            </span>
          )}
        </p>
        <p className="text-xs text-zinc-500">
          {product.shop_name ?? "—"} · đăng {timeAgo(product.listed_at)}
        </p>
        {product.keywords.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {product.keywords.map((k) => (
              <span key={k} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </a>
  );
}
