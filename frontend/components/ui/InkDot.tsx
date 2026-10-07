import { INK_BG, type Ink } from "@/lib/sources";

/** A small dot (or square) of process ink. Decorative — always pair it with text. */
export default function InkDot({
  ink,
  shape = "dot",
  size = 8,
  className = "",
}: {
  ink: Ink;
  shape?: "dot" | "square";
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block shrink-0 ${shape === "dot" ? "rounded-full" : "rounded-[1px]"} ${INK_BG[ink]} ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
