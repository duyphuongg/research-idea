import type { InputHTMLAttributes, ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: ReactNode };

/** Native checkbox with ink accent and a clickable label. */
export default function Checkbox({ label, className = "", ...rest }: Props) {
  return (
    <label className={`inline-flex cursor-pointer select-none items-center gap-2 text-sm text-ink ${className}`}>
      <input type="checkbox" className="size-4 shrink-0 cursor-pointer rounded-sm accent-ink" {...rest} />
      {label}
    </label>
  );
}
