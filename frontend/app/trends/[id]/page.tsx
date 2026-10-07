"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ProductCard from "@/components/ProductCard";
import { Button, Card, Delta, EmptyState, HalftoneMeter, InkDot, Notice, PageHeader, Section } from "@/components/ui";
import { ApiError, api, type ProductPage, type TrendDetail } from "@/lib/api";
import { METRIC_LABEL, formatNumber } from "@/lib/format";
import { type Ink, sourceInk, sourceLabel } from "@/lib/sources";

type Loaded = { key: string; detail?: TrendDetail; products?: ProductPage; error?: string };

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Hex values of the process inks (app/globals.css @theme) — Recharts needs raw colours. */
const INK_HEX: Record<Ink, string> = { cyan: "#0096B7", magenta: "#C8246E", yellow: "#E3A600", ink: "#15171E" };
const RULE_HEX = "#D5DAE1";
const INK2_HEX = "#5B6170";
const AXIS_TICK = { fontSize: 10, fill: INK2_HEX, fontFamily: "var(--font-plex-mono), ui-monospace, monospace" };

function StatBlock({ label, value, meter }: { label: string; value: ReactNode; meter?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 bg-sheet p-4">
      <p className="eyebrow text-ink-2">{label}</p>
      <p className="font-mono text-[32px] font-medium leading-none text-ink">{value}</p>
      {meter && <div className="mt-auto">{meter}</div>}
    </div>
  );
}

export default function TrendDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [tick, setTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${id}#${tick}`;
  const loading = loaded?.key !== key;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getTrend(id), api.listProducts({ keyword_id: id, sort: "velocity", limit: 20 })])
      .then(([detail, products]) => !cancelled && setLoaded({ key, detail, products }))
      .catch((err) =>
        !cancelled &&
        setLoaded({ key, error: err instanceof ApiError && err.status === 404 ? "Không tìm thấy keyword." : String(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [id, key]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage("Đã thêm vào watchlist — lần quét tới sẽ lấy sản phẩm Etsy (shop US).");
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? "Keyword đã có trong watchlist." : String(err));
    }
  }

  if (loading)
    return (
      <Card className="text-sm text-ink-2" role="status">
        Đang tải…
      </Card>
    );
  if (loaded?.error || !loaded?.detail)
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-ink-2 hover:text-ink hover:underline">
          ← Trend Radar
        </Link>
        <Notice tone="error" title="Không tải được keyword">
          {loaded?.error}
        </Notice>
      </div>
    );
  const { detail, products } = loaded;
  const trend = detail.trend;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="mb-3 inline-block text-sm text-ink-2 hover:text-ink hover:underline">
          ← Trend Radar
        </Link>
        <PageHeader
          eyebrow={<>Trend Radar · Chi tiết keyword</>}
          title={detail.keyword}
          description={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>{detail.is_seed ? "seed" : "ngách khám phá"}</span>
              {!detail.is_pod_relevant && (
                <span className="inline-flex items-center gap-1.5 text-ink">
                  <InkDot ink="yellow" size={7} />
                  có thể không phải POD
                </span>
              )}
            </span>
          }
          actions={
            !detail.is_seed && (
              <Button size="sm" variant="secondary" onClick={() => follow(detail.keyword)}>
                + Theo dõi
              </Button>
            )
          }
        />
        {message && <Notice tone="info">{message}</Notice>}
      </div>

      <section aria-label="Thông số" className="overflow-hidden rounded-md border border-rule shadow-card">
        <div className="grid grid-cols-2 gap-px bg-rule sm:grid-cols-3 lg:grid-cols-5">
          <StatBlock
            label="Điểm"
            value={trend ? Math.round(trend.score) : "—"}
            meter={trend && <HalftoneMeter value={trend.score / 100} size="sm" />}
          />
          <StatBlock
            label="Nhu cầu"
            value={pct(trend?.demand ?? null)}
            meter={trend?.demand != null && <HalftoneMeter value={trend.demand} size="sm" />}
          />
          <StatBlock
            label="Đà tăng"
            value={pct(trend?.momentum ?? null)}
            meter={trend?.momentum != null && <HalftoneMeter value={trend.momentum} size="sm" />}
          />
          <StatBlock
            label="Cạnh tranh (tương đối)"
            value={pct(trend?.competition ?? null)}
            meter={trend?.competition != null && <HalftoneMeter value={trend.competition} size="sm" />}
          />
          <StatBlock
            label="Tăng trưởng"
            value={<Delta value={trend?.growth ?? null} />}
          />
          <div className="bg-sheet lg:hidden" aria-hidden="true" />
        </div>
      </section>

      <Section title="Tín hiệu 30 ngày (thị trường Mỹ)">
        {detail.signals.length === 0 && <EmptyState title="Chưa có tín hiệu" body="Tín hiệu sẽ xuất hiện sau lần quét tới." />}
        <div className="grid gap-4 md:grid-cols-2">
          {detail.signals.map((series) => {
            const ink = sourceInk(series.source);
            return (
              <Card key={`${series.source}/${series.metric}`}>
                <p className="mb-3 flex items-center gap-2 text-sm">
                  <InkDot ink={ink} size={8} />
                  <span className="font-semibold text-ink">{sourceLabel(series.source)}</span>
                  <span className="text-ink-2">· {METRIC_LABEL[series.metric] ?? series.metric}</span>
                </p>
                {series.points.length < 2 ? (
                  <p className="flex items-baseline gap-2">
                    <span className="font-mono text-2xl text-ink">{formatNumber(series.points[0]?.value ?? null)}</span>
                    <span className="text-xs text-ink-2">(cần ≥ 2 ngày để vẽ biểu đồ)</span>
                  </p>
                ) : (
                  <div className="h-40">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={series.points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                        <CartesianGrid stroke={RULE_HEX} strokeDasharray="2 4" vertical={false} />
                        <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: RULE_HEX }} />
                        <YAxis tick={AXIS_TICK} width={48} tickLine={false} axisLine={false} />
                        <Tooltip
                          contentStyle={{ border: `1px solid ${RULE_HEX}`, borderRadius: 6, fontSize: 12 }}
                          labelStyle={{ color: INK2_HEX }}
                          formatter={(v) => [formatNumber(Number(v)), METRIC_LABEL[series.metric] ?? series.metric]}
                        />
                        <Line type="monotone" dataKey="value" stroke={INK_HEX[ink]} dot={false} strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </Section>

      <Section title="Keyword liên quan">
        {detail.related.length === 0 && <p className="text-sm text-ink-2">Chưa có.</p>}
        <div className="flex flex-wrap gap-2">
          {detail.related.map((r) => (
            <Link
              key={`${r.relation}-${r.keyword_id}-${r.source}`}
              href={`/trends/${r.keyword_id}`}
              title={sourceLabel(r.source)}
              className="inline-flex items-center gap-2 rounded-full border border-rule bg-sheet px-3 py-1 text-sm text-ink transition-colors hover:border-ink-2"
            >
              <InkDot ink={sourceInk(r.source)} size={7} />
              {r.relation === "parent" ? "↑ " : ""}
              {r.keyword}
              <span className="font-mono text-xs text-ink-2">{r.score !== null ? Math.round(r.score) : "—"}</span>
            </Link>
          ))}
        </div>
      </Section>

      <Section title="Sản phẩm Etsy (shop US)">
        {!detail.is_seed && (products?.items.length ?? 0) === 0 && (
          <EmptyState
            title="Chưa có sản phẩm"
            body="Theo dõi keyword này để lấy sản phẩm Etsy từ lần quét tới."
            action={
              <Button variant="primary" onClick={() => follow(detail.keyword)}>
                + Theo dõi
              </Button>
            }
          />
        )}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {products?.items.map((p) => <ProductCard key={p.id} product={p} />)}
        </div>
      </Section>
    </div>
  );
}
