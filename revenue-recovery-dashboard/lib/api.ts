// Central place for the backend URL — change this if your FastAPI
// server runs somewhere other than localhost:8000
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ToneStats = {
  messages_sent: number;
  recovered_count: number;
  recovery_rate_pct: number;
  amount_at_risk: number;
  amount_recovered: number;
};

export type MetricsSummary = {
  total_payments: number;
  total_amount_at_risk: number;
  total_amount_recovered: number;
  overall_recovery_rate_pct: number;
  recovery_rate_by_tone: Record<string, ToneStats>;
  blocked_by_compliance_count: number;
  exceptions_count: number;
  assumptions: Record<string, string>;
};

export type PaymentSummary = {
  payment_id: string;
  customer_id: string;
  amount: number;
  predicted_category: string;
  final_action: string;
  chosen_tone: string;
  gate_status: string;
  recovered: boolean;
};

export type PaymentTrace = {
  payment_id: string;
  customer: {
    name: string;
    customer_id: string;
    past_payment_behavior: string;
    formality_preference: string;
    opted_out: string;
  };
  payment: {
    amount: number;
    failure_reason_raw: string;
    retry_count: string;
    timestamp: string;
  };
  stages: {
    "1_detect": { status: string; raw_reason: string };
    "2_diagnose": { predicted_category: string; reasoning: string };
    "3_choose_intervention": { action: string; tone: string; reasoning: string };
    "4_compliance_gate": { final_action: string; status: string; reason: string };
    "5_message": { text: string };
    "6_customer_response": { reply: string; outcome: string; promised_date: string } | null;
    "7_promise_tracking": { promise_kept: string; escalation_step: string } | null;
  };
  final_outcome: { recovered: boolean; recovery_path: string };
};

export type ToneComparison = Record<
  string,
  Record<
    string,
    {
      sample_size: number;
      recovered: number;
      recovery_rate_pct: number;
      example_payment_ids: string[];
    }
  >
>;

export type AuditLog = {
  total_blocked: number;
  entries: {
    payment_id: string;
    customer_id: string;
    chosen_action: string;
    final_action: string;
    reason: string;
  }[];
};

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status} on ${path}`);
  }
  return res.json();
}

export const api = {
  metrics: () => fetchJSON<MetricsSummary>("/api/metrics"),
  payments: () => fetchJSON<PaymentSummary[]>("/api/payments"),
  paymentTrace: (id: string) => fetchJSON<PaymentTrace>(`/api/payments/${id}`),
  toneComparison: () => fetchJSON<ToneComparison>("/api/tone-comparison"),
  auditLog: () => fetchJSON<AuditLog>("/api/audit-log"),
};
