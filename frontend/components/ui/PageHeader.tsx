import type { ReactNode } from "react";
import RegistrationMark from "./RegistrationMark";

/** Page header: ⊕ eyebrow (page name · data date), Archivo title, one-line description, actions on the right. */
export default function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <p className="eyebrow flex items-center gap-1.5 text-ink-2">
          <RegistrationMark className="text-ink" />
          {eyebrow}
        </p>
        <h1 className="font-wide mt-1 font-display text-[24px] font-extrabold leading-tight tracking-tight text-ink sm:text-[28px]">
          {title}
        </h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
