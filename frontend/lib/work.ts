"use client";

import { useEffect, useSyncExternalStore } from "react";
import { api, type WorkItem, type WorkKind, type WorkStatusValue } from "./api";

/** Display order on /work and in the status picker. */
export const WORK_STATUSES: WorkStatusValue[] = ["designing", "idea", "listed", "skipped"];

export const WORK_STATUS: Record<WorkStatusValue, { icon: string; label: string }> = {
  idea: { icon: "💡", label: "Ý tưởng" },
  designing: { icon: "🎨", label: "Đang thiết kế" },
  listed: { icon: "✅", label: "Đã đăng" },
  skipped: { icon: "⏸", label: "Bỏ qua" },
};

export const workKey = (kind: WorkKind, id: number) => `${kind}:${id}`;

/**
 * One shared copy of GET /api/work for the whole app: every WorkStatus control reads from it,
 * so a list of 100 rows makes one request, and updates are applied optimistically.
 */
type State = { loaded: boolean; error: string | null; items: Map<string, WorkItem> };

let state: State = { loaded: false, error: null, items: new Map() };
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const SERVER_STATE: State = { loaded: false, error: null, items: new Map() };

/** Fetch the list (once, unless `force`). Errors are kept in state; controls still work. */
export function loadWork(force = false): Promise<void> {
  if (inflight) return inflight;
  if (state.loaded && !force) return Promise.resolve();
  inflight = api
    .listWork()
    .then((items) => emit({ loaded: true, error: null, items: new Map(items.map((i) => [workKey(i.subject_kind, i.subject_id), i])) }))
    .catch((err) => emit({ ...state, loaded: true, error: String(err) }))
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

function withItem(key: string, item: WorkItem | undefined): Map<string, WorkItem> {
  const items = new Map(state.items);
  if (item) items.set(key, item);
  else items.delete(key);
  return items;
}

/** Set a status (and note); optimistic, reverts and rethrows on failure. */
export async function saveWork(
  kind: WorkKind,
  id: number,
  status: WorkStatusValue,
  note: string | null,
  title?: string,
): Promise<void> {
  const key = workKey(kind, id);
  const prev = state.items.get(key);
  const optimistic: WorkItem = {
    subject_kind: kind,
    subject_id: id,
    title: prev?.title ?? title ?? "",
    image_url: prev?.image_url ?? null,
    link: prev?.link ?? null,
    external_url: prev?.external_url ?? null,
    status,
    note,
    updated_at: new Date().toISOString(),
  };
  emit({ ...state, items: withItem(key, optimistic) });
  try {
    const saved = await api.setWork(kind, id, { status, note });
    emit({ ...state, items: withItem(key, saved) });
  } catch (err) {
    emit({ ...state, items: withItem(key, prev) });
    throw err;
  }
}

/** Remove the status; optimistic, reverts and rethrows on failure. */
export async function clearWork(kind: WorkKind, id: number): Promise<void> {
  const key = workKey(kind, id);
  const prev = state.items.get(key);
  emit({ ...state, items: withItem(key, undefined) });
  try {
    await api.deleteWork(kind, id);
  } catch (err) {
    emit({ ...state, items: withItem(key, prev) });
    throw err;
  }
}

/** Shared work list; triggers the one-time fetch on first use. */
export function useWork(): State {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => state,
    () => SERVER_STATE,
  );
  useEffect(() => {
    loadWork();
  }, []);
  return snapshot;
}

/** The work item for one subject (undefined when none). */
export function useWorkItem(kind: WorkKind, id: number): WorkItem | undefined {
  return useWork().items.get(workKey(kind, id));
}
