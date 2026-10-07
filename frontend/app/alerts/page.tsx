"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button, Card, EmptyState, ImageZoom, Notice, PageHeader, RegistrationMark, Section } from "@/components/ui";
import { api, ApiError, type AlertItem, type AlertKind, type TelegramStatus } from "@/lib/api";

const KIND: Record<AlertKind, { icon: string; label: string }> = {
  niche: { icon: "🚀", label: "Ngách bứt phá" },
  listing: { icon: "🔥", label: "Mẫu Etsy tăng mạnh" },
  hot_product: { icon: "⭐", label: "Sản phẩm hot" },
  amazon: { icon: "🛒", label: "Amazon mới vào top" },
};

function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

function errorText(err: unknown): string {
  return err instanceof ApiError || err instanceof Error ? err.message : String(err);
}

function externalLabel(url: string): string {
  return url.includes("amazon") ? "Amazon ↗" : "Etsy ↗";
}

export default function AlertsPage() {
  const [items, setItems] = useState<AlertItem[] | null>(null);
  const [unreadIds, setUnreadIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listAlerts()
      .then(async (page) => {
        if (cancelled) return;
        setUnreadIds(new Set(page.items.filter((a) => !a.read).map((a) => a.id)));
        setItems(page.items);
        if (page.unread > 0 || page.items.some((a) => !a.read)) {
          await api.markAlertsRead();
          window.dispatchEvent(new Event("alerts:read"));
        }
      })
      .catch((err) => !cancelled && setError(errorText(err)));
    api
      .telegramStatus()
      .then((t) => !cancelled && setTelegram(t))
      .catch(() => !cancelled && setTelegram(null));
    return () => {
      cancelled = true;
    };
  }, []);

  async function sendTest() {
    setTesting(true);
    setTestResult(null);
    try {
      await api.testTelegram();
      setTestResult({ ok: true, text: "Đã gửi — kiểm tra Telegram" });
    } catch (err) {
      setTestResult({ ok: false, text: errorText(err) });
    } finally {
      setTesting(false);
    }
  }

  const groups: { date: string; items: AlertItem[] }[] = [];
  for (const a of items ?? []) {
    const last = groups[groups.length - 1];
    if (last && last.date === a.scan_date) last.items.push(a);
    else groups.push({ date: a.scan_date, items: [a] });
  }

  return (
    <div>
      <PageHeader
        eyebrow="Tin mới"
        title="Tin mới"
        description="Phát hiện sau mỗi lần quét (8:00 và 20:00): ngách bứt phá, mẫu Etsy tăng mạnh, sản phẩm hot, Amazon mới vào top."
      />

      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h2 className="eyebrow text-ink-2">Telegram</h2>
          {telegram?.configured ? (
            <>
              <span className="inline-flex items-center gap-2 text-sm text-ink">
                <span aria-hidden="true" className="inline-block size-2 rounded-full bg-go" />
                Đã kết nối
              </span>
              <Button size="sm" onClick={sendTest} disabled={testing}>
                {testing ? "Đang gửi…" : "Gửi tin thử"}
              </Button>
            </>
          ) : telegram ? (
            <Notice tone="info" className="min-w-0 flex-1 basis-72">
              Chưa kết nối Telegram. Trên máy Mac, chạy <code className="font-mono text-xs">make telegram-setup</code> rồi làm
              theo hướng dẫn.
            </Notice>
          ) : (
            <span className="text-sm text-ink-2">Đang kiểm tra…</span>
          )}
        </div>
        {testResult && (
          <Notice tone={testResult.ok ? "info" : "error"} className="mt-3">
            {testResult.text}
          </Notice>
        )}
      </Card>

      {error && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{error}</span>
        </Notice>
      )}
      {!error && items === null && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {items && items.length === 0 && (
        <EmptyState
          title="Chưa có tin nào"
          body="Tin xuất hiện sau lần quét kế tiếp khi có ngách hoặc sản phẩm vượt ngưỡng (chỉnh trong backend/config/alerts.yaml)."
        />
      )}

      <div className="space-y-6">
        {groups.map((g) => (
          <Section key={g.date} title={<span className="font-mono">{formatDate(g.date)}</span>}>
            <Card padded={false} className="divide-y divide-rule overflow-hidden">
              {g.items.map((a) => (
                <AlertRow key={a.id} alert={a} unread={unreadIds.has(a.id)} />
              ))}
            </Card>
          </Section>
        ))}
      </div>
    </div>
  );
}

function AlertRow({ alert: a, unread }: { alert: AlertItem; unread: boolean }) {
  const kind = KIND[a.kind];
  return (
    <div className={`flex items-start gap-3 p-3 ${unread ? "border-l-[3px] border-cyan" : ""}`}>
      <span aria-hidden="true" className="w-6 shrink-0 pt-0.5 text-center text-lg leading-none">
        {kind.icon}
      </span>
      <span className="sr-only">{kind.label}</span>
      {a.image_url ? (
        <ImageZoom src={a.image_url} alt={a.title} href={a.external_url ?? undefined} className="size-14 shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={a.image_url} alt="" loading="lazy" className="size-14 rounded-md border border-rule object-cover" />
        </ImageZoom>
      ) : (
        <span
          aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-md border border-rule bg-paper text-ink-2"
        >
          <RegistrationMark size={18} />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="eyebrow text-ink-2">{kind.label}</span>
          {a.watch_keyword && (
            <span className="rounded-full border border-rule bg-paper px-2 py-0.5 text-xs text-ink">{a.watch_keyword}</span>
          )}
        </p>
        <Link href={a.link} className="line-clamp-2 text-sm font-medium text-ink hover:underline">
          {a.title}
        </Link>
        <p className="mt-0.5 font-mono text-xs text-ink-2">{a.reason}</p>
      </div>
      {a.external_url && (
        <a
          href={a.external_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs font-medium text-ink underline underline-offset-2"
        >
          {externalLabel(a.external_url)}
        </a>
      )}
    </div>
  );
}
