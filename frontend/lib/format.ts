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
