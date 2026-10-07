"use client";

import { useEffect, useState } from "react";
import { api, type ScanStatus, type SourceHealth } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { INK_LETTER, type Ink, sourceInk, sourceLabel } from "@/lib/sources";
import InkDot from "./InkDot";

// Plate squares on the dark sidebar; letter colours chosen for contrast on each ink.
const PLATE: Record<Ink, string> = {
  cyan: "bg-cyan text-ink",
  magenta: "bg-magenta text-white",
  yellow: "bg-yellow text-ink",
  ink: "bg-white/15 text-white",
};

type Result = { data?: SourceHealth[]; error?: string };

const MARK: Record<ScanStatus, { glyph: string; text: string; cls: string }> = {
  ok: { glyph: "✓", text: "thành công", cls: "bg-go text-white" },
  partial: { glyph: "!", text: "một phần", cls: "bg-yellow text-ink" },
  failed: { glyph: "✕", text: "lỗi", cls: "bg-stop text-white" },
  running: { glyph: "…", text: "đang quét", cls: "bg-white/20 text-white" },
};

/** "Bản in hôm nay" — latest scan per source, printed as C/M/Y/K plates. Designed for the dark sidebar. */
export default function PressStatus() {
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .sourceHealth()
      .then((data) => alive && setResult({ data }))
      .catch((err) => alive && setResult({ error: String(err) }));
    return () => {
      alive = false;
    };
  }, []);

  const sources = (result?.data ?? []).filter((s) => s.enabled);

  return (
    <div className="border-t border-white/10 px-5 py-4">
      <div className="flex items-center justify-between">
        <p className="eyebrow text-white/70">Bản in hôm nay</p>
        <span className="flex gap-0.5" aria-hidden="true">
          <InkDot ink="cyan" shape="square" size={7} />
          <InkDot ink="magenta" shape="square" size={7} />
          <InkDot ink="yellow" shape="square" size={7} />
          <InkDot ink="ink" shape="square" size={7} className="ring-1 ring-white/50" />
        </span>
      </div>

      {result === null && <p className="mt-2 text-xs text-white/60">Đang tải…</p>}
      {result?.error && <p className="mt-2 text-xs text-white/70">Không kết nối được backend.</p>}
      {result?.data && sources.length === 0 && <p className="mt-2 text-xs text-white/60">Chưa bật nguồn nào.</p>}

      {sources.length > 0 && (
        <ul className="mt-3 space-y-2">
          {sources.map((s) => {
            const ink = sourceInk(s.name);
            const mark = s.last_status ? MARK[s.last_status] : null;
            return (
              <li key={s.name} className="flex items-start gap-2 text-xs">
                <span
                  className={`mt-px inline-flex size-4 shrink-0 items-center justify-center rounded-[2px] font-mono text-[9px] font-medium ${PLATE[ink]}`}
                  aria-hidden="true"
                >
                  {INK_LETTER[ink]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate leading-[18px] text-white/90">{sourceLabel(s.name)}</span>
                  <span className="block font-mono text-[11px] leading-4 text-white/60">
                    {!s.configured ? "chưa cấu hình" : s.last_status ? timeAgo(s.last_finished_at) : "chưa quét"}
                  </span>
                </span>
                {s.configured && mark && (
                  <span
                    className={`mt-px inline-flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] leading-none ${mark.cls}`}
                    title={mark.text}
                  >
                    <span aria-hidden="true">{mark.glyph}</span>
                    <span className="sr-only">{mark.text}</span>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
