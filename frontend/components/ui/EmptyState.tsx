import type { ReactNode } from "react";
import RegistrationMark from "./RegistrationMark";

/** Empty result: tells the user what to do next. */
export default function EmptyState({
  title,
  body,
  action,
  className = "",
}: {
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-center gap-2 rounded-md border border-dashed border-rule bg-sheet px-6 py-10 text-center ${className}`}
    >
      <RegistrationMark size={20} className="text-ink-2" />
      <p className="font-semibold text-ink">{title}</p>
      {body && <p className="max-w-md text-sm text-ink-2">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
