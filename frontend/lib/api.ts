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
};
