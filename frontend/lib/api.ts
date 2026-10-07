export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
};

export type ProductPage = { total: number; items: Product[] };

export type ProductQuery = {
  source?: string;
  type?: ProductType;
  keyword_id?: number;
  sort?: ProductSort;
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
};

export type TrendPage = { date: string | null; items: TrendItem[] };

export type TrendQuery = {
  source?: string;
  origin?: "seed" | "discovered";
  pod_only?: boolean;
  limit?: number;
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
  listProducts: (q: ProductQuery = {}) => request<ProductPage>(`/api/products${toQuery(q)}`),
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
  getCalendar: (days = 120) => request<CalendarPage>(`/api/calendar${toQuery({ days })}`),
};
