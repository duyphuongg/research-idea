"use client";

import { useEffect, useState } from "react";
import { Notice } from "@/components/ui";
import { api, type SourceHealth } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { sourceLabel } from "@/lib/sources";

export default function SourceHealthBanner() {
  const [sources, setSources] = useState<SourceHealth[]>([]);

  useEffect(() => {
    api.sourceHealth().then(setSources).catch(() => setSources([]));
  }, []);

  const warnings = sources.filter(
    (s) => s.enabled && (!s.configured || s.last_status === "failed" || s.last_status === "partial"),
  );
  if (warnings.length === 0) return null;
  const failed = warnings.some((s) => s.configured && s.last_status === "failed");

  return (
    <Notice tone={failed ? "error" : "warn"} title="Một số nguồn dữ liệu cần kiểm tra" className="mb-4">
      <ul className="space-y-0.5">
        {warnings.map((s) => (
          <li key={s.name}>
            <span className="font-medium">{sourceLabel(s.name)}</span>
            <span className="font-mono text-xs text-ink-2"> ({s.name})</span>:{" "}
            {!s.configured
              ? "chưa cấu hình API key"
              : s.last_status === "failed"
                ? `lỗi lần quét gần nhất (${timeAgo(s.last_finished_at)})`
                : `lần quét gần nhất chỉ thành công một phần (${timeAgo(s.last_finished_at)})`}
          </li>
        ))}
      </ul>
    </Notice>
  );
}
