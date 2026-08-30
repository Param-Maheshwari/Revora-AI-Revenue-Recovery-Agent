"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/live", label: "Live Demo" },
  { href: "/payments", label: "Payments" },
  { href: "/compare", label: "Compare Tones" },
  { href: "/audit", label: "Audit Log" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border sticky top-0 z-20 bg-background/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-accent" aria-hidden />
            <span className="font-display font-semibold text-lg tracking-tight">
              Revora
            </span>
          </div>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
                    active
                      ? "bg-surface-raised text-foreground"
                      : "text-muted hover:text-foreground"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-10">{children}</main>
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-5 text-xs text-muted font-mono">
          Revora — AI Revenue Recovery Agent · Razorpay AI Buildathon · Track 03 · synthetic data
        </div>
      </footer>
    </div>
  );
}
