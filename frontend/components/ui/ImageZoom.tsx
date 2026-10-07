"use client";

import { useRef, useState, type ReactNode } from "react";
import { fullSizeImage } from "@/lib/images";

/**
 * Thumbnail that opens a full-size preview in a modal on click.
 * `children` is the thumbnail; the button takes the size of `className`.
 * Uses a native <dialog>: Esc and backdrop click close it, focus returns to the thumbnail.
 */
export default function ImageZoom({
  src,
  alt,
  href,
  className = "",
  children,
}: {
  src: string;
  alt: string;
  href?: string;
  className?: string;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  // What the dialog shows: the (already cached) thumbnail first, swapped for the full-size image once it loads.
  const [shown, setShown] = useState<string | null>(null);

  function open() {
    setShown(src);
    dialog.current?.showModal();
    const full = fullSizeImage(src);
    if (full === src) return;
    const preload = new Image();
    preload.onload = () => setShown((cur) => (cur === null ? cur : full));
    preload.src = full;
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        aria-label={`Phóng to ảnh: ${alt}`}
        className={`block cursor-zoom-in ${className}`}
      >
        {children}
      </button>
      <dialog
        ref={dialog}
        aria-label={alt}
        onClick={(e) => e.target === e.currentTarget && dialog.current?.close()}
        onClose={() => setShown(null)}
        className="m-auto max-h-[92vh] w-[min(92vw,760px)] overflow-hidden rounded-md border border-rule bg-sheet p-0 text-ink shadow-[0_24px_64px_rgba(21,23,30,0.35)] backdrop:bg-ink/75"
      >
        <div className="flex items-center justify-between gap-3 border-b border-rule px-3 py-2">
          <p className="line-clamp-1 min-w-0 text-sm font-medium">{alt}</p>
          <div className="flex shrink-0 items-center gap-1">
            {href && (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-7 items-center rounded-md border border-rule px-2.5 text-xs font-medium hover:border-ink-2"
              >
                Mở sản phẩm ↗
              </a>
            )}
            <button
              type="button"
              onClick={() => dialog.current?.close()}
              aria-label="Đóng"
              className="inline-flex size-7 items-center justify-center rounded-md text-lg leading-none hover:bg-ink/5"
            >
              ×
            </button>
          </div>
        </div>
        <div className="flex items-center justify-center bg-paper">
          {shown && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={shown}
              alt={alt}
              className="aspect-[4/5] max-h-[calc(92vh-45px)] w-full object-contain"
            />
          )}
        </div>
      </dialog>
    </>
  );
}
