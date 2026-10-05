"use client";

import { useEffect, useState } from "react";
import { api, type SourceHealth } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function SourceHealthBanner() {
  const [sources, setSources] = useState<SourceHealth[]>([]);

  useEffect(() => {
    api.sourceHealth().then(setSources).catch(() => setSources([]));
  }, []);

  const warnings = sources.filter(
    (s) => s.enabled && (!s.configured || s.last_status === "failed" || s.last_status === "partial"),
  );
  if (warnings.length === 0) return null;

  return (
    <div className="mb-4 space-y-1 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      {warnings.map((s) => (
        <p key={s.name}>
          ⚠ <b>{s.name}</b>:{" "}
          {!s.configured
            ? "chưa cấu hình API key"
            : s.last_status === "failed"
              ? `lỗi lần quét gần nhất (${timeAgo(s.last_finished_at)})`
              : `lần quét gần nhất chỉ thành công một phần (${timeAgo(s.last_finished_at)})`}
        </p>
      ))}
    </div>
  );
}
