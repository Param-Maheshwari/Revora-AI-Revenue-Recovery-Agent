"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { api, PaymentTrace } from "@/lib/api";

function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

type Stage = {
  key: string;
  title: string;
  kind: "detect" | "ai" | "gate" | "message" | "response" | "tracking";
  render: (trace: PaymentTrace) => React.ReactNode;
  applicable: (trace: PaymentTrace) => boolean;
};

const STAGES: Stage[] = [
  {
    key: "detect",
    title: "Detect",
    kind: "detect",
    applicable: () => true,
    render: (t) => (
      <p className="text-sm text-muted">
        Raw failure signal: <span className="font-mono text-foreground">&ldquo;{t.stages["1_detect"].raw_reason}&rdquo;</span>
      </p>
    ),
  },
  {
    key: "diagnose",
    title: "Diagnose (AI)",
    kind: "ai",
    applicable: () => true,
    render: (t) => (
      <div className="text-sm">
        <p className="text-muted mb-1">
          Category: <span className="text-foreground font-medium capitalize">{t.stages["2_diagnose"].predicted_category?.replace(/_/g, " ")}</span>
        </p>
        <p className="text-muted italic">&ldquo;{t.stages["2_diagnose"].reasoning}&rdquo;</p>
      </div>
    ),
  },
  {
    key: "choose",
    title: "Choose Intervention (AI)",
    kind: "ai",
    applicable: () => true,
    render: (t) => (
      <div className="text-sm">
        <p className="text-muted mb-1">
          Action: <span className="text-foreground font-medium">{t.stages["3_choose_intervention"].action}</span>
          {"  ·  "}
          Tone: <span className="text-foreground font-medium capitalize">{t.stages["3_choose_intervention"].tone}</span>
        </p>
        <p className="text-muted italic">&ldquo;{t.stages["3_choose_intervention"].reasoning}&rdquo;</p>
      </div>
    ),
  },
  {
    key: "gate",
    title: "Compliance Gate",
    kind: "gate",
    applicable: () => true,
    render: (t) => {
      const g = t.stages["4_compliance_gate"];
      const blocked = g.status === "BLOCKED";
      return (
        <div className="text-sm">
          <p className={`font-medium mb-1 ${blocked ? "text-danger" : "text-success"}`}>
            {blocked ? "BLOCKED" : "ALLOWED"} → {g.final_action}
          </p>
          <p className="text-muted">{g.reason}</p>
          <p className="text-xs text-muted mt-1 font-mono">deterministic rule check — no AI here, by design</p>
        </div>
      );
    },
  },
  {
    key: "message",
    title: "Hinglish Message",
    kind: "message",
    applicable: (t) => !!t.stages["5_message"].text && !t.stages["5_message"].text.startsWith("[no message"),
    render: (t) => (
      <div className="bg-surface-raised border border-border rounded-md p-3 text-sm font-mono">
        {t.stages["5_message"].text}
      </div>
    ),
  },
  {
    key: "response",
    title: "Simulated Customer Response (AI)",
    kind: "response",
    applicable: (t) => !!t.stages["6_customer_response"],
    render: (t) => {
      const r = t.stages["6_customer_response"];
      if (!r) return null;
      return (
        <div className="text-sm">
          <div className="bg-surface-raised border border-border rounded-md p-3 font-mono mb-2">
            {r.reply}
          </div>
          <p className="text-muted">
            Outcome: <span className="text-foreground font-medium">{r.outcome.replace(/_/g, " ")}</span>
            {r.promised_date && <> · promised: <span className="text-foreground">{r.promised_date}</span></>}
          </p>
        </div>
      );
    },
  },
  {
    key: "tracking",
    title: "Promise Tracking",
    kind: "tracking",
    applicable: (t) => !!t.stages["7_promise_tracking"],
    render: (t) => {
      const tr = t.stages["7_promise_tracking"];
      if (!tr) return null;
      const kept = tr.promise_kept === "True";
      return (
        <p className="text-sm">
          Promise <span className={`font-medium ${kept ? "text-success" : "text-danger"}`}>{kept ? "kept" : "broken"}</span>
          {!kept && <> → escalated to <span className="text-foreground font-medium">{tr.escalation_step}</span></>}
        </p>
      );
    },
  },
];

const KIND_COLOR: Record<Stage["kind"], string> = {
  detect: "#8b94a7",
  ai: "#f0b429",
  gate: "#fb7185",
  message: "#2dd4bf",
  response: "#f0b429",
  tracking: "#2dd4bf",
};

export default function PaymentTracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [trace, setTrace] = useState<PaymentTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealedCount, setRevealedCount] = useState(0);

  useEffect(() => {
    api
      .paymentTrace(id)
      .then(setTrace)
      .catch((e) => setError(e.message));
  }, [id]);

  const applicableStages = trace ? STAGES.filter((s) => s.applicable(trace)) : [];

  useEffect(() => {
    if (!trace) return;
    setRevealedCount(0);
    const total = applicableStages.length;
    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      setRevealedCount(i);
      if (i >= total) clearInterval(interval);
    }, 350);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trace]);

  if (error) {
    return (
      <Shell>
        <div className="bg-danger-dim border border-danger/30 rounded-lg p-6 text-danger text-sm">
          Couldn&apos;t load this payment. Error: {error}
        </div>
      </Shell>
    );
  }

  if (!trace) {
    return (
      <Shell>
        <div className="text-muted font-mono text-sm">Loading trace…</div>
      </Shell>
    );
  }

  return (
    <Shell>
      <Link href="/payments" className="text-sm text-muted hover:text-foreground mb-6 inline-block">
        ← Back to payments
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <div className="text-xs uppercase tracking-widest text-accent font-medium mb-1">
            {trace.payment_id}
          </div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            {trace.customer.name}
          </h1>
          <p className="text-sm text-muted mt-1">
            {formatINR(trace.payment.amount)} · {trace.customer.past_payment_behavior}
          </p>
        </div>
        <div
          className={`px-4 py-2 rounded-md text-sm font-medium ${
            trace.final_outcome.recovered
              ? "bg-success-dim text-success"
              : "bg-surface-raised text-muted"
          }`}
        >
          {trace.final_outcome.recovered ? "Recovered" : "Not recovered"}
        </div>
      </div>

      <div className="space-y-0">
        {applicableStages.map((stage, i) => {
          const revealed = i < revealedCount;
          const isLast = i === applicableStages.length - 1;
          return (
            <div key={stage.key} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div
                  className={`w-3 h-3 rounded-full border-2 shrink-0 transition-all duration-500 ${
                    revealed ? "" : "opacity-30"
                  }`}
                  style={{
                    borderColor: KIND_COLOR[stage.kind],
                    backgroundColor: revealed ? KIND_COLOR[stage.kind] : "transparent",
                  }}
                />
                {!isLast && (
                  <div
                    className={`w-px flex-1 min-h-8 transition-opacity duration-500 ${
                      revealed ? "opacity-100" : "opacity-20"
                    }`}
                    style={{ backgroundColor: "var(--border)" }}
                  />
                )}
              </div>
              <div
                className={`pb-8 flex-1 transition-all duration-500 ${
                  revealed ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
                }`}
              >
                <h3 className="font-display font-semibold text-sm mb-2">{stage.title}</h3>
                {revealed && stage.render(trace)}
              </div>
            </div>
          );
        })}
      </div>

      {revealedCount >= applicableStages.length && (
        <div className="bg-surface-raised border border-border rounded-lg p-5 mt-4">
          <p className="text-sm">
            <span className="font-medium">Final outcome: </span>
            <span className="text-muted">{trace.final_outcome.recovery_path}</span>
          </p>
        </div>
      )}
    </Shell>
  );
}
