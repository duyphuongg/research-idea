"use client";

import Link from "next/link";
import { useEffect } from "react";
import WorkStatus from "@/components/WorkStatus";
import { Button, Card, EmptyState, ImageZoom, Notice, PageHeader, RegistrationMark, Section } from "@/components/ui";
import type { WorkItem } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { WORK_STATUS, WORK_STATUSES, loadWork, useWork } from "@/lib/work";

export default function WorkPage() {
  const { loaded, error, items } = useWork();
  // Titles/links of items marked elsewhere this session come from the server; refresh on open.
  useEffect(() => {
    loadWork(true);
  }, []);
  const all = [...items.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const groups = WORK_STATUSES.map((status) => ({ status, items: all.filter((i) => i.status === status) })).filter(
    (g) => g.items.length > 0,
  );

  return (
    <div>
      <PageHeader
        eyebrow="Việc của tôi"
        title="Việc của tôi"
        description="Ngách và mẫu bạn đã đánh dấu. Ngách/mẫu “Đã đăng” hoặc “Bỏ qua” sẽ không còn báo trong Tin mới."
      />

      {error && (
        <Notice
          tone="error"
          title="Không tải được dữ liệu"
          className="mb-4"
          action={
            <Button size="sm" onClick={() => loadWork(true)}>
              Thử lại
            </Button>
          }
        >
          <span className="break-all font-mono text-xs">{error}</span>
        </Notice>
      )}
      {!loaded && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {loaded && !error && all.length === 0 && (
        <EmptyState
          title="Chưa có việc nào"
          body="Chọn trạng thái (💡 Ý tưởng, 🎨 Đang thiết kế…) ở Trend Radar, Watchlist, Listing Signals hoặc trang Phân tích ngách."
        />
      )}

      <div className="space-y-8">
        {groups.map((g) => (
          <Section
            key={g.status}
            title={
              <>
                <span aria-hidden="true">{WORK_STATUS[g.status].icon}</span> {WORK_STATUS[g.status].label}
              </>
            }
            aside={<span className="font-mono">{g.items.length}</span>}
          >
            <Card padded={false} className="divide-y divide-rule">
              {g.items.map((item) => (
                <WorkRow key={`${item.subject_kind}:${item.subject_id}`} item={item} />
              ))}
            </Card>
          </Section>
        ))}
      </div>
    </div>
  );
}

function WorkRow({ item }: { item: WorkItem }) {
  const title = item.title || (item.subject_kind === "keyword" ? `Keyword #${item.subject_id}` : `Sản phẩm #${item.subject_id}`);
  return (
    <div className="flex items-start gap-3 p-3">
      {item.image_url ? (
        <ImageZoom src={item.image_url} alt={title} href={item.external_url ?? undefined} className="size-14 shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={item.image_url} alt="" loading="lazy" className="size-14 rounded-md border border-rule object-cover" />
        </ImageZoom>
      ) : (
        <span
          aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-md border border-rule bg-paper text-ink-2"
        >
          <RegistrationMark size={18} />
        </span>
      )}
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="eyebrow text-ink-2">{item.subject_kind === "keyword" ? "Ngách" : "Mẫu Etsy"}</span>
          <span className="font-mono text-xs text-ink-2">· {timeAgo(item.updated_at)}</span>
        </p>
        {item.link ? (
          <Link href={item.link} className="line-clamp-2 text-sm font-medium text-ink hover:underline">
            {title}
          </Link>
        ) : (
          <p className="line-clamp-2 text-sm font-medium text-ink">{title}</p>
        )}
        <WorkStatus kind={item.subject_kind} id={item.subject_id} title={title} withNote />
      </div>
      {item.external_url && (
        <a
          href={item.external_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs font-medium text-ink underline underline-offset-2"
        >
          Etsy ↗
        </a>
      )}
    </div>
  );
}
