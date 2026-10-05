"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type AppSettings, type ScanRun, type Seed } from "@/lib/api";
import { parseUtc, timeAgo } from "@/lib/format";

const STATUS_STYLE: Record<ScanRun["status"], string> = {
  running: "bg-blue-100 text-blue-800",
  ok: "bg-green-100 text-green-800",
  partial: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-800",
};

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function SettingsPage() {
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [scans, setScans] = useState<ScanRun[]>([]);
  const [newSeed, setNewSeed] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const loadSeeds = useCallback(() => api.listSeeds().then(setSeeds), []);
  const loadScans = useCallback(() => api.listScans(20).then(setScans), []);

  useEffect(() => {
    Promise.all([loadSeeds(), api.getSettings().then(setSettings), loadScans()]).catch((err) =>
      setMessage(`Không kết nối được backend: ${errorText(err)}`),
    );
  }, [loadSeeds, loadScans]);

  const anyRunning = scans.some((s) => s.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => loadScans().catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [anyRunning, loadScans]);

  async function addSeed(e: FormEvent) {
    e.preventDefault();
    const keyword = newSeed.trim();
    if (!keyword) return;
    try {
      await api.addSeed(keyword);
      setNewSeed("");
      setMessage(null);
      await loadSeeds();
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `"${keyword}" đã có trong watchlist` : errorText(err));
    }
  }

  async function removeSeed(id: number) {
    try {
      await api.deleteSeed(id);
      await loadSeeds();
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  async function saveSettings(body: Parameters<typeof api.updateSettings>[0]) {
    try {
      setSettings(await api.updateSettings(body));
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  async function scanNow() {
    try {
      const res = await api.startScan();
      setMessage(`Đã bắt đầu quét: ${res.sources.join(", ")}`);
      await loadScans();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setMessage("Đang có lần quét chạy, vui lòng chờ.");
      else if (err instanceof ApiError && err.status === 400) setMessage("Không có nguồn nào đang bật và đã cấu hình API key.");
      else setMessage(errorText(err));
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Cài đặt</h1>
      {message && <p className="rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}

      <section className="space-y-3">
        <h2 className="font-semibold">Watchlist keyword</h2>
        <form onSubmit={addSeed} className="flex gap-2">
          <input
            value={newSeed}
            onChange={(e) => setNewSeed(e.target.value)}
            placeholder="vd: nurse, dog mom, fishing"
            className="w-72 rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
          />
          <button className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white">Thêm</button>
        </form>
        <div className="flex flex-wrap gap-2">
          {seeds.length === 0 && <p className="text-sm text-zinc-500">Chưa có keyword nào.</p>}
          {seeds.map((s) => (
            <span key={s.id} className="flex items-center gap-1 rounded-full border border-zinc-300 bg-white px-3 py-1 text-sm">
              {s.keyword}
              <button onClick={() => removeSeed(s.id)} className="text-zinc-400 hover:text-red-600" aria-label={`Xóa ${s.keyword}`}>
                ×
              </button>
            </span>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Nguồn dữ liệu</h2>
        <ul className="divide-y divide-zinc-200 rounded-md border border-zinc-200 bg-white">
          {settings?.connectors.map((c) => (
            <li key={c.name} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="w-24 font-medium">{c.name}</span>
              <span className={c.configured ? "text-green-700" : "text-zinc-400"}>
                {c.configured ? "Đã cấu hình API key" : "Chưa cấu hình (thêm vào backend/.env)"}
              </span>
              <label className="ml-auto flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={c.enabled}
                  onChange={(e) => saveSettings({ connectors_enabled: { [c.name]: e.target.checked } })}
                />
                Bật
              </label>
            </li>
          ))}
        </ul>
        {settings && (
          <label className="flex items-center gap-2 text-sm">
            Giờ quét hằng ngày (UTC):
            <select
              value={settings.scan_hour_utc}
              onChange={(e) => saveSettings({ scan_hour_utc: Number(e.target.value) })}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1"
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
            <span className="text-zinc-500">= {String((settings.scan_hour_utc + 7) % 24).padStart(2, "0")}:00 giờ Việt Nam</span>
          </label>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">Lịch sử quét</h2>
          <button
            onClick={scanNow}
            disabled={anyRunning}
            className="rounded-md bg-orange-500 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {anyRunning ? "Đang quét…" : "Quét ngay"}
          </button>
        </div>
        <table className="w-full rounded-md border border-zinc-200 bg-white text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">Nguồn</th>
              <th className="px-3 py-2">Trạng thái</th>
              <th className="px-3 py-2">Bắt đầu</th>
              <th className="px-3 py-2">Bản ghi</th>
              <th className="px-3 py-2">Lỗi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {scans.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-3 text-zinc-500">
                  Chưa có lần quét nào.
                </td>
              </tr>
            )}
            {scans.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2">{s.source}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[s.status]}`}>{s.status}</span>
                </td>
                <td className="px-3 py-2" title={parseUtc(s.started_at).toLocaleString()}>
                  {timeAgo(s.started_at)}
                </td>
                <td className="px-3 py-2">{s.records}</td>
                <td className="max-w-md truncate px-3 py-2 text-xs text-red-700" title={s.error ?? ""}>
                  {s.error}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
