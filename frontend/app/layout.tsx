import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "POD Trend Radar",
  description: "Nghiên cứu ngách và sản phẩm POD bán chạy tại Mỹ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="min-h-screen bg-zinc-50 text-zinc-900 antialiased">
        <header className="border-b border-zinc-200 bg-white">
          <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
            <span className="font-semibold">POD Trend Radar</span>
            <Link href="/" className="text-zinc-600 hover:text-zinc-900">
              Trend Radar
            </Link>
            <Link href="/products" className="text-zinc-600 hover:text-zinc-900">
              Best Sellers
            </Link>
            <Link href="/calendar" className="text-zinc-600 hover:text-zinc-900">
              Lịch mùa vụ
            </Link>
            <Link href="/settings" className="text-zinc-600 hover:text-zinc-900">
              Cài đặt
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
