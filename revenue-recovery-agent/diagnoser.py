"""
diagnoser.py — reads data/payments.csv, asks a LOCAL Ollama model (Mistral)
to diagnose the root cause of each failure, and writes results to
data/diagnosed_payments.csv

Requires: Ollama running locally with mistral pulled (you already have this).
Make sure the Ollama app/service is running before you run this script —
on Windows, just open the Ollama app once, it runs in the background.

RESUMABLE: if it stops partway (crash, etc.), just run it again — it
skips payments already diagnosed and continues from there.

Run with: python diagnoser.py
"""

import os
import csv
import json
import time
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"

CATEGORIES = ["transient", "customer_action_needed", "risk_flag"]
OUTPUT_FILE = "data/diagnosed_payments.csv"

DIAGNOSER_PROMPT = """You are a payment-failure diagnosis agent for an Indian fintech company.

Given a raw payment failure reason, classify it into EXACTLY ONE of these categories:
- transient: temporary/technical issue, safe to auto-retry (timeouts, network errors, temporary bank-side glitches)
- customer_action_needed: the customer needs to do something (expired card, wrong CVV, OTP not entered)
- risk_flag: repeated failures or fraud/insufficient-funds signals that need a softer, non-pushy approach

Context:
- Raw failure reason: "{raw_reason}"
- Retry count so far: {retry_count}
- Payment amount: Rs {amount}

Respond with ONLY valid JSON, no markdown, no extra text, in this exact format:
{{"category": "one_of_the_three_categories_above", "reasoning": "one short sentence explaining why"}}
"""


def check_ollama_running():
    try:
        requests.get("http://localhost:11434", timeout=3)
        return True
    except requests.exceptions.ConnectionError:
        return False


def diagnose(raw_reason, retry_count, amount, max_retries=3):
    prompt = DIAGNOSER_PROMPT.format(
        raw_reason=raw_reason, retry_count=retry_count, amount=amount
    )

    for attempt in range(max_retries):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",  # ask Ollama to constrain output to JSON
                },
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
                if result.get("category") not in CATEGORIES:
                    result["category"] = "risk_flag"
                return result
            except json.JSONDecodeError:
                return {"category": "EXCEPTION_PARSE_FAILED", "reasoning": f"raw response: {text[:100]}"}

        except requests.exceptions.RequestException as e:
            print(f"    ⚠️  Request error (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(3)
            continue

    return {"category": "EXCEPTION_REQUEST_FAILED", "reasoning": "gave up after max retries"}


def load_already_done():
    if not os.path.exists(OUTPUT_FILE):
        return set(), []
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    done_ids = {r["payment_id"] for r in rows}
    return done_ids, rows


def main():
    if not check_ollama_running():
        print("❌ Ollama doesn't seem to be running.")
        print("   Open the Ollama app (or run 'ollama serve' in a terminal) and try again.")
        return

    with open("data/payments.csv", newline="", encoding="utf-8") as f:
        all_payments = list(csv.DictReader(f))

    done_ids, _ = load_already_done()
    remaining = [p for p in all_payments if p["payment_id"] not in done_ids]

    if not remaining:
        print("✅ All payments already diagnosed. Nothing to do.")
        return

    print(f"{len(done_ids)} already done. Diagnosing remaining {len(remaining)} payments using local Mistral...\n")

    file_exists = os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = None

        for i, p in enumerate(remaining, 1):
            diagnosis = diagnose(p["failure_reason_raw"], p["retry_count"], p["amount"])

            predicted = diagnosis["category"]
            true_cat = p["true_category"]
            is_correct = predicted == true_cat

            p["predicted_category"] = predicted
            p["diagnosis_reasoning"] = diagnosis["reasoning"]
            p["diagnosis_correct"] = is_correct

            if writer is None:
                fieldnames = list(p.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()

            writer.writerow(p)
            f.flush()

            mark = "✓" if is_correct else f"✗ expected {true_cat}"
            print(f"[{i}/{len(remaining)}] {p['payment_id']}: {predicted} ({mark})")

    _, all_rows = load_already_done()
    correct = sum(1 for r in all_rows if r["diagnosis_correct"] == "True")
    exceptions = sum(1 for r in all_rows if "EXCEPTION" in r["predicted_category"])
    accuracy = correct / len(all_rows) * 100

    print(f"\n✅ Done. {len(all_rows)}/{len(all_payments)} total diagnosed → {OUTPUT_FILE}")
    print(f"Accuracy: {correct}/{len(all_rows)} ({accuracy:.1f}%)")
    print(f"Exceptions: {exceptions}")


if __name__ == "__main__":
    main()