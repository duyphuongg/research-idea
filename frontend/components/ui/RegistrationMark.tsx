/** Printer's registration mark (⊕) — used before every page eyebrow and in the logo. */
export default function RegistrationMark({ size = 12, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      aria-hidden="true"
      className={`inline-block shrink-0 ${className}`}
    >
      <circle cx="6" cy="6" r="3.6" />
      <path d="M6 0v12M0 6h12" />
    </svg>
  );
}
