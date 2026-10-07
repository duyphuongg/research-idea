import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-ink text-white border border-ink hover:bg-ink/85",
  secondary: "bg-sheet text-ink border border-rule hover:border-ink-2",
  ghost: "bg-transparent text-ink border border-transparent hover:bg-ink/5",
};
const SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs gap-1",
  md: "h-9 px-3.5 text-sm gap-1.5",
};

export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md", className = ""): string {
  return `inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`;
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize };

export default function Button({ variant = "secondary", size = "md", className = "", type = "button", ...rest }: Props) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}

/** Same look as Button, rendered as a Next.js Link. */
export function ButtonLink({
  variant = "secondary",
  size = "md",
  className = "",
  ...rest
}: ComponentProps<typeof Link> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={buttonClass(variant, size, className)} {...rest} />;
}
