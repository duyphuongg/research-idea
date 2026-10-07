"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type AppSettings, type ScanRun, type Seed } from "@/lib/api";
import { Button, Card, Checkbox, InkDot, Notice, PageHeader, Section, Select, StatusBadge } from "@/components/ui";
import { sourceInk, sourceLabel } from "@/lib/sources";
import { parseUtc, timeAgo } from "@/lib/format";

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
    <div>
      <PageHeader eyebrow="Cài đặt" title="Cài đặt" description="Watchlist, nguồn dữ liệu và lịch quét." />
      {message && <Notice className="mb-5">{message}</Notice>}

      <div className="space-y-6">
        <Card className="p-5">
          <Section title="Watchlist keyword">
            <form onSubmit={addSeed} className="flex gap-2">
              <input
                value={newSeed}
                onChange={(e) => setNewSeed(e.target.value)}
                placeholder="vd: nurse, dog mom, fishing"
                aria-label="Keyword mới"
                className="h-9 min-w-0 flex-1 rounded-md border border-rule bg-sheet px-3 text-sm text-ink placeholder:text-ink-2/70 hover:border-ink-2 sm:max-w-xs sm:flex-none sm:basis-72"
              />
              <Button type="submit" variant="primary">
                Thêm
              </Button>
            </form>
            <div className="flex flex-wrap gap-2">
              {seeds.length === 0 && <p className="text-sm text-ink-2">Chưa có keyword nào.</p>}
              {seeds.map((s) => (
                <span key={s.id} className="inline-flex items-center gap-1 rounded-full border border-rule bg-paper py-0.5 pl-3 pr-1 text-sm text-ink">
                  {s.keyword}
                  <button
                    onClick={() => removeSeed(s.id)}
                    className="inline-flex size-5 items-center justify-center rounded-full text-ink-2 hover:bg-stop/10 hover:text-stop"
                    aria-label={`Xóa ${s.keyword}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </Section>
        </Card>

        <Card className="p-5">
          <Section title="Nguồn dữ liệu">
            <ul className="divide-y divide-rule rounded-md border border-rule">
              {settings?.connectors.map((c) => (
                <li key={c.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-sm">
                  <span className="inline-flex w-32 items-center gap-2 font-medium text-ink">
                    <InkDot ink={sourceInk(c.name)} size={8} />
                    {sourceLabel(c.name)}
                  </span>
                  <span className={`min-w-0 flex-1 basis-48 text-xs ${c.configured ? "text-ink" : "text-ink-2"}`}>
                    <span aria-hidden="true" className={`mr-1.5 inline-block size-1.5 rounded-full align-middle ${c.configured ? "bg-go" : "bg-ink-2/40"}`} />
                    {c.configured ? "Đã cấu hình API key" : "Chưa cấu hình (thêm vào backend/.env)"}
                  </span>
                  <Checkbox
                    label="Bật"
                    checked={c.enabled}
                    onChange={(e) => saveSettings({ connectors_enabled: { [c.name]: e.target.checked } })}
                  />
                </li>
              ))}
            </ul>
            {settings && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-3 text-sm text-ink">
                  <Select
                    label="Giờ quét hằng ngày (UTC)"
                    className="w-28"
                    value={settings.scan_hour_utc}
                    onChange={(e) => saveSettings({ scan_hour_utc: Number(e.target.value) })}
                  >
                    {Array.from({ length: 24 }, (_, h) => (
                      <option key={h} value={h}>
                        {String(h).padStart(2, "0")}:00
                      </option>
                    ))}
                  </Select>
                  <span className="self-end pb-2 font-mono text-xs text-ink-2">
                    = {String((settings.scan_hour_utc + 7) % 24).padStart(2, "0")}:00 giờ Việt Nam
                  </span>
                </div>
                <p className="max-w-2xl text-xs text-ink-2">
                  Đang quét tự động mỗi ngày bằng lịch của máy (make install-daily); giờ này chỉ dùng khi bật scheduler của backend.
                </p>
              </div>
            )}
          </Section>
        </Card>

        <Card className="p-5">
          <Section
            title="Lịch sử quét"
            aside={
              <Button variant="primary" onClick={scanNow} disabled={anyRunning}>
                {anyRunning ? "Đang quét…" : "Quét ngay"}
              </Button>
            }
          >
            <div className="overflow-x-auto rounded-md border border-rule">
              <table className="w-full min-w-[34rem] text-left text-sm">
                <thead className="bg-paper">
                  <tr className="eyebrow text-ink-2">
                    <th className="px-3 py-2 font-medium">Nguồn</th>
                    <th className="px-3 py-2 font-medium">Trạng thái</th>
                    <th className="px-3 py-2 font-medium">Bắt đầu</th>
                    <th className="px-3 py-2 text-right font-medium">Bản ghi</th>
                    <th className="px-3 py-2 font-medium">Lỗi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {scans.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-4 text-ink-2">
                        Chưa có lần quét nào.
                      </td>
                    </tr>
                  )}
                  {scans.map((s) => (
                    <tr key={s.id}>
                      <td className="px-3 py-2 text-ink">{sourceLabel(s.source)}</td>
                      <td className="px-3 py-2">
                        <StatusBadge kind="scan" status={s.status} />
                      </td>
                      <td className="px-3 py-2 text-ink-2" title={parseUtc(s.started_at).toLocaleString()}>
                        {timeAgo(s.started_at)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-ink">{s.records}</td>
                      <td className="max-w-xs truncate px-3 py-2 text-xs text-stop" title={s.error ?? ""}>
                        {s.error}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </Card>
      </div>
    </div>
  );
}
