"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ToneComparison } from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  transient: "Transient failure",
  customer_action_needed: "Needs customer action",
  risk_flag: "Risk flag",
};

const TONE_COLORS: Record<string, string> = {
  casual: "#2dd4bf",
  empathetic: "#f0b429",
  formal: "#8b94a7",
};

function ToneCell({
  tone,
  stats,
  isBest,
}: {
  tone: string;
  stats: { sample_size: number; recovered: number; recovery_rate_pct: number };
  isBest: boolean;
}) {
  const color = TONE_COLORS[tone] || "#8b94a7";
  return (
    <div
      className={`rounded-lg border p-4 ${
        isBest ? "border-accent bg-accent/5" : "border-border bg-surface"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium capitalize">{tone}</span>
        {isBest && (
          <span className="text-xs font-medium text-accent bg-accent/10 px-2 py-0.5 rounded">
            best
          </span>
        )}
      </div>
      <div className="font-mono text-3xl font-semibold mb-1" style={{ color }}>
        {stats.recovery_rate_pct}%
      </div>
      <div className="text-xs text-muted">
        {stats.recovered}/{stats.sample_size} recovered
      </div>
    </div>
  );
}

export default function ComparePage() {
  const [data, setData] = useState<ToneComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.toneComparison().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <Shell>
        <div className="bg-danger-dim border border-danger/30 rounded-lg p-6 text-danger text-sm">
          Couldn&apos;t reach the backend API. Error: {error}
        </div>
      </Shell>
    );
  }

  if (!data) {
    return (
      <Shell>
        <div className="text-muted font-mono text-sm">Loading comparison…</div>
      </Shell>
    );
  }

  const categories = Object.keys(data);

  return (
    <Shell>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">
          Same problem, different tone
        </h1>
        <p className="text-muted text-sm max-w-2xl">
          Payments diagnosed with the same root cause, split by the tone their recovery message
          used. This is the direct evidence that tone — not just the action taken — changes the
          outcome.
        </p>
      </div>

      <div className="space-y-8">
        {categories.map((category) => {
          const tones = data[category];
          const toneEntries = Object.entries(tones);
          const maxRate = Math.max(...toneEntries.map(([, s]) => s.recovery_rate_pct));

          return (
            <div key={category}>
              <h2 className="font-display font-semibold text-lg mb-3">
                {CATEGORY_LABELS[category] || category}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {toneEntries.map(([tone, stats]) => (
                  <ToneCell
                    key={tone}
                    tone={tone}
                    stats={stats}
                    isBest={stats.recovery_rate_pct === maxRate}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-surface-raised border border-border rounded-lg p-5 mt-10 text-sm text-muted">
        Sample sizes here are small (synthetic data, ~150 payments total) — read this as a
        directional signal the pipeline surfaces and measures, not a statistically proven result.
      </div>
    </Shell>
  );
}
