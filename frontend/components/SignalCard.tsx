import Link from "next/link";
import type { SignalItem, SignalStatus } from "@/lib/api";
import { formatNumber, formatPrice } from "@/lib/format";

export const STATUS_LABEL: Record<SignalStatus, string> = {
  super_breakout: "🚀 Super Breakout",
  steady_grower: "📈 Steady Grower",
  graduated: "🎓 Graduated",
  calibrating: "⏳ Calibrating",
  normal: "Bình thường",
  gone: "Đã gỡ",
};

const STATUS_CLASS: Record<SignalStatus, string> = {
  super_breakout: "bg-orange-500 text-white",
  steady_grower: "bg-green-600 text-white",
  graduated: "bg-blue-600 text-white",
  calibrating: "bg-amber-100 text-amber-800",
  normal: "bg-zinc-100 text-zinc-600",
  gone: "bg-zinc-200 text-zinc-500",
};

function formatDelta(delta: number | null): string {
  if (delta === null) return "—";
  return `${delta > 0 ? "+" : ""}${Math.round(delta)}/ngày`;
}

function formatDsr(dsr: number | null): string {
  return dsr === null ? "—" : `${(dsr * 100).toFixed(1)}%`;
}

export default function SignalCard({ item }: { item: SignalItem }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white hover:shadow-md">
      <div className="relative aspect-square bg-zinc-100">
        {item.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.image_url} alt={item.title} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-400">Không có ảnh</div>
        )}
        <span className={`absolute left-2 top-2 rounded px-1.5 py-0.5 text-xs font-semibold ${STATUS_CLASS[item.status] ?? STATUS_CLASS.normal}`}>
          {STATUS_LABEL[item.status] ?? item.status}
        </span>
        {item.age_days !== null && (
          <span className="absolute right-2 top-2 rounded bg-white/90 px-1.5 py-0.5 text-xs text-zinc-600">
            {item.age_days} ngày tuổi
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3 text-sm">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="line-clamp-2 font-medium hover:underline"
        >
          {item.title}
        </a>
        <div className="flex items-center justify-between">
          <span className="font-semibold">{formatPrice(item.price, item.currency)}</span>
          <span className="text-xs text-zinc-500">
            {item.shop_name ?? "—"}
            {item.shop_sold_count !== null && <> · đã bán {formatNumber(item.shop_sold_count)}</>}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-1 text-xs text-zinc-600">
          <p>
            <span className="block text-[10px] uppercase text-zinc-400">Views</span>
            {formatNumber(item.views)}
            <span className="block text-green-600">{formatDelta(item.delta_views)}</span>
          </p>
          <p>
            <span className="block text-[10px] uppercase text-zinc-400">Lưu</span>
            {formatNumber(item.saves)}
            <span className="block text-green-600">{formatDelta(item.delta_saves)}</span>
          </p>
          <p>
            <span className="block text-[10px] uppercase text-zinc-400">DSR</span>
            {formatDsr(item.dsr)}
          </p>
        </div>
        {item.tags.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {item.tags.slice(0, 4).map((t) =>
              t.keyword_id !== null ? (
                <Link
                  key={t.tag}
                  href={`/trends/${t.keyword_id}`}
                  className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700 hover:underline"
                >
                  {t.tag}
                </Link>
              ) : (
                <span key={t.tag} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                  {t.tag}
                </span>
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
