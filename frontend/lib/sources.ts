import { SOURCE_LABEL } from "./format";

/** Each data source prints in one process ink. Always pair the ink with a text label. */
export type Ink = "cyan" | "magenta" | "yellow" | "ink";

export const SOURCE_INK: Record<string, Ink> = {
  etsy: "cyan",
  etsy_tags: "cyan",
  etsy_signals: "cyan",
  google_suggest: "yellow",
  google_daily: "yellow",
};

/** Single-letter plate code shown next to the ink (C/M/Y/K). */
export const INK_LETTER: Record<Ink, string> = { cyan: "C", magenta: "M", yellow: "Y", ink: "K" };

/** Static class names so Tailwind can see them. */
export const INK_BG: Record<Ink, string> = {
  cyan: "bg-cyan",
  magenta: "bg-magenta",
  yellow: "bg-yellow",
  ink: "bg-ink",
};

export function sourceInk(source: string): Ink {
  return SOURCE_INK[source] ?? "ink";
}

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

export { SOURCE_LABEL };
