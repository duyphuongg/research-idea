import type { HTMLAttributes } from "react";

/** White sheet with a 1px rule border and hairline bottom shadow. */
export default function Card({
  padded = true,
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement> & { padded?: boolean }) {
  return <div className={`rounded-md border border-rule bg-sheet shadow-card ${padded ? "p-4" : ""} ${className}`} {...rest} />;
}
