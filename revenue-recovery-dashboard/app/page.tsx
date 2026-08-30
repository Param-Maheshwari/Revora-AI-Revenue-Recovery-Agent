"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, MetricsSummary } from "@/lib/api";

function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

function MetricCard({
  label,
  value,
  sublabel,
  accent,
}: {
  label: string;
  value: string;
  sublabel?: string;
  accent?: "success" | "danger" | "default";
}) {
  const valueColor =
    accent === "success" ? "text-success" : accent === "danger" ? "text-danger" : "text-foreground";
  return (
    <div className="bg-surface border border-border rounded-lg p-5">
      <div className="text-xs uppercase tracking-wider text-muted font-medium mb-2">{label}</div>
      <div className={`font-mono text-3xl font-semibold ${valueColor}`}>{value}</div>
      {sublabel && <div className="text-sm text-muted mt-1">{sublabel}</div>}
    </div>
  );
}

const TONE_COLORS: Record<string, string> = {
  casual: "#2dd4bf",
  empathetic: "#f0b429",
  formal: "#8b94a7",
};

function ToneBar({ tone, stats }: { tone: string; stats: { recovery_rate_pct: number; recovered_count: number; messages_sent: number; amount_recovered: number } }) {
  const widthPct = stats.recovery_rate_pct; // scale against a fixed 0-100% axis, not the leading tone's value
  const color = TONE_COLORS[tone] || "#8b94a7";
  return (
    <div className="flex items-center gap-4">
      <div className="w-24 text-sm font-medium capitalize text-right shrink-0">{tone}</div>
      <div className="flex-1 h-9 bg-surface-raised rounded-md overflow-hidden relative">
        <div
          className="h-full rounded-md transition-all duration-700 ease-out flex items-center justify-end pr-3"
          style={{ width: `${widthPct}%`, backgroundColor: color, minWidth: "3.5rem" }}
        >
          <span className="font-mono text-xs font-semibold text-background">
            {stats.recovery_rate_pct}%
          </span>
        </div>
      </div>
      <div className="w-40 shrink-0 text-xs text-muted font-mono text-right">
        {stats.recovered_count}/{stats.messages_sent} · {formatINR(stats.amount_recovered)}
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .metrics()
      .then(setMetrics)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <Shell>
        <div className="bg-danger-dim border border-danger/30 rounded-lg p-6 text-danger">
          <p className="font-medium mb-1">Couldn&apos;t reach the backend API.</p>
          <p className="text-sm opacity-90">
            Make sure your FastAPI server is running at http://localhost:8000 (uvicorn main:app --reload).
            Error: {error}
          </p>
        </div>
      </Shell>
    );
  }

  if (!metrics) {
    return (
      <Shell>
        <div className="text-muted font-mono text-sm">Loading pipeline results…</div>
      </Shell>
    );
  }

  const toneEntries = Object.entries(metrics.recovery_rate_by_tone).sort(
    (a, b) => b[1].recovery_rate_pct - a[1].recovery_rate_pct
  );

  return (
    <Shell>
      <div className="mb-10">
        <div className="text-xs uppercase tracking-widest text-accent font-medium mb-2">
          Track 03 — AI Revenue Recovery
        </div>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight mb-2">
          Detect. Diagnose. Recover.
        </h1>
        <p className="text-muted max-w-2xl">
          An agent pipeline that diagnoses why a payment failed, chooses a bounded recovery action,
          gates it against compliance rules, and messages the customer in natural Hinglish — then
          measures what actually worked.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <MetricCard label="Total at risk" value={formatINR(metrics.total_amount_at_risk)} />
        <MetricCard
          label="Total recovered"
          value={formatINR(metrics.total_amount_recovered)}
          accent="success"
        />
        <MetricCard
          label="Overall recovery rate"
          value={`${metrics.overall_recovery_rate_pct}%`}
          sublabel={`across ${metrics.total_payments} payments`}
        />
        <MetricCard
          label="Blocked by compliance"
          value={String(metrics.blocked_by_compliance_count)}
          sublabel={`${metrics.exceptions_count} exceptions`}
          accent="danger"
        />
      </div>

      <div className="bg-surface border border-border rounded-lg p-6 mb-10">
        <div className="flex items-baseline justify-between mb-1">
          <h2 className="font-display text-lg font-semibold">Recovery rate by message tone</h2>
          <span className="text-xs text-muted font-mono">measured, not assumed</span>
        </div>
        <p className="text-sm text-muted mb-6">
          Same failure categories, different tone of Hinglish message — this is what actually moved
          the needle.
        </p>
        <div className="space-y-4">
          {toneEntries.map(([tone, stats]) => (
            <ToneBar key={tone} tone={tone} stats={stats} />
          ))}
        </div>
      </div>

      <div className="bg-surface-raised border border-border rounded-lg p-5 text-sm text-muted">
        <span className="text-foreground font-medium">A note on these numbers: </span>
        recovery outcomes are simulated by an LLM customer-persona reasoning over each message and
        profile, not real customer data — the tone ranking is a measured hypothesis this system
        generates consistently, not a proven real-world result. See{" "}
        <span className="font-mono text-xs">/audit</span> for the full compliance trail.
      </div>
    </Shell>
  );
}
