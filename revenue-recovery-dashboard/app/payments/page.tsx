"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { api, PaymentSummary } from "@/lib/api";

function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

const CATEGORY_LABELS: Record<string, string> = {
  transient: "Transient",
  customer_action_needed: "Needs action",
  risk_flag: "Risk flag",
};

function StatusPill({ recovered, gateStatus }: { recovered: boolean; gateStatus: string }) {
  if (gateStatus === "BLOCKED") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-danger-dim text-danger">
        blocked
      </span>
    );
  }
  if (recovered) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-success-dim text-success">
        recovered
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-surface-raised text-muted">
      pending
    </span>
  );
}

export default function PaymentsPage() {
  const [payments, setPayments] = useState<PaymentSummary[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.payments().then(setPayments).catch((e) => setError(e.message));
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

  if (!payments) {
    return (
      <Shell>
        <div className="text-muted font-mono text-sm">Loading payments…</div>
      </Shell>
    );
  }

  const filtered = payments.filter((p) => {
    if (filter === "all") return true;
    if (filter === "recovered") return p.recovered;
    if (filter === "blocked") return p.gate_status === "BLOCKED";
    return p.predicted_category === filter;
  });

  return (
    <Shell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Payments</h1>
        <p className="text-muted text-sm">
          Click any payment to see its full agent trace — every stage, every decision.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mb-5">
        {[
          { key: "all", label: `All (${payments.length})` },
          { key: "recovered", label: "Recovered" },
          { key: "blocked", label: "Blocked" },
          { key: "transient", label: "Transient" },
          { key: "customer_action_needed", label: "Needs action" },
          { key: "risk_flag", label: "Risk flag" },
        ].map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
              filter === f.key
                ? "bg-accent text-background"
                : "bg-surface border border-border text-muted hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted">
              <th className="px-4 py-3 font-medium">Payment</th>
              <th className="px-4 py-3 font-medium">Category</th>
              <th className="px-4 py-3 font-medium">Action</th>
              <th className="px-4 py-3 font-medium">Tone</th>
              <th className="px-4 py-3 font-medium text-right">Amount</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.payment_id} className="border-b border-border last:border-0 hover:bg-surface-raised transition-colors">
                <td className="px-4 py-3">
                  <Link
                    href={`/payments/${p.payment_id}`}
                    className="font-mono text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent rounded"
                  >
                    {p.payment_id}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted">
                  {CATEGORY_LABELS[p.predicted_category] || p.predicted_category}
                </td>
                <td className="px-4 py-3 text-muted">{p.final_action}</td>
                <td className="px-4 py-3 text-muted capitalize">{p.chosen_tone || "—"}</td>
                <td className="px-4 py-3 text-right font-mono">{formatINR(p.amount)}</td>
                <td className="px-4 py-3">
                  <StatusPill recovered={p.recovered} gateStatus={p.gate_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="px-4 py-10 text-center text-muted text-sm">No payments match this filter.</div>
        )}
      </div>
    </Shell>
  );
}
