import type { IpHit, IpLevel } from "@/lib/api";

/** Vietnamese label for each IP term category from the backend. */
export const IP_CATEGORY_LABEL: Record<string, string> = {
  league: "giải/sự kiện",
  team: "đội",
  team_nickname: "tên đội",
  player: "cầu thủ",
  brand: "thương hiệu",
  character: "nhân vật",
  celebrity: "người nổi tiếng",
  slogan: "khẩu hiệu",
};

export function ipCategoryLabel(category: string): string {
  return IP_CATEGORY_LABEL[category] ?? category;
}

/** "nfl (giải/sự kiện), cowboys (tên đội)" */
export function formatIpHits(hits: IpHit[]): string {
  return hits.map((h) => `${h.term} (${ipCategoryLabel(h.category)})`).join(", ");
}

const LEVEL: Record<IpLevel, { label: string; cls: string; title: string }> = {
  red: { label: "🔴 Thương hiệu", cls: "bg-stop/10 border-stop/40", title: "Có thương hiệu / bản quyền — không nên dùng" },
  yellow: { label: "🟡 Cần kiểm tra", cls: "bg-yellow/15 border-yellow/60", title: "Có thể dính thương hiệu — nên kiểm tra" },
  green: { label: "🟢", cls: "bg-go/10 border-go/40", title: "Không thấy thương hiệu trong danh sách" },
};

/** IP risk badge: red/yellow by default; green only with `showGreen`. Hover lists the matched terms. */
export default function IpBadge({
  level,
  hits,
  showGreen = false,
  className = "",
}: {
  level: IpLevel | null | undefined;
  hits?: IpHit[];
  showGreen?: boolean;
  className?: string;
}) {
  if (!level || (level === "green" && !showGreen)) return null;
  const spec = LEVEL[level];
  if (!spec) return null;
  const title = hits && hits.length > 0 ? `${spec.title}: ${formatIpHits(hits)}` : spec.title;
  return (
    <span
      title={title}
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-1.5 text-[11px] font-medium leading-4 text-ink ${spec.cls} ${className}`}
    >
      {spec.label}
    </span>
  );
}
