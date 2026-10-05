import type { ProductType } from "./api";

export const PRODUCT_TYPE_LABEL: Record<ProductType, string> = {
  tshirt: "T-shirt",
  sweatshirt: "Sweatshirt",
  hoodie: "Hoodie",
};

/** Backend returns naive UTC timestamps; mark them as UTC before parsing. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const minutes = Math.floor((Date.now() - parseUtc(iso).getTime()) / 60000);
  if (minutes < 60) return `${Math.max(minutes, 0)} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} ngày trước`;
  if (days < 30) return `${Math.floor(days / 7)} tuần trước`;
  if (days < 365) return `${Math.floor(days / 30)} tháng trước`;
  return `${Math.floor(days / 365)} năm trước`;
}

export function formatPrice(price: number | null, currency: string | null): string {
  if (price === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency ?? "USD" }).format(price);
}

export const SOURCE_LABEL: Record<string, string> = {
  etsy: "Etsy",
  etsy_tags: "Etsy tag",
  google_suggest: "Google gợi ý",
  google_daily: "Google xu hướng ngày",
};

export const METRIC_LABEL: Record<string, string> = {
  views_per_day: "Lượt xem TB/ngày (shop US)",
  us_listing_count: "Số listing áo shop US (top 100 × 3)",
  new_listings_30d: "Listing mới ≤ 30 ngày (shop US)",
  listing_count_tshirt: "Tổng listing Etsy (shirt)",
  listing_count_sweatshirt: "Tổng listing Etsy (sweatshirt)",
  listing_count_hoodie: "Tổng listing Etsy (hoodie)",
  tag_count: "Số listing shop US dùng tag",
  suggest_score: "Thứ hạng gợi ý Google (10 = đầu tiên)",
  traffic: "Lượt tìm kiếm ước tính (US)",
};

export function formatGrowth(growth: number | null): string {
  if (growth === null) return "—";
  const pct = Math.round(growth * 100);
  return `${pct > 0 ? "+" : ""}${pct}%`;
}

export function formatNumber(n: number | null): string {
  if (n === null) return "—";
  return new Intl.NumberFormat("en-US", { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}
