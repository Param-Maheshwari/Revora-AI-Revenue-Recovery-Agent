"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { api, AuditLog } from "@/lib/api";

export default function AuditPage() {
  const [log, setLog] = useState<AuditLog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.auditLog().then(setLog).catch((e) => setError(e.message));
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

  if (!log) {
    return (
      <Shell>
        <div className="text-muted font-mono text-sm">Loading audit log…</div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Audit Log</h1>
        <p className="text-muted text-sm max-w-2xl">
          Every action the compliance gate blocked, and why. This runs on plain deterministic
          rules — no AI — because compliance decisions need to be predictable and explainable, not
          model-decided.
        </p>
      </div>

      <div className="bg-surface border border-border rounded-lg p-5 mb-6 inline-flex items-center gap-3">
        <span className="font-mono text-2xl font-semibold text-danger">{log.total_blocked}</span>
        <span className="text-sm text-muted">actions blocked out of the full batch</span>
      </div>

      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted">
              <th className="px-4 py-3 font-medium">Payment</th>
              <th className="px-4 py-3 font-medium">Customer</th>
              <th className="px-4 py-3 font-medium">Would-be action</th>
              <th className="px-4 py-3 font-medium">Final action</th>
              <th className="px-4 py-3 font-medium">Reason blocked</th>
            </tr>
          </thead>
          <tbody>
            {log.entries.map((e) => (
              <tr key={e.payment_id} className="border-b border-border last:border-0 hover:bg-surface-raised transition-colors">
                <td className="px-4 py-3">
                  <Link
                    href={`/payments/${e.payment_id}`}
                    className="font-mono text-accent hover:underline"
                  >
                    {e.payment_id}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-muted text-xs">{e.customer_id}</td>
                <td className="px-4 py-3 text-muted">{e.chosen_action}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-danger-dim text-danger">
                    {e.final_action}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted">{e.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
