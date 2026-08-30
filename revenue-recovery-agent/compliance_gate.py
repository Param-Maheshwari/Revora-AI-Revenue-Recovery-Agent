"""
compliance_gate.py — reads data/interventions.csv, enforces hard
deterministic rules (NO AI here on purpose — compliance must be
predictable, not model-decided), and writes the final gated decision
to data/gated_actions.csv

Rules enforced:
1. Max 3 messaging attempts per customer -> 4th+ forced to human_handoff
   (auto_retry doesn't count as a "contact", it's silent)
2. No messaging outside 9 AM - 8 PM window
3. Opted-out customers never get messaged, forced to human_handoff instead
4. Every decision (allowed or blocked) is logged with a clear reason
   -> this IS your audit trail

The rules themselves live in pipeline.compliance_check — ONE
implementation, called by this batch script and by the live per-row path
in live_processor.py. That is deliberate: the moment compliance logic is
written twice, the two copies drift, and a rule that holds in the demo
stops holding in the batch (or vice versa). Tests in tests/ assert the
rules and their precedence directly against that shared function.

IMPORTANT: the time-window check uses a SIMULATED per-payment attempt
hour, NOT your computer's real clock. This is intentional — a rule that
depends on what time you happen to run the script would make results
different every run and undemonstrable in a demo. The hour is derived
from a hash of the payment_id (see pipeline.simulated_attempt_hour), so
it is stable across runs, unaffected by row order or resumption, and
identical to the hour the live path assigns the same payment.

Run with: python compliance_gate.py
"""

import csv
from collections import defaultdict

import pipeline

MAX_CONTACT_ATTEMPTS = pipeline.MAX_CONTACT_ATTEMPTS
MESSAGING_ACTIONS = pipeline.MESSAGING_ACTIONS
WINDOW_START_HOUR = pipeline.WINDOW_START_HOUR
WINDOW_END_HOUR = pipeline.WINDOW_END_HOUR

INPUT_FILE = pipeline.data_path("interventions.csv")
CUSTOMERS_FILE = pipeline.data_path("customers.csv")
OUTPUT_FILE = pipeline.data_path("gated_actions.csv")


def load_customers():
    with open(CUSTOMERS_FILE, newline="", encoding="utf-8") as f:
        return {c["customer_id"]: c for c in csv.DictReader(f)}


def main():
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        interventions = list(csv.DictReader(f))

    customers = load_customers()

    contact_counts = defaultdict(int)  # actual contacts MADE per customer_id

    results = []

    for row in interventions:
        cust_id = row["customer_id"]
        cust = customers.get(cust_id, {})
        action = row["chosen_action"]

        attempt_hour = pipeline.simulated_attempt_hour(row["payment_id"])

        gate = pipeline.compliance_check(
            action=action,
            opted_out=cust.get("opted_out") == "True",
            contact_count_so_far=contact_counts[cust_id],
            within_window=pipeline.is_within_window(attempt_hour),
            attempt_hour=attempt_hour,
        )

        # Only a contact that was actually ALLOWED counts against the cap —
        # a blocked attempt was never delivered to the customer.
        if gate["status"] == "ALLOWED" and action in MESSAGING_ACTIONS:
            contact_counts[cust_id] += 1

        results.append({
            "payment_id": row["payment_id"],
            "customer_id": cust_id,
            "amount": row["amount"],
            "predicted_category": row["predicted_category"],
            "chosen_action": action,
            "chosen_tone": row["chosen_tone"],
            "final_action": gate["final_action"],
            "gate_status": gate["status"],
            "gate_reason": gate["reason"],
            "simulated_attempt_hour": attempt_hour,
        })

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    allowed = sum(1 for r in results if r["gate_status"] == "ALLOWED")
    blocked = sum(1 for r in results if r["gate_status"] == "BLOCKED")

    print(f"✅ Done. {len(results)} actions gated → {OUTPUT_FILE}")
    print(f"Allowed: {allowed}")
    print(f"Blocked: {blocked}")

    print("\nBlocked reasons breakdown:")
    from collections import Counter
    blocked_reasons = Counter(
        r["gate_reason"].split(" — simulated")[0] for r in results if r["gate_status"] == "BLOCKED"
    )
    for reason, count in blocked_reasons.items():
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()