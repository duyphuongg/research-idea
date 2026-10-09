"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import CompetitionBadge from "@/components/CompetitionBadge";
import { TAG_CHIP } from "@/components/SignalCard";
import WorkStatus from "@/components/WorkStatus";
import { Button, ButtonLink, Card, EmptyState, Notice, PageHeader, Section, Tabs } from "@/components/ui";
import { ApiError, api, type NicheReport, type ProductType, type WatchItem } from "@/lib/api";
import { formatInt, formatNumber, formatPrice } from "@/lib/format";

const TYPE_LABEL: Record<ProductType | "all", string> = {
  all: "Tất cả",
  tshirt: "Áo thun",
  sweatshirt: "Sweatshirt",
  hoodie: "Hoodie",
};
const TYPES: ProductType[] = ["tshirt", "sweatshirt", "hoodie"];
const TYPE_TABS = (["all", ...TYPES] as const).map((value) => ({ value, label: TYPE_LABEL[value] }));

const TH = "eyebrow whitespace-nowrap px-3 py-2 text-left font-bold text-ink-2";
const TD = "px-3 py-2 align-middle";

type Result = { key: string; data?: NicheReport; error?: string; notFound?: boolean };

/** Copy text; falls back to execCommand where the Clipboard API is missing (plain http over Tailscale). */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall back below
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}

/** "hockey mom" → "#hockeymom" (spaces and punctuation removed). */
function hashtag(tag: string): string {
  return `#${tag.replace(/[^\p{L}\p{N}]/gu, "")}`;
}

function CopyButton({ text, label, variant = "secondary" }: { text: string; label: string; variant?: "secondary" | "ghost" }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const t = setTimeout(() => setState("idle"), 1600);
    return () => clearTimeout(t);
  }, [state]);
  return (
    <Button size="sm" variant={variant} onClick={async () => setState((await copyText(text)) ? "ok" : "fail")}>
      <span aria-live="polite">{state === "ok" ? "✓ Đã copy" : state === "fail" ? "Không copy được" : label}</span>
    </Button>
  );
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

export default function NichePage() {
  return (
    <Suspense fallback={null}>
      <NicheView />
    </Suspense>
  );
}

function NicheView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const keyword = params.get("keyword")?.trim() ?? "";
  const typeParam = params.get("product_type");
  const productType = TYPES.find((t) => t === typeParam);

  const [draft, setDraft] = useState(keyword);
  const [watch, setWatch] = useState<WatchItem[] | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [tick, setTick] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${keyword}|${productType ?? ""}#${tick}`;
  const loading = keyword !== "" && result?.key !== key;

  // Keep the input in step with the URL (back/forward, chip clicks).
  const [seenKeyword, setSeenKeyword] = useState(keyword);
  if (seenKeyword !== keyword) {
    setSeenKeyword(keyword);
    setDraft(keyword);
    setMessage(null);
  }

  useEffect(() => {
    api
      .getWatchlist()
      .then((w) => setWatch(w.items))
      .catch(() => setWatch([]));
  }, []);

  useEffect(() => {
    if (!keyword) return;
    let cancelled = false;
    api
      .getNiche(keyword, productType)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch(
        (err) =>
          !cancelled &&
          setResult(err instanceof ApiError && err.status === 404 ? { key, notFound: true } : { key, error: String(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [key, keyword, productType]);

  function go(next: { keyword?: string; type?: ProductType }, replace = false) {
    const q = new URLSearchParams();
    if (next.keyword) q.set("keyword", next.keyword);
    if (next.type) q.set("product_type", next.type);
    const url = q.toString() ? `${pathname}?${q}` : pathname;
    if (replace) router.replace(url, { scroll: false });
    else router.push(url);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const k = draft.trim().toLowerCase();
    if (k) go({ keyword: k, type: productType });
  }

  async function follow() {
    try {
      await api.addSeed(keyword);
      setMessage(`Đã thêm “${keyword}” vào Watchlist — lần quét tới sẽ lấy sản phẩm Etsy cho ngách này.`);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `“${keyword}” đã có trong Watchlist.` : String(err));
    }
  }

  // While switching the type tab, keep showing the previous report of the same keyword.
  const data = result?.key.startsWith(`${keyword}|`) ? result.data : undefined;
  const watched = watch?.some((w) => w.keyword.toLowerCase() === keyword.toLowerCase()) ?? false;

  return (
    <div>
      <PageHeader
        eyebrow="Phân tích ngách"
        title={keyword || "Phân tích ngách"}
        description="Cạnh tranh, giá, tag hay dùng và bộ 13 tag gợi ý — dựa trên sản phẩm Etsy (shop US) 30 ngày gần nhất."
        actions={
          <form onSubmit={submit} className="flex w-full gap-2 sm:w-auto">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="vd: hockey mom"
              aria-label="Keyword cần phân tích"
              className="h-9 min-w-0 flex-1 rounded-md border border-rule bg-sheet px-3 text-sm text-ink placeholder:text-ink-2/70 hover:border-ink-2 sm:w-64 sm:flex-none"
            />
            <Button type="submit" variant="primary">
              Phân tích
            </Button>
          </form>
        }
      />

      {!keyword && (
        <Card className="space-y-3">
          <p className="text-sm text-ink">Nhập một keyword, hoặc chọn ngách trong Watchlist:</p>
          {watch === null ? (
            <p className="text-sm text-ink-2">Đang tải…</p>
          ) : watch.length === 0 ? (
            <p className="text-sm text-ink-2">
              Watchlist trống — <Link href="/watchlist" className="text-ink underline underline-offset-2">thêm keyword</Link>{" "}
              để app quét sản phẩm.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {watch.map((w) => (
                <Link
                  key={w.seed_id}
                  href={`/niche?keyword=${encodeURIComponent(w.keyword)}`}
                  className={`${TAG_CHIP} text-[13px] leading-5 text-ink hover:border-ink-2`}
                >
                  {w.keyword}
                </Link>
              ))}
            </div>
          )}
        </Card>
      )}

      {message && (
        <Notice tone="info" className="mb-4">
          {message}
        </Notice>
      )}
      {keyword && loading && !data && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {keyword && !loading && result?.error && (
        <Notice
          tone="error"
          title="Không tải được dữ liệu"
          className="mb-4"
          action={
            <Button size="sm" onClick={() => setTick((t) => t + 1)}>
              Thử lại
            </Button>
          }
        >
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {keyword && !loading && result?.notFound && (
        <EmptyState title="Không tìm thấy ngách" body="Thử một keyword khác, ví dụ cụm 2–3 từ như “hockey mom”." />
      )}

      {data && (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <span className="text-ink-2">
              <span className="font-mono font-medium text-ink">{formatInt(data.listings)}</span> sản phẩm ·{" "}
              <span className="font-mono font-medium text-ink">{formatInt(data.breakouts)}</span> đang bứt phá
              {productType && <> · chỉ {TYPE_LABEL[productType]}</>}
            </span>
            {data.keyword_id !== null && <WorkStatus kind="keyword" id={data.keyword_id} title={data.keyword} withNote />}
            <span className="flex flex-wrap gap-2 sm:ml-auto">
              {data.keyword_id !== null && (
                <ButtonLink size="sm" href={`/trends/${data.keyword_id}`}>
                  Xem xu hướng
                </ButtonLink>
              )}
              <ButtonLink size="sm" href={`/signals?keyword=${encodeURIComponent(data.keyword)}&status=all`}>
                Xem listing
              </ButtonLink>
              {watch !== null && !watched && (
                <Button size="sm" onClick={follow}>
                  + Theo dõi
                </Button>
              )}
            </span>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Competition data={data} />
            <Prices data={data} />
          </div>

          <div className={`mt-8 grid gap-6 transition-opacity lg:grid-cols-[3fr_2fr] ${loading ? "opacity-60" : ""}`}>
            <TopTags
              data={data}
              type={productType ?? "all"}
              onType={(t) => go({ keyword, type: t === "all" ? undefined : t }, true)}
            />
            <div className="space-y-6">
              <TagSet tags={data.generated.tags} />
              <TitlePhrases phrases={data.generated.title_phrases} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Competition({ data }: { data: NicheReport }) {
  const { counts, level, date } = data.competition;
  const known = TYPES.some((t) => counts[t] !== undefined && counts[t] !== null);
  return (
    <Section
      title="Cạnh tranh"
      aside={
        <>
          {level && <CompetitionBadge level={level} />}
          {date && <span className="font-mono">{formatDate(date)}</span>}
        </>
      }
    >
      {known ? (
        <Card>
          <div className="grid grid-cols-3 gap-3">
            {TYPES.map((t) => (
              <div key={t} className="min-w-0">
                <p className="eyebrow text-[10px] leading-4 text-ink-2">{TYPE_LABEL[t]}</p>
                <p className="font-mono text-lg font-medium leading-7 text-ink" title={formatInt(counts[t] ?? null)}>
                  {formatNumber(counts[t] ?? null)}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 border-t border-rule pt-2 text-xs leading-5 text-ink-2">
            Tổng listing Etsy khi tìm “{data.keyword} shirt / sweatshirt / hoodie”. Mức: Thấp &lt; 10k, Vừa &lt; 50k, Cao ≥ 50k
            (theo áo thun).
          </p>
        </Card>
      ) : (
        <Card className="text-sm text-ink-2">Chưa có dữ liệu — có sau lần quét tới.</Card>
      )}
    </Section>
  );
}

function Prices({ data }: { data: NicheReport }) {
  return (
    <Section title="Giá tham khảo" aside={<span>USD · Etsy shop US</span>}>
      {data.prices.length === 0 ? (
        <Card className="text-sm text-ink-2">Chưa có giá — chưa có sản phẩm trong ngách.</Card>
      ) : (
        <Card padded={false} className="overflow-x-auto">
          <table className="w-full min-w-[440px] text-sm">
            <thead>
              <tr className="border-b border-rule">
                <th className={TH}>Loại</th>
                <th className={`${TH} text-right`}>SL</th>
                <th className={`${TH} text-right`}>Thấp (p25)</th>
                <th className={`${TH} text-right`}>Giữa</th>
                <th className={`${TH} text-right`}>Cao (p75)</th>
                <th className={`${TH} text-right`}>Mẫu bứt phá</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {data.prices.map((p) => (
                <tr
                  key={p.product_type}
                  className={`border-b border-rule last:border-0 ${p.product_type === "all" ? "bg-paper/60 font-medium" : ""}`}
                >
                  <td className={`${TD} font-sans`}>{TYPE_LABEL[p.product_type] ?? p.product_type}</td>
                  <td className={`${TD} text-right text-ink-2`}>{formatInt(p.count)}</td>
                  <td className={`${TD} text-right`}>{formatPrice(p.p25, "USD")}</td>
                  <td className={`${TD} text-right font-semibold`}>{formatPrice(p.median, "USD")}</td>
                  <td className={`${TD} text-right`}>{formatPrice(p.p75, "USD")}</td>
                  <td className={`${TD} text-right`}>{formatPrice(p.breakout_median, "USD")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </Section>
  );
}

function TopTags({
  data,
  type,
  onType,
}: {
  data: NicheReport;
  type: ProductType | "all";
  onType: (t: ProductType | "all") => void;
}) {
  return (
    <Section title="Top tag" aside={<span>Tag hay dùng nhất trong ngách</span>}>
      <Tabs label="Loại áo" items={TYPE_TABS} value={type} onChange={onType} />
      {data.tags.length === 0 ? (
        <Card className="text-sm text-ink-2">Chưa có tag — chưa có sản phẩm{type !== "all" && ` ${TYPE_LABEL[type]}`} trong ngách.</Card>
      ) : (
        <Card padded={false} className="overflow-x-auto">
          <table className="w-full min-w-[460px] text-sm">
            <thead>
              <tr className="border-b border-rule">
                <th className={TH}>Tag</th>
                <th className={`${TH} text-right`}>Listing</th>
                <th className={`${TH} text-right`}>Bứt phá</th>
                <th className={`${TH} text-right`}>Tỷ lệ</th>
              </tr>
            </thead>
            <tbody>
              {data.tags.map((t) => (
                <tr key={t.tag} className="border-b border-rule last:border-0 hover:bg-paper/60">
                  <td className={TD}>
                    <span className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/niche?keyword=${encodeURIComponent(t.tag)}`}
                        className="text-ink underline-offset-2 hover:underline"
                        title="Phân tích ngách này"
                      >
                        {t.tag}
                      </Link>
                      {t.rising && (
                        <span
                          className="whitespace-nowrap rounded-full border border-magenta/40 bg-magenta/10 px-1.5 text-[11px] font-medium leading-4 text-ink"
                          title={`Mẫu bứt phá dùng tag này nhiều gấp ${t.lift.toFixed(1)} lần bình thường`}
                        >
                          🔥 nổi
                        </span>
                      )}
                    </span>
                  </td>
                  <td className={`${TD} text-right font-mono`}>{formatInt(t.listings)}</td>
                  <td className={`${TD} text-right font-mono ${t.breakouts > 0 ? "text-ink" : "text-ink-2"}`}>
                    {formatInt(t.breakouts)}
                  </td>
                  <td className={`${TD} text-right font-mono text-ink-2`}>{Math.round(t.share * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </Section>
  );
}

function TagSet({ tags }: { tags: string[] }) {
  return (
    <Section title="Bộ 13 tag" aside={<span className="font-mono">{tags.length}/13</span>}>
      {tags.length === 0 ? (
        <Card className="text-sm text-ink-2">Chưa đủ dữ liệu để gợi ý tag.</Card>
      ) : (
        <Card className="space-y-3">
          <ol className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <li
                key={t}
                className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-sheet px-2.5 py-0.5 text-[13px] leading-5 text-ink"
              >
                {t}
                <span className={`font-mono text-[11px] ${t.length > 20 ? "text-stop" : "text-ink-2"}`}>{t.length}</span>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2 border-t border-rule pt-3">
            <CopyButton text={tags.join(", ")} label="Copy tag" />
            <CopyButton text={tags.map(hashtag).join(" ")} label="Copy #hashtag" />
          </div>
          <p className="text-xs leading-5 text-ink-2">Mỗi tag ≤ 20 ký tự (giới hạn Etsy). Số bên cạnh = số ký tự.</p>
        </Card>
      )}
    </Section>
  );
}

function TitlePhrases({ phrases }: { phrases: string[] }) {
  return (
    <Section title="Gợi ý cụm từ cho tiêu đề">
      {phrases.length === 0 ? (
        <Card className="text-sm text-ink-2">Chưa có gợi ý.</Card>
      ) : (
        <Card padded={false} className="divide-y divide-rule">
          {phrases.map((p) => (
            <div key={p} className="flex items-center justify-between gap-3 px-3 py-1.5">
              <span className="min-w-0 break-words text-sm text-ink">{p}</span>
              <CopyButton text={p} label="Copy" variant="ghost" />
            </div>
          ))}
        </Card>
      )}
    </Section>
  );
}
