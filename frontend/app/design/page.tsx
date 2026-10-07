"use client";

import { useState } from "react";
import Sparkline from "@/components/Sparkline";
import {
  Button,
  ButtonLink,
  Card,
  Checkbox,
  Delta,
  EmptyState,
  HalftoneMeter,
  InkDot,
  Notice,
  PageHeader,
  RegistrationMark,
  Section,
  Select,
  SourceChip,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import type { CalendarPhase, ScanStatus, SignalStatus } from "@/lib/api";
import { SOURCE_INK } from "@/lib/sources";

const COLORS = [
  { token: "paper", hex: "#EEF1F4", use: "nền trang" },
  { token: "sheet", hex: "#FFFFFF", use: "thẻ, bảng, panel" },
  { token: "ink", hex: "#15171E", use: "chữ chính, sidebar, nút chính" },
  { token: "ink-2", hex: "#5B6170", use: "chữ phụ" },
  { token: "rule", hex: "#D5DAE1", use: "viền 1px" },
  { token: "cyan", hex: "#0096B7", use: "Etsy" },
  { token: "magenta", hex: "#C8246E", use: "Amazon, bản quyền" },
  { token: "yellow", hex: "#E3A600", use: "Google" },
  { token: "go", hex: "#1F8A5B", use: "tăng, ok" },
  { token: "stop", hex: "#C8371D", use: "giảm, lỗi" },
];

const SWATCH: Record<string, string> = {
  paper: "bg-paper",
  sheet: "bg-sheet",
  ink: "bg-ink",
  "ink-2": "bg-ink-2",
  rule: "bg-rule",
  cyan: "bg-cyan",
  magenta: "bg-magenta",
  yellow: "bg-yellow",
  go: "bg-go",
  stop: "bg-stop",
};

const SCAN: ScanStatus[] = ["ok", "partial", "failed", "running"];
const SIGNAL: SignalStatus[] = ["super_breakout", "steady_grower", "graduated", "calibrating", "normal", "gone"];
const PHASE: CalendarPhase[] = ["upcoming", "design", "launch", "push", "cutoff", "peak", "after"];

type Tab = "signals" | "all" | "calibrating";

export default function DesignPage() {
  const [tab, setTab] = useState<Tab>("signals");
  const [checked, setChecked] = useState(true);

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow="Design system · Press Room"
        title="Bảng mẫu in"
        description="Mọi token và component dùng chung. Trang này không nằm trong menu."
        actions={
          <>
            <Button variant="secondary">Xuất CSV</Button>
            <Button variant="primary">Quét ngay</Button>
          </>
        }
      />

      <Section title="Màu (tokens)" aside={<span className="font-mono">@theme · app/globals.css</span>}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {COLORS.map((c) => (
            <Card key={c.token} padded={false} className="overflow-hidden">
              <div className={`h-14 border-b border-rule ${SWATCH[c.token]}`} />
              <div className="p-2.5">
                <p className="font-semibold">{c.token}</p>
                <p className="font-mono text-xs text-ink-2">{c.hex}</p>
                <p className="text-xs text-ink-2">{c.use}</p>
              </div>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Chữ">
        <Card className="space-y-4">
          <div>
            <p className="eyebrow flex items-center gap-1.5 text-ink-2">
              <RegistrationMark className="text-ink" /> Eyebrow · Archivo 11px · 0.08em
            </p>
            <p className="font-wide font-display text-[28px] font-extrabold leading-tight">Ngách đang lên — 28px Archivo 800</p>
            <p className="text-[18px] font-semibold">Tiêu đề section — 18px Be Vietnam Pro 600</p>
            <p>Văn bản giao diện 14px: Theo dõi, Quét ngay, Ẩn sản phẩm có bản quyền.</p>
            <p className="text-xs text-ink-2">Chữ nhỏ 12px, ink-2 cho thông tin phụ.</p>
          </div>
          <div className="flex flex-wrap items-baseline gap-6">
            <span className="font-mono text-[32px] font-medium leading-none">87.4</span>
            <span className="font-mono">B0CX12ABCD · 07/10/2026 · 1,234</span>
          </div>
        </Card>
      </Section>

      <Section title="Thước halftone" aside="HalftoneMeter value 0..1 · size sm|md">
        <Card className="grid gap-3 sm:grid-cols-2">
          {[0, 0.12, 0.35, 0.5, 0.74, 0.96].map((v) => (
            <div key={v} className="flex items-center gap-4">
              <span className="w-10 font-mono text-xs text-ink-2">{v}</span>
              <HalftoneMeter value={v} label={String(Math.round(v * 100))} />
              <HalftoneMeter value={v} size="sm" />
            </div>
          ))}
          <div className="flex items-center gap-4">
            <span className="w-10 font-mono text-xs text-ink-2">null</span>
            <HalftoneMeter value={null} />
          </div>
        </Card>
      </Section>

      <Section title="Nguồn & mực">
        <Card className="flex flex-wrap items-center gap-2">
          {Object.keys(SOURCE_INK).map((s) => (
            <SourceChip key={s} source={s} />
          ))}
          <span className="ml-2 flex items-center gap-1.5">
            <InkDot ink="cyan" />
            <InkDot ink="magenta" />
            <InkDot ink="yellow" />
            <InkDot ink="ink" />
            <InkDot ink="cyan" shape="square" size={10} />
          </span>
        </Card>
      </Section>

      <Section title="Số liệu">
        <Card className="flex flex-wrap items-center gap-6">
          <Delta value={0.42} />
          <Delta value={-0.18} />
          <Delta value={0} />
          <Delta value={null} />
          <Delta value={12} ratio={false} unit="" />
          <Delta value={-3} ratio={false} unit="" />
          <Sparkline values={[2, 3, 3, 5, 4, 6, 8, 9]} />
          <Sparkline values={[9, 8, 8, 6, 7, 4, 3, 2]} />
          <Sparkline values={[1]} />
        </Card>
      </Section>

      <Section title="Trạng thái">
        <Card className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow w-28 text-ink-2">Quét</span>
            {SCAN.map((s) => (
              <StatusBadge key={s} kind="scan" status={s} />
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow w-28 text-ink-2">Listing</span>
            {SIGNAL.map((s) => (
              <StatusBadge key={s} kind="signal" status={s} />
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow w-28 text-ink-2">Lịch</span>
            {PHASE.map((s) => (
              <StatusBadge key={s} kind="phase" status={s} />
            ))}
          </div>
        </Card>
      </Section>

      <Section title="Điều khiển">
        <Card className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary">Theo dõi</Button>
            <Button variant="secondary">Bỏ lọc</Button>
            <Button variant="ghost">Xem thêm</Button>
            <Button variant="primary" disabled>
              Đang quét…
            </Button>
            <Button variant="primary" size="sm">
              Theo dõi
            </Button>
            <Button variant="secondary" size="sm">
              Ẩn
            </Button>
            <ButtonLink href="/" variant="ghost" size="sm">
              Về Trend Radar →
            </ButtonLink>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <Select label="Loại áo" defaultValue="tshirt">
              <option value="tshirt">T-shirt</option>
              <option value="sweatshirt">Sweatshirt</option>
              <option value="hoodie">Hoodie</option>
            </Select>
            <Select size="sm" aria-label="Sắp xếp" defaultValue="velocity">
              <option value="velocity">Bán nhanh</option>
              <option value="reviews">Nhiều review</option>
            </Select>
            <Checkbox label="Ẩn sản phẩm có bản quyền" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          </div>
          <Tabs<Tab>
            label="Trạng thái listing"
            value={tab}
            onChange={setTab}
            items={[
              { value: "signals", label: "Tín hiệu", count: 42 },
              { value: "all", label: "Tất cả", count: 1280 },
              { value: "calibrating", label: "Đang hiệu chỉnh", count: 7 },
            ]}
          />
        </Card>
      </Section>

      <Section title="Thông báo">
        <div className="space-y-2">
          <Notice tone="info" title="Dữ liệu Amazon lấy qua proxy">
            Kết quả có thể chậm hơn vài phút so với trang gốc.
          </Notice>
          <Notice tone="warn" action={<Button size="sm">Cài đặt</Button>}>
            Etsy: chưa cấu hình API key.
          </Notice>
          <Notice tone="error" title="Lỗi lần quét gần nhất">
            Google xu hướng ngày — 3 giờ trước.
          </Notice>
        </div>
      </Section>

      <Section title="Trạng thái rỗng">
        <EmptyState
          title="Chưa có ngách nào"
          body="Thêm keyword vào watchlist rồi bấm Quét ngay để có dữ liệu đầu tiên."
          action={<ButtonLink href="/settings" variant="primary">Mở Cài đặt</ButtonLink>}
        />
      </Section>

      <Section title="Bảng mẫu" aside="cuộn ngang trong khung riêng">
        <Card padded={false} className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-rule text-left">
                <th className="eyebrow px-4 py-2 text-ink-2">#</th>
                <th className="eyebrow px-4 py-2 text-ink-2">Keyword</th>
                <th className="eyebrow px-4 py-2 text-ink-2">Điểm</th>
                <th className="eyebrow px-4 py-2 text-ink-2">Tăng trưởng</th>
                <th className="eyebrow px-4 py-2 text-ink-2">Nguồn</th>
                <th className="eyebrow px-4 py-2 text-ink-2">30 ngày</th>
              </tr>
            </thead>
            <tbody>
              {[
                { k: "retro halloween", s: 0.87, g: 0.64, src: "etsy", v: [1, 2, 2, 4, 6, 9] },
                { k: "teacher fall", s: 0.62, g: 0.12, src: "google_daily", v: [3, 3, 4, 4, 5, 5] },
                { k: "christmas family", s: 0.41, g: -0.08, src: "amazon", v: [6, 5, 5, 4, 4, 3] },
              ].map((r, i) => (
                <tr key={r.k} className="border-b border-rule last:border-0">
                  <td className="px-4 py-2.5 font-mono text-ink-2">{i + 1}</td>
                  <td className="px-4 py-2.5 font-semibold">{r.k}</td>
                  <td className="px-4 py-2.5">
                    <HalftoneMeter value={r.s} size="sm" label={String(Math.round(r.s * 100))} />
                  </td>
                  <td className="px-4 py-2.5">
                    <Delta value={r.g} />
                  </td>
                  <td className="px-4 py-2.5">
                    <SourceChip source={r.src} />
                  </td>
                  <td className="px-4 py-2.5">
                    <Sparkline values={r.v} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </Section>
    </div>
  );
}
