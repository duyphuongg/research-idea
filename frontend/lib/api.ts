// Same origin by default: Next.js proxies /api/* to the backend (see next.config.ts),
// so the UI works from any device that can reach port 3000.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export type ProductType = "tshirt" | "sweatshirt" | "hoodie";
export type ProductSort = "velocity" | "reviews" | "price" | "newest";

export type Product = {
  id: number;
  source: string;
  title: string;
  url: string;
  image_url: string | null;
  shop_name: string | null;
  price: number | null;
  currency: string | null;
  product_type: ProductType;
  listed_at: string | null;
  reviews: number | null;
  favorites: number | null;
  rating: number | null;
  views: number | null;
  shop_sold_count: number | null;
  velocity_metric: "reviews" | "views" | "favorites" | null;
  delta_7d: number | null;
  velocity: number | null;
  hot: boolean;
  keywords: string[];
  licensed: boolean | null;
};

export type ProductPage = { total: number; items: Product[] };

export type ProductQuery = {
  source?: string;
  type?: ProductType;
  keyword_id?: number;
  sort?: ProductSort;
  limit?: number;
  offset?: number;
  hide_licensed?: boolean;
};

export type SignalStatus = "super_breakout" | "steady_grower" | "graduated" | "calibrating" | "normal" | "gone";
export type SignalSort = "delta_saves" | "dsr" | "delta_views" | "newest";
export type SignalTag = { tag: string; keyword_id: number | null };
export type SignalItem = {
  product_id: number;
  title: string;
  url: string;
  image_url: string | null;
  shop_name: string | null;
  shop_sold_count: number | null;
  price: number | null;
  currency: string | null;
  product_type: string;
  listed_at: string | null;
  age_days: number | null;
  views: number | null;
  saves: number | null;
  delta_views: number | null;
  delta_saves: number | null;
  dsr: number | null;
  status: SignalStatus;
  discovery_query: string;
  tags: SignalTag[];
};
export type SignalPage = { updated_on: string | null; counts: Record<string, number>; total: number; items: SignalItem[] };
export type SignalQuery = {
  status?: "signals" | "all" | SignalStatus;
  max_age?: number;
  keyword?: string;
  sort?: SignalSort;
  limit?: number;
  offset?: number;
};

export type Seed = { id: number; keyword: string; active: boolean; created_at: string; keyword_id: number };

export type ConnectorStatus = { name: string; kind: string; configured: boolean; enabled: boolean };

export type AppSettings = { scan_hour_utc: number; connectors: ConnectorStatus[] };

export type ScanStatus = "running" | "ok" | "partial" | "failed";

export type ScanRun = {
  id: number;
  source: string;
  status: ScanStatus;
  started_at: string;
  finished_at: string | null;
  records: number;
  error: string | null;
};

export type SourceHealth = ConnectorStatus & {
  last_status: ScanStatus | null;
  last_finished_at: string | null;
  last_error: string | null;
};

export type TrendItem = {
  keyword_id: number;
  keyword: string;
  origin: "seed" | "discovered";
  is_pod_relevant: boolean;
  is_seed: boolean;
  is_new: boolean;
  score: number;
  demand: number | null;
  momentum: number | null;
  competition: number | null;
  growth: number | null;
  sources: string[];
  sources_rising: number;
  sparkline: number[];
  /** Latest Etsy total listing count for "<keyword> shirt" (null when unknown). */
  listing_count?: number | null;
  competition_level?: CompetitionLevel | null;
  /** 0–100: demand + momentum discounted by competition (null without competition data). */
  opportunity?: number | null;
};

export type TrendPage = { date: string | null; items: TrendItem[] };

export type TrendSort = "score" | "opportunity";
export type TrendQuery = {
  source?: string;
  origin?: "seed" | "discovered";
  pod_only?: boolean;
  sort?: TrendSort;
  limit?: number;
};

export type CompetitionLevel = "low" | "medium" | "high";

export type NichePrice = {
  /** A product type, or "all" for the row over every type. */
  product_type: ProductType | "all";
  count: number;
  p25: number | null;
  median: number | null;
  p75: number | null;
  breakout_median: number | null;
};
export type NicheTag = { tag: string; listings: number; breakouts: number; share: number; lift: number; rising: boolean };
export type NicheReport = {
  keyword: string;
  keyword_id: number | null;
  product_type: ProductType | null;
  listings: number;
  breakouts: number;
  competition: {
    date: string | null;
    counts: Partial<Record<ProductType, number | null>>;
    level: CompetitionLevel | null;
  };
  prices: NichePrice[];
  tags: NicheTag[];
  generated: { tags: string[]; title_phrases: string[] };
};

export type WorkKind = "keyword" | "product";
export type WorkStatusValue = "idea" | "designing" | "listed" | "skipped";
export type WorkItem = {
  subject_kind: WorkKind;
  subject_id: number;
  status: WorkStatusValue;
  note: string | null;
  updated_at: string;
  title: string;
  image_url: string | null;
  link: string | null;
  external_url: string | null;
};

export type SignalSeries = { source: string; metric: string; points: { date: string; value: number }[] };

export type RelatedKeyword = {
  keyword_id: number;
  keyword: string;
  relation: "child" | "parent";
  source: string;
  score: number | null;
  is_pod_relevant: boolean;
};

export type TrendDetail = {
  keyword_id: number;
  keyword: string;
  origin: "seed" | "discovered";
  is_pod_relevant: boolean;
  is_seed: boolean;
  trend: TrendItem | null;
  signals: SignalSeries[];
  related: RelatedKeyword[];
};

export type CalendarIdea = { keyword: string; keyword_id: number | null; score: number | null; is_seed: boolean };
export type CalendarMatch = { keyword_id: number; keyword: string; score: number };
export type CalendarPhase = "upcoming" | "design" | "launch" | "push" | "cutoff" | "peak" | "after";
export type CalendarEvent = {
  key: string;
  name: string;
  type: "holiday" | "occasion" | "awareness" | "sale";
  start: string;
  end: string;
  days_until: number;
  phase: CalendarPhase;
  phase_label: string;
  advice: string;
  note: string;
  design_start: string;
  launch_by: string;
  push_from: string;
  ship_by: string | null;
  order_by: string | null;
  theme_words: string[];
  seed_ideas: CalendarIdea[];
  radar_matches: CalendarMatch[];
};
export type CalendarPage = { today: string; fulfillment_days: number; events: CalendarEvent[] };

export type AlertKind = "niche" | "listing" | "hot_product" | "shop" | "nfl" | "nfl_moment" | "event";
export type AlertItem = {
  id: number;
  /** A known AlertKind, or a kind this UI does not know (shown with a fallback icon). */
  kind: AlertKind | (string & {});
  level: number;
  title: string;
  reason: string;
  image_url: string | null;
  link: string;
  external_url: string | null;
  watch_keyword: string | null;
  scan_date: string;
  created_at: string;
  read: boolean;
};
export type AlertPage = { unread: number; items: AlertItem[] };
export type TelegramStatus = { configured: boolean; app_url: string | null };
export type WatchItem = {
  seed_id: number;
  keyword: string;
  keyword_id: number | null;
  score: number | null;
  growth: number | null;
  children_total: number;
  children: { keyword_id: number; keyword: string; score: number }[];
  listings: { super_breakout: number; steady_grower: number };
  thumbnails: { product_id: number; image_url: string | null; title: string; url: string; status: SignalStatus }[];
  alerts_7d: number;
};
export type WatchPage = { date: string | null; items: WatchItem[] };

/** A change over an actual span of `days` (may be shorter than the window while history builds up). */
export type ShopDelta = { value: number; days: number };
export type Shop = {
  id: number;
  name: string;
  url: string | null;
  icon_url: string | null;
  opened_year: number | null;
  listing_count: number | null;
  sold_count: number | null;
  sales_7d: ShopDelta | null;
  sales_30d: ShopDelta | null;
  favorers_7d: ShopDelta | null;
  sales_per_listing: number | null;
  review_average: number | null;
  review_count: number | null;
  watched: boolean;
  last_seen: string;
};
export type ShopPage = { total: number; latest_date: string | null; items: Shop[] };
export type ShopPoint = { date: string; sold_count: number | null; favorers: number | null };
export type ShopDetail = Shop & { series: ShopPoint[]; products: Product[] };
export type ShopSort =
  | "sales_7d"
  | "sales_30d"
  | "sold_count"
  | "sales_per_listing"
  | "opened_at"
  | "listing_count"
  | "review_average"
  | "last_seen";
export type ShopListings = "lt200" | "200_1000" | "gt1000";
export type ShopOpened = "2026" | "2025plus" | "2024plus" | "before2024";
export type ShopQuery = {
  q?: string;
  min_sales?: number;
  listings?: ShopListings;
  min_spl?: number;
  opened?: ShopOpened;
  min_rating?: number;
  watched?: boolean;
  sort?: ShopSort;
  order?: "desc" | "asc";
  limit?: number;
  offset?: number;
};

export type NflWeek = { season: number; season_type: number; week: number; games: number };
export type NflLine = { category: string; stat_line: string };
export type NflStandout = {
  athlete_id: string;
  name: string;
  position: string | null;
  jersey: string | null;
  team: string | null;
  headshot_url: string | null;
  player_url: string | null;
  games: string[];
  lines: NflLine[];
  points: number;
  performance: number;
  etsy_listings: number | null;
  merch_suggestions: number | null;
  trending: boolean;
  potential: number;
};
export type NflPage = {
  season: number | null;
  season_type: number | null;
  week: number | null;
  weeks: NflWeek[];
  items: NflStandout[];
};
export type NflQuery = { season?: number; season_type?: number; week?: number };
export type NflMomentNews = { title: string; url: string | null; source: string | null };
export type NflMomentPlayer = {
  athlete_id: string;
  name: string;
  team: string | null;
  position: string | null;
  headshot_url: string | null;
};
export type NflMoment = {
  id: number;
  query: string;
  traffic: number;
  first_seen: string;
  last_seen: string;
  news: NflMomentNews[];
  picture_url: string | null;
  etsy_listings: number | null;
  team: string | null;
  player: NflMomentPlayer | null;
};
export type NflMomentsPage = { items: NflMoment[] };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  listProducts: (q: ProductQuery = {}) => request<ProductPage>(
      `/api/products${toQuery({ ...q, hide_licensed: q.hide_licensed ? "true" : undefined })}`,
    ),
  listSignals: (q: SignalQuery = {}) => request<SignalPage>(`/api/signals${toQuery(q)}`),
  listTrends: (q: TrendQuery = {}) =>
    request<TrendPage>(
      `/api/trends${toQuery({ ...q, pod_only: q.pod_only === undefined ? undefined : String(q.pod_only) })}`,
    ),
  getTrend: (id: number) => request<TrendDetail>(`/api/trends/${id}`),
  listSeeds: () => request<Seed[]>("/api/seeds"),
  addSeed: (keyword: string) =>
    request<Seed>("/api/seeds", { method: "POST", body: JSON.stringify({ keyword }) }),
  deleteSeed: (id: number) => request<void>(`/api/seeds/${id}`, { method: "DELETE" }),
  getSettings: () => request<AppSettings>("/api/settings"),
  updateSettings: (body: { scan_hour_utc?: number; connectors_enabled?: Record<string, boolean> }) =>
    request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  startScan: (sources?: string[]) =>
    request<{ sources: string[] }>("/api/scans", { method: "POST", body: JSON.stringify({ sources }) }),
  listScans: (limit = 20) => request<ScanRun[]>(`/api/scans${toQuery({ limit })}`),
  sourceHealth: () => request<SourceHealth[]>("/api/health/sources"),
  listAlerts: (limit = 100) => request<AlertPage>(`/api/alerts${toQuery({ limit })}`),
  unreadAlerts: () => request<{ unread: number }>("/api/alerts/unread-count"),
  markAlertsRead: () => request<{ unread: number }>("/api/alerts/read", { method: "POST" }),
  telegramStatus: () => request<TelegramStatus>("/api/alerts/telegram"),
  testTelegram: () => request<{ ok: boolean }>("/api/alerts/test", { method: "POST" }),
  getWatchlist: () => request<WatchPage>("/api/watchlist"),
  listShops: (q: ShopQuery = {}) =>
    request<ShopPage>(`/api/shops${toQuery({ ...q, watched: q.watched === undefined ? undefined : String(q.watched) })}`),
  getShop: (id: number) => request<ShopDetail>(`/api/shops/${id}`),
  watchShop: (id: number) => request<Shop>(`/api/shops/${id}/watch`, { method: "POST" }),
  unwatchShop: (id: number) => request<Shop>(`/api/shops/${id}/watch`, { method: "DELETE" }),
  getNiche: (keyword: string, productType?: ProductType) =>
    request<NicheReport>(`/api/niche${toQuery({ keyword, product_type: productType })}`),
  listWork: (status?: WorkStatusValue) => request<WorkItem[]>(`/api/work${toQuery({ status })}`),
  setWork: (kind: WorkKind, id: number, body: { status: WorkStatusValue; note: string | null }) =>
    request<WorkItem>(`/api/work/${kind}/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteWork: (kind: WorkKind, id: number) => request<void>(`/api/work/${kind}/${id}`, { method: "DELETE" }),
  getCalendar: (days = 120) => request<CalendarPage>(`/api/calendar${toQuery({ days })}`),
  getNflStandouts: (q: NflQuery = {}) => request<NflPage>(`/api/nfl/standouts${toQuery(q)}`),
  getNflMoments: (days = 7) => request<NflMomentsPage>(`/api/nfl/moments${toQuery({ days })}`),
};
