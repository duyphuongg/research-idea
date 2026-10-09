"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SalesDelta, ShopIcon } from "@/components/ShopBits";
import { Button, ButtonLink, Card, EmptyState, Notice, Section } from "@/components/ui";
import { api, type Shop } from "@/lib/api";
import { formatInt } from "@/lib/format";

const TH_BASE = "eyebrow whitespace-nowrap px-3 py-2 font-bold text-ink-2";
const TH = `${TH_BASE} text-right`;
const TD = "whitespace-nowrap px-3 py-2 text-right font-mono text-[13px] text-ink";

/** Watchlist section: shops the user follows, newest orders first. */
export default function WatchedShops({ className = "" }: { className?: string }) {
  const [shops, setShops] = useState<Shop[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      api
        .listShops({ watched: true, sort: "sales_7d", limit: 200 })
        .then((page) => {
          setShops(page.items);
          setError(null);
        })
        .catch((err) => setError(String(err))),
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function unwatch(shop: Shop) {
    if (!confirm(`Bỏ theo dõi shop “${shop.name}”?`)) return;
    try {
      await api.unwatchShop(shop.id);
      setShops((list) => list?.filter((s) => s.id !== shop.id) ?? null);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <Section
      id="watched-shops"
      className={className}
      title="Shop đang theo dõi"
      aside={
        <ButtonLink size="sm" href="/shops">
          Mở Shop Explorer
        </ButtonLink>
      }
    >
      {error && (
        <Notice tone="error" title="Không tải được shop">
          <span className="break-all font-mono text-xs">{error}</span>
        </Notice>
      )}
      {!shops && !error && <p className="py-2 text-sm text-ink-2">Đang tải…</p>}
      {shops && shops.length === 0 && <EmptyState title="Chưa theo dõi shop nào — bấm ☆ ở trang Shop." />}
      {shops && shops.length > 0 && (
        <Card padded={false} className="relative overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead className="border-b border-rule">
              <tr>
                <th scope="col" className={`${TH_BASE} sticky left-0 z-10 bg-sheet shadow-[1px_0_0_var(--color-rule)] text-left`}>
                  Shop
                </th>
                <th scope="col" className={`${TH} text-ink`}>
                  +Đơn 7 ngày
                </th>
                <th scope="col" className={TH}>
                  +Đơn 30 ngày
                </th>
                <th scope="col" className={TH}>
                  Tổng đơn
                </th>
                <th scope="col" className={TH}>
                  +Yêu thích 7 ngày
                </th>
                <th scope="col" className={TH}>
                  <span className="sr-only">Bỏ theo dõi</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {shops.map((s) => (
                <tr key={s.id} className="group hover:bg-paper/50">
                  <th scope="row" className="sticky left-0 z-10 bg-sheet shadow-[1px_0_0_var(--color-rule)] px-3 py-2 text-left font-normal group-hover:bg-paper">
                    <span className="flex max-w-[150px] items-center sm:max-w-[220px] gap-2">
                      <ShopIcon shop={s} />
                      <Link href={`/shops/${s.id}`} className="truncate font-medium text-ink hover:underline">
                        {s.name}
                      </Link>
                    </span>
                  </th>
                  <td className={`${TD} font-medium`}>
                    <SalesDelta delta={s.sales_7d} window={7} />
                  </td>
                  <td className={TD}>
                    <SalesDelta delta={s.sales_30d} window={30} />
                  </td>
                  <td className={TD}>{formatInt(s.sold_count)}</td>
                  <td className={TD}>
                    <SalesDelta delta={s.favorers_7d} window={7} />
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <Button size="sm" variant="ghost" onClick={() => unwatch(s)}>
                      Bỏ theo dõi
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </Section>
  );
}
