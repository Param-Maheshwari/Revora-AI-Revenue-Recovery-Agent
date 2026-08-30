"""
promise_tracker.py — reads data/simulated_responses.csv, and for every
"promised_later" outcome, simulates whether the promise gets KEPT or
BROKEN.

The keep-probability is now TWO-FACTOR, not just behavior-based:
1. A baseline rate from the customer's past_payment_behavior (as before)
2. An adjustment based on how firm/specific their promise actually
   sounded (commitment_strength, extracted by response_simulator.py from
   their reply text) — a confident, specific promise shifts the odds up,
   a vague one shifts them down.

This means the customer's actual reply text now genuinely influences
whether their promise is modeled as kept, not just their historical
label — closing a gap where the two were previously disconnected.

Broken promises get escalated per a compliant ladder with a hard stop.

Writes data/tracked_promises.csv

Run with: python promise_tracker.py
"""

import csv
import random

random.seed(21)

INPUT_FILE = "data/simulated_responses.csv"
OUTPUT_FILE = "data/tracked_promises.csv"

# Baseline keep-rate by behavior — our stated assumption (documented here
# + in README).
KEEP_RATE_BY_BEHAVIOR = {
    "usually pays on time": 0.85,
    "first-time failure": 0.65,
    "usually pays late": 0.45,
    "frequent failures": 0.25,
}
DEFAULT_KEEP_RATE = 0.5

# How much the LLM's read on commitment firmness shifts the baseline,
# up or down. Clamped later so the final rate stays in a sane 5-95% range.
COMMITMENT_ADJUSTMENT = {
    "high": 0.15,
    "medium": 0.0,
    "low": -0.15,
    "": 0.0,  # no signal extracted — fall back to baseline only
}

ESCALATION_LADDER = ["reminder", "second_reminder", "human_handoff"]
MAX_ESCALATION_STEPS = len(ESCALATION_LADDER)


def main():
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        responses = list(csv.DictReader(f))

    with open("data/customers.csv", newline="", encoding="utf-8") as f:
        customers = {c["customer_id"]: c for c in csv.DictReader(f)}

    results = []

    for row in responses:
        if row["outcome"] != "promised_later":
            results.append({
                **row,
                "promise_kept": "N/A",
                "escalation_step": "N/A",
                "baseline_rate_from_behavior": "",
                "adjustment_applied": "",
                "final_keep_probability_used": "",
            })
            continue

        cust = customers.get(row["customer_id"], {})
        behavior = cust.get("past_payment_behavior", "unknown")
        commitment_strength = row.get("commitment_strength", "")

        baseline_rate = KEEP_RATE_BY_BEHAVIOR.get(behavior, DEFAULT_KEEP_RATE)
        adjustment = COMMITMENT_ADJUSTMENT.get(commitment_strength, 0.0)
        final_rate = min(0.95, max(0.05, baseline_rate + adjustment))

        promise_kept = random.random() < final_rate

        if promise_kept:
            escalation_step = "N/A — promise kept, no escalation needed"
        else:
            escalation_step = ESCALATION_LADDER[0]

        results.append({
            **row,
            "promise_kept": str(promise_kept),
            "escalation_step": escalation_step,
            "baseline_rate_from_behavior": baseline_rate,
            "adjustment_applied": adjustment,
            "final_keep_probability_used": round(final_rate, 2),
        })

    fieldnames = list(results[0].keys())
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    promised = [r for r in results if r["outcome"] == "promised_later"]
    kept = sum(1 for r in promised if r["promise_kept"] == "True")
    broken = sum(1 for r in promised if r["promise_kept"] == "False")

    print(f"✅ Done. {len(results)} rows processed → {OUTPUT_FILE}")
    print(f"Promises made: {len(promised)}")
    print(f"  Kept: {kept}")
    print(f"  Broken (escalated to '{ESCALATION_LADDER[0]}'): {broken}")

    from collections import Counter
    strength_counts = Counter(r["commitment_strength"] for r in promised if r["commitment_strength"])
    if strength_counts:
        print("\nCommitment strength breakdown (of promises made):")
        for strength, count in strength_counts.items():
            print(f"  {strength}: {count}")


if __name__ == "__main__":
    main()