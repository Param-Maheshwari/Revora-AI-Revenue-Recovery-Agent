"""
intervention_chooser.py — reads data/diagnosed_payments.csv, decides a
recovery ACTION and message TONE for each payment (using local Mistral),
and writes results to data/interventions.csv

This does NOT generate the actual message text yet — that's a separate
step (message_generator.py) so we only call Gemini for unique
category+tone combos instead of once per payment.

Run with: python intervention_chooser.py
"""

import os
import csv
import json
import time
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"

OUTPUT_FILE = "data/interventions.csv"

# Fixed, allowed action list — the LLM must pick from these, never invent one.
# This matters for the compliance/audit story: bounded action space = safer.
ACTIONS = [
    "auto_retry",          # transient failures — just retry the payment, no customer contact
    "send_update_reminder",  # customer_action_needed — ask them to update card/details
    "send_soft_reminder",   # risk_flag, first-time — gentle nudge, no pressure
    "offer_payment_plan",   # risk_flag, repeated failures — offer flexibility instead of pushing
]

TONES = ["formal", "casual", "empathetic"]

CHOOSER_PROMPT = """You are a revenue-recovery agent deciding how to handle a failed payment.

Payment details:
- Diagnosed category: {category}
- Diagnosis reasoning: {reasoning}
- Customer's past payment behavior: {behavior}
- Customer's stated formality preference: {formality}
- Retry count so far: {retry_count}
- Amount: Rs {amount}

Choose exactly ONE action from this list: {actions}
Choose exactly ONE tone from this list: {tones}

Rules of thumb:
- transient failures should almost always be auto_retry (no customer contact needed)
- customer_action_needed should get send_update_reminder
- risk_flag with low retry_count should get send_soft_reminder (never pushy)
- risk_flag with high retry_count (2+) should get offer_payment_plan (be flexible, not aggressive)
- Match tone to the customer's stated preference when possible, but use "empathetic" if their behavior shows repeated struggles

Respond with ONLY valid JSON, no markdown, in this exact format:
{{"action": "one_of_the_actions", "tone": "one_of_the_tones", "reasoning": "one short sentence why"}}
"""


def check_ollama_running():
    try:
        requests.get("http://localhost:11434", timeout=3)
        return True
    except requests.exceptions.ConnectionError:
        return False


def choose_intervention(category, reasoning, behavior, formality, retry_count, amount, max_retries=3):
    prompt = CHOOSER_PROMPT.format(
        category=category, reasoning=reasoning, behavior=behavior,
        formality=formality, retry_count=retry_count, amount=amount,
        actions=", ".join(ACTIONS), tones=", ".join(TONES),
    )

    for attempt in range(max_retries):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json"},
                timeout=60,
            )
            response.raise_for_status()
            text = response.json()["response"].strip()

            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            try:
                result = json.loads(text)
                if result.get("action") not in ACTIONS:
                    result["action"] = "send_soft_reminder"  # safe fallback
                if result.get("tone") not in TONES:
                    result["tone"] = "empathetic"  # safe fallback
                return result
            except json.JSONDecodeError:
                return {"action": "EXCEPTION_PARSE_FAILED", "tone": "empathetic", "reasoning": f"raw: {text[:100]}"}

        except requests.exceptions.RequestException as e:
            print(f"    ⚠️  Request error (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(3)
            continue

    return {"action": "EXCEPTION_REQUEST_FAILED", "tone": "empathetic", "reasoning": "gave up after max retries"}


def load_already_done():
    if not os.path.exists(OUTPUT_FILE):
        return set(), []
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    done_ids = {r["payment_id"] for r in rows}
    return done_ids, rows


def main():
    if not check_ollama_running():
        print("❌ Ollama doesn't seem to be running. Open the Ollama app and try again.")
        return

    with open("data/diagnosed_payments.csv", newline="", encoding="utf-8") as f:
        diagnosed = list(csv.DictReader(f))

    with open("data/customers.csv", newline="", encoding="utf-8") as f:
        customers = {c["customer_id"]: c for c in csv.DictReader(f)}

    done_ids, _ = load_already_done()
    remaining = [p for p in diagnosed if p["payment_id"] not in done_ids]

    if not remaining:
        print("✅ All payments already have interventions chosen. Nothing to do.")
        return

    print(f"{len(done_ids)} already done. Choosing interventions for remaining {len(remaining)} payments...\n")

    file_exists = os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = None

        for i, p in enumerate(remaining, 1):
            cust = customers.get(p["customer_id"], {})
            decision = choose_intervention(
                category=p["predicted_category"],
                reasoning=p["diagnosis_reasoning"],
                behavior=cust.get("past_payment_behavior", "unknown"),
                formality=cust.get("formality_preference", "neutral"),
                retry_count=p["retry_count"],
                amount=p["amount"],
            )

            row = {
                "payment_id": p["payment_id"],
                "customer_id": p["customer_id"],
                "predicted_category": p["predicted_category"],
                "amount": p["amount"],
                "chosen_action": decision["action"],
                "chosen_tone": decision["tone"],
                "chooser_reasoning": decision["reasoning"],
            }

            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not file_exists:
                    writer.writeheader()

            writer.writerow(row)
            f.flush()

            print(f"[{i}/{len(remaining)}] {p['payment_id']}: {decision['action']} / {decision['tone']}")

    _, all_rows = load_already_done()
    exceptions = sum(1 for r in all_rows if "EXCEPTION" in r["chosen_action"])
    print(f"\n✅ Done. {len(all_rows)}/{len(diagnosed)} total → {OUTPUT_FILE}")
    print(f"Exceptions: {exceptions}")

    # quick breakdown for sanity check
    from collections import Counter
    action_counts = Counter(r["chosen_action"] for r in all_rows)
    print("\nAction breakdown:")
    for action, count in action_counts.items():
        print(f"  {action}: {count}")


if __name__ == "__main__":
    main()