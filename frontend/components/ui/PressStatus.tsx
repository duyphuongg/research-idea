"use client";

import { useEffect, useState } from "react";
import { api, type ScanStatus, type SourceHealth } from "@/lib/api";
import { parseUtc } from "@/lib/format";
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

/** Compact age for the narrow sidebar: "12 phút", "5 giờ", "3 ngày". */
function shortAgo(iso: string | null): string {
  if (!iso) return "—";
  const minutes = Math.max(0, Math.floor((Date.now() - parseUtc(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} phút`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} giờ`;
  return `${Math.floor(minutes / 1440)} ngày`;
}

function needsAttention(s: SourceHealth): boolean {
  return !s.configured || s.last_status === "failed" || s.last_status === "partial";
}

/**
 * "Bản in hôm nay" — one summary line (sources OK · last update) that expands to the latest scan per source,
 * printed as C/M/Y/K plates. Opens by itself when a source needs attention. Designed for the dark sidebar.
 */
export default function PressStatus() {
  const [result, setResult] = useState<Result | null>(null);
  const [open, setOpen] = useState<boolean | null>(null); // null = not chosen by the user yet

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
  const problems = sources.filter(needsAttention);
  const latest = sources
    .map((s) => s.last_finished_at)
    .filter((t): t is string => t !== null)
    .sort()
    .at(-1);
  const expanded = open ?? problems.length > 0;

  let summary = "Đang tải…";
  if (result?.error) summary = "Không kết nối được backend";
  else if (result?.data && sources.length === 0) summary = "Chưa bật nguồn nào";
  else if (sources.length > 0)
    summary = problems.length > 0 ? `${problems.length} nguồn cần xem` : `${sources.length} nguồn ổn`;

  return (
    <div className="px-5 pt-3">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls="press-status-list"
        onClick={() => setOpen(!expanded)}
        disabled={sources.length === 0}
        className="group flex w-full items-center gap-2 rounded-md py-1 text-left disabled:cursor-default"
      >
        <span className="flex shrink-0 gap-0.5" aria-hidden="true">
          <InkDot ink="cyan" shape="square" size={7} />
          <InkDot ink="magenta" shape="square" size={7} />
          <InkDot ink="yellow" shape="square" size={7} />
          <InkDot ink="ink" shape="square" size={7} className="ring-1 ring-white/50" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="eyebrow block text-[10px] leading-3 text-white/40">Bản in hôm nay</span>
          <span className={`block text-xs leading-4 ${problems.length > 0 ? "text-yellow" : "text-white/80"}`}>
            {summary}
            {latest && <span className="whitespace-nowrap font-mono text-[11px] text-white/50"> · {shortAgo(latest)} trước</span>}
          </span>
        </span>
        {sources.length > 0 && (
          <span
            aria-hidden="true"
            className={`text-xs text-white/50 transition-transform group-hover:text-white ${expanded ? "rotate-90" : ""}`}
          >
            ›
          </span>
        )}
      </button>

      {expanded && sources.length > 0 && (
        <ul id="press-status-list" className="mt-2 space-y-1.5 pb-1">
          {sources.map((s) => {
            const ink = sourceInk(s.name);
            const mark = s.last_status ? MARK[s.last_status] : null;
            return (
              <li key={s.name} className="flex items-center gap-2 text-xs">
                <span
                  className={`inline-flex size-4 shrink-0 items-center justify-center rounded-[2px] font-mono text-[9px] font-medium ${PLATE[ink]}`}
                  aria-hidden="true"
                >
                  {INK_LETTER[ink]}
                </span>
                <span className="min-w-0 flex-1 truncate text-white/85" title={sourceLabel(s.name)}>
                  {sourceLabel(s.name)}
                </span>
                <span className={`shrink-0 font-mono text-[10px] ${s.configured ? "text-white/50" : "text-yellow"}`}>
                  {!s.configured ? "chưa cài" : s.last_status ? shortAgo(s.last_finished_at) : "chưa quét"}
                </span>
                {s.configured && mark && (
                  <span
                    className={`inline-flex size-3.5 shrink-0 items-center justify-center rounded-full text-[9px] leading-none ${mark.cls}`}
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
