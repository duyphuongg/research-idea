"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import WatchCard from "@/components/WatchCard";
import { Button, EmptyState, Notice, PageHeader } from "@/components/ui";
import { ApiError, api, type WatchItem, type WatchPage } from "@/lib/api";

export default function WatchlistPage() {
  const [data, setData] = useState<WatchPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [newKeyword, setNewKeyword] = useState("");

  const load = useCallback(
    () =>
      api
        .getWatchlist()
        .then((d) => {
          setData(d);
          setError(null);
        })
        .catch((err) => setError(String(err))),
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    const keyword = newKeyword.trim();
    if (!keyword) return;
    try {
      await api.addSeed(keyword);
      setNewKeyword("");
      setMessage(null);
      await load();
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? "Keyword đã có trong Watchlist" : String(err));
    }
  }

  async function remove(item: WatchItem) {
    if (!confirm(`Bỏ theo dõi “${item.keyword}”?`)) return;
    try {
      await api.deleteSeed(item.seed_id);
      setMessage(null);
      await load();
    } catch (err) {
      setMessage(String(err));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow={<>Watchlist{data?.date && <span className="font-mono">· {data.date}</span>}</>}
        title="Ngách đang theo dõi"
        description="Mỗi keyword: ngách con tìm được và mẫu Etsy đang bứt phá. Thêm keyword để app quét thêm ngách."
        actions={
          <form onSubmit={add} className="flex gap-2">
            <input
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              placeholder="vd: volleyball mom"
              aria-label="Keyword mới"
              className="h-9 min-w-0 flex-1 rounded-md border border-rule bg-sheet px-3 text-sm text-ink placeholder:text-ink-2/70 hover:border-ink-2 sm:w-64 sm:flex-none"
            />
            <Button type="submit" variant="primary">
              Theo dõi
            </Button>
          </form>
        }
      />

      {message && (
        <Notice tone="warn" className="mb-4">
          {message}
        </Notice>
      )}
      {error && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{error}</span>
        </Notice>
      )}
      {!data && !error && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {data && data.items.length === 0 && (
        <EmptyState
          title="Chưa theo dõi keyword nào"
          body="Thêm một ngách, ví dụ football mom hoặc pickleball. Dữ liệu có sau lần quét kế tiếp (8:00 hoặc 20:00)."
        />
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.items.map((item) => <WatchCard key={item.seed_id} item={item} onRemove={remove} />)}
      </div>
    </div>
  );
}
