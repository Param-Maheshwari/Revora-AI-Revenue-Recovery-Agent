"""
metrics_engine.py — reads across the whole pipeline's output files and
produces the final measured report: total at-risk, total recovered,
recovery rate overall AND by tone (the standout metric), plus an honest
exceptions/blocked list.

Writes:
  data/metrics_summary.json  — headline numbers, for a dashboard/API to consume
  data/metrics_by_payment.csv — one row per payment with its final recovered status

Run with: python metrics_engine.py
"""

import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pipeline


def money(value):
    """Rupee amounts are accumulated as Decimal, not float.

    Summing 150 float rupee values drifts in the paise, and a recovery total
    that doesn't reconcile against the sum of its own line items is the one
    number in a revenue product nobody will trust.
    """
    try:
        return Decimal(str(value).replace(",", "").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0")


def to_float(value):
    return float(money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


with open(pipeline.data_path("gated_actions.csv"), newline="", encoding="utf-8") as f:
    gated = {r["payment_id"]: r for r in csv.DictReader(f)}

with open(pipeline.data_path("simulated_responses.csv"), newline="", encoding="utf-8") as f:
    responses = {r["payment_id"]: r for r in csv.DictReader(f)}

with open(pipeline.data_path("tracked_promises.csv"), newline="", encoding="utf-8") as f:
    tracked = {r["payment_id"]: r for r in csv.DictReader(f)}

with open(pipeline.data_path("payments.csv"), newline="", encoding="utf-8") as f:
    all_payments = list(csv.DictReader(f))

MESSAGING_ACTIONS = pipeline.MESSAGING_ACTIONS

per_payment_rows = []
total_at_risk = Decimal("0")
total_recovered = Decimal("0")

for p in all_payments:
    pid = p["payment_id"]
    amount = money(p["amount"])
    total_at_risk += amount

    gate_row = gated.get(pid, {})
    final_action = gate_row.get("final_action", "unknown")
    chosen_tone = gate_row.get("chosen_tone", "")

    recovered = False
    recovery_path = "not recovered"

    if final_action == "auto_retry":
        # we don't have a separate retry-success simulation, so treat
        # auto_retry as NOT counted toward "recovered via intervention"
        # metrics — it's a transient technical fix, tracked separately
        recovery_path = "auto_retry (technical, not counted as recovery intervention)"

    elif pid in responses:
        resp = responses[pid]
        outcome = resp["outcome"]

        if outcome == "paid_immediately":
            recovered = True
            recovery_path = "paid immediately after message"
        elif outcome == "promised_later":
            track = tracked.get(pid, {})
            if track.get("promise_kept") == "True":
                recovered = True
                recovery_path = "paid after keeping promise"
            else:
                recovery_path = f"promise broken -> escalated to {track.get('escalation_step', 'unknown')}"
        elif outcome == "pushed_back":
            recovery_path = "customer pushed back, not recovered"
        elif "EXCEPTION" in outcome:
            recovery_path = f"exception during response simulation: {outcome}"

    elif final_action in ("human_handoff", "deferred"):
        recovery_path = f"blocked by compliance gate -> {gate_row.get('gate_reason', '')}"

    if recovered:
        total_recovered += amount

    per_payment_rows.append({
        "payment_id": pid,
        "amount": amount,
        "final_action": final_action,
        "chosen_tone": chosen_tone,
        "recovered": recovered,
        "recovery_path": recovery_path,
    })

# --- write per-payment detail file ---
with open(pipeline.data_path("metrics_by_payment.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(per_payment_rows[0].keys()))
    writer.writeheader()
    writer.writerows(per_payment_rows)

# --- recovery rate by tone (only among payments that got a real message) ---
tone_stats = defaultdict(lambda: {
    "total": 0, "recovered": 0, "amount_total": Decimal("0"), "amount_recovered": Decimal("0"),
})
for row in per_payment_rows:
    if row["chosen_tone"] and row["final_action"] in MESSAGING_ACTIONS:
        t = row["chosen_tone"]
        tone_stats[t]["total"] += 1
        tone_stats[t]["amount_total"] += row["amount"]
        if row["recovered"]:
            tone_stats[t]["recovered"] += 1
            tone_stats[t]["amount_recovered"] += row["amount"]

tone_breakdown = {}
for tone, stats in tone_stats.items():
    rate = (stats["recovered"] / stats["total"] * 100) if stats["total"] else 0
    tone_breakdown[tone] = {
        "messages_sent": stats["total"],
        "recovered_count": stats["recovered"],
        "recovery_rate_pct": round(rate, 1),
        "amount_at_risk": to_float(stats["amount_total"]),
        "amount_recovered": to_float(stats["amount_recovered"]),
    }

# --- exceptions / blocked list (the honest part) ---
blocked = [r for r in per_payment_rows if "blocked by compliance gate" in r["recovery_path"]]
exceptions = [r for r in per_payment_rows if "exception" in r["recovery_path"].lower()]

# --- overall summary ---
overall_recovery_rate = (
    round(float(total_recovered / total_at_risk * 100), 1) if total_at_risk else 0
)

summary = {
    "total_payments": len(all_payments),
    "total_amount_at_risk": to_float(total_at_risk),
    "total_amount_recovered": to_float(total_recovered),
    "overall_recovery_rate_pct": overall_recovery_rate,
    "recovery_rate_by_tone": tone_breakdown,
    "blocked_by_compliance_count": len(blocked),
    "exceptions_count": len(exceptions),
    "assumptions": {
        "promise_keep_rate_source": "varies by customer past_payment_behavior — see promise_tracker.py KEEP_RATE_BY_BEHAVIOR",
        "auto_retry_note": "auto_retry actions are excluded from recovery-rate metrics — they're a technical fix, not a customer-facing recovery intervention",
    },
}

with open(pipeline.data_path("metrics_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

# --- print report ---
print("=" * 50)
print("REVENUE RECOVERY — MEASURED RESULTS")
print("=" * 50)
print(f"Total payments processed: {summary['total_payments']}")
print(f"Total ₹ at risk: ₹{summary['total_amount_at_risk']:,.2f}")
print(f"Total ₹ recovered: ₹{summary['total_amount_recovered']:,.2f}")
print(f"Overall recovery rate: {summary['overall_recovery_rate_pct']}%")
print(f"\nBlocked by compliance gate: {summary['blocked_by_compliance_count']}")
print(f"Exceptions: {summary['exceptions_count']}")
print("\n--- Recovery rate BY TONE (the headline chart) ---")
for tone, stats in tone_breakdown.items():
    print(f"  {tone}: {stats['recovery_rate_pct']}% "
          f"({stats['recovered_count']}/{stats['messages_sent']} messages, "
          f"₹{stats['amount_recovered']:,.0f} recovered)")
print(f"\n✅ Full report written to data/metrics_summary.json")
print(f"✅ Per-payment detail written to data/metrics_by_payment.csv")