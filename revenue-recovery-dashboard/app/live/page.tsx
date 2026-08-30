"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { API_BASE } from "@/lib/api";

type StageEvent = {
  type: string;
  payment_id?: string;
  index?: number;
  total?: number;
  total_rows?: number;
  stage?: string;
  data?: Record<string, unknown>;
  recovered?: boolean;
  amount?: number;
  auto_retry?: boolean;
};

type PaymentCard = {
  payment_id: string;
  stages: { stage: string; data: Record<string, unknown> }[];
  recovered: boolean | null;
  autoRetry: boolean;
  complete: boolean;
};

const STAGE_LABELS: Record<string, string> = {
  detect: "Detect",
  diagnose: "Diagnose (AI)",
  choose_intervention: "Choose intervention (AI)",
  compliance_gate: "Compliance gate",
  message: "Hinglish message (AI)",
  customer_response: "Simulated response (AI)",
  promise_tracking: "Promise tracking",
};

function renderStageContent(stage: string, data: Record<string, unknown>) {
  switch (stage) {
    case "detect":
      return <span className="text-muted">&ldquo;{String(data.raw_reason)}&rdquo;</span>;
    case "diagnose":
      return (
        <span>
          <span className="text-foreground font-medium capitalize">
            {String(data.category).replace(/_/g, " ")}
          </span>
          <span className="text-muted"> — {String(data.reasoning)}</span>
        </span>
      );
    case "choose_intervention":
      return (
        <span>
          <span className="text-foreground font-medium">{String(data.action)}</span>
          {" / "}
          <span className="text-foreground font-medium capitalize">{String(data.tone)}</span>
          <span className="text-muted"> — {String(data.reasoning)}</span>
        </span>
      );
    case "compliance_gate":
      return (
        <span>
          <span className={String(data.status) === "BLOCKED" ? "text-danger font-medium" : "text-success font-medium"}>
            {String(data.status)}
          </span>
          <span className="text-muted"> → {String(data.final_action)} · {String(data.reason)}</span>
        </span>
      );
    case "message":
      return <span className="font-mono text-xs">{String(data.text)}</span>;
    case "customer_response":
      return (
        <span>
          <span className="font-mono text-xs">&ldquo;{String(data.customer_reply)}&rdquo;</span>
          <span className="text-muted"> → {String(data.outcome).replace(/_/g, " ")}</span>
        </span>
      );
    case "promise_tracking":
      return (
        <span>
          <span className={data.promise_kept ? "text-success" : "text-danger"}>
            {data.promise_kept ? "kept" : `broken → ${String(data.escalation_step)}`}
          </span>
          {data.commitment_strength ? (
            <span className="text-muted">
              {" "}
              (commitment: {String(data.commitment_strength)}, adjusted rate {Math.round(Number(data.final_keep_probability_used) * 100)}%)
            </span>
          ) : null}
        </span>
      );
    default:
      return null;
  }
}

export default function LivePage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payments, setPayments] = useState<Record<string, PaymentCard>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [totalRecovered, setTotalRecovered] = useState(0);
  const [totalRecoveredAmount, setTotalRecoveredAmount] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  function reset() {
    setPayments({});
    setOrder([]);
    setProgress(null);
    setTotalRecovered(0);
    setTotalRecoveredAmount(0);
    setError(null);
    setNote(null);
  }

  async function handleUpload() {
    if (!file) return;
    reset();
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/api/live/upload`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const json = await res.json();
      setNote(json.note);
      setUploading(false);
      setRunning(true);
      startStream(json.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setUploading(false);
    }
  }

  function startStream(jobId: string) {
    const es = new EventSource(`${API_BASE}/api/live/stream/${jobId}`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      const evt: StageEvent = JSON.parse(event.data);

      if (evt.type === "job_started") {
        setProgress({ done: 0, total: evt.total_rows || 0 });
      } else if (evt.type === "stage" && evt.payment_id && evt.stage) {
        const pid = evt.payment_id;
        setPayments((prev) => {
          const existing = prev[pid] || { payment_id: pid, stages: [], recovered: null, autoRetry: false, complete: false };
          return {
            ...prev,
            [pid]: {
              ...existing,
              stages: [...existing.stages, { stage: evt.stage!, data: evt.data || {} }],
            },
          };
        });
        setOrder((prev) => (prev.includes(pid) ? prev : [pid, ...prev]));
      } else if (evt.type === "payment_complete" && evt.payment_id) {
        const pid = evt.payment_id;
        setPayments((prev) => ({
          ...prev,
          [pid]: { ...prev[pid], recovered: !!evt.recovered, autoRetry: !!evt.auto_retry, complete: true },
        }));
        setProgress({ done: evt.index || 0, total: evt.total || 0 });
        if (evt.recovered) {
          setTotalRecovered((n) => n + 1);
          setTotalRecoveredAmount((n) => n + (evt.amount || 0));
        }
      } else if (evt.type === "job_complete") {
        setRunning(false);
        es.close();
      } else if (evt.type === "error") {
        setError(String(evt));
        setRunning(false);
        es.close();
      }
    };

    es.onerror = () => {
      setRunning(false);
      es.close();
    };
  }

  return (
    <Shell>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">
          Live Processing
        </h1>
        <p className="text-muted text-sm max-w-2xl">
          Upload a payments CSV and watch the agent diagnose, decide, gate, message, and simulate
          recovery in real time — one payment at a time, exactly as it happens.
        </p>
      </div>

      <div className="bg-surface border border-border rounded-lg p-5 mb-8">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm text-muted file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-surface-raised file:text-foreground file:text-sm file:font-medium hover:file:bg-border cursor-pointer"
          />
          <button
            onClick={handleUpload}
            disabled={!file || uploading || running}
            className="px-4 py-2 rounded-md text-sm font-medium bg-accent text-background disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
          >
            {uploading ? "Uploading…" : running ? "Processing…" : "Run agent live"}
          </button>
          {progress && (
            <span className="text-xs font-mono text-muted ml-auto">
              {progress.done}/{progress.total} payments processed
            </span>
          )}
        </div>
        {note && <p className="text-xs text-muted mt-3">{note}</p>}
        {error && <p className="text-xs text-danger mt-3">{error}</p>}
        <p className="text-xs text-muted mt-3">
          Expected columns: payment_id, failure_reason_raw, retry_count, amount, customer_id (and
          optionally customer_name).
        </p>
      </div>

      {order.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-3">
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="text-xs uppercase tracking-wider text-muted mb-1">Processed</div>
            <div className="font-mono text-2xl font-semibold">{order.length}</div>
          </div>
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="text-xs uppercase tracking-wider text-muted mb-1">Recovered</div>
            <div className="font-mono text-2xl font-semibold text-success">{totalRecovered}</div>
          </div>
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="text-xs uppercase tracking-wider text-muted mb-1">₹ Recovered live</div>
            <div className="font-mono text-2xl font-semibold text-success">
              {new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(totalRecoveredAmount)}
            </div>
          </div>
        </div>
      )}

      {order.length > 0 && (
        <p className="text-xs text-muted mb-8">
          This is a small, real-time sample run for demonstration. For the full statistical
          comparison across all 150 payments, see the{" "}
          <Link href="/compare" className="text-accent hover:underline">Compare Tones</Link> page.
        </p>
      )}

      <div className="space-y-3">
        {order.map((pid) => {
          const card = payments[pid];
          if (!card) return null;
          return (
            <div key={pid} className="bg-surface border border-border rounded-lg p-4 animate-in">
              <div className="flex items-center justify-between mb-3">
                <span className="font-mono text-sm text-accent font-medium">{pid}</span>
                {card.complete && (
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded ${
                      card.autoRetry
                        ? "bg-surface-raised text-muted"
                        : card.recovered
                        ? "bg-success-dim text-success"
                        : "bg-surface-raised text-muted"
                    }`}
                  >
                    {card.autoRetry ? "auto-retried (technical)" : card.recovered ? "recovered" : "not recovered"}
                  </span>
                )}
                {!card.complete && (
                  <span className="text-xs font-mono text-accent animate-pulse">processing…</span>
                )}
              </div>
              <div className="space-y-1.5">
                {card.stages.map((s, i) => (
                  <div key={i} className="text-xs flex gap-2">
                    <span className="text-muted font-medium w-40 shrink-0">
                      {STAGE_LABELS[s.stage] || s.stage}
                    </span>
                    <span className="flex-1">{renderStageContent(s.stage, s.data)}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {order.length === 0 && !uploading && (
        <div className="text-center py-16 text-muted text-sm">
          Upload a CSV above to watch the agent process it live.
        </div>
      )}
    </Shell>
  );
}
