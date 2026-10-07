import type { ReactNode } from "react";

/** A titled block: garment-label title (eyebrow style) with a rule, optional aside on the right. */
export default function Section({
  title,
  aside,
  children,
  className = "",
  id,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`space-y-3 ${className}`} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 border-b border-rule pb-2">
        <h2 id={id ? `${id}-title` : undefined} className="text-[18px] font-semibold leading-6 text-ink">
          {title}
        </h2>
        {aside && <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">{aside}</div>}
      </div>
      {children}
    </section>
  );
}
