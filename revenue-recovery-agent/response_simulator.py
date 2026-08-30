"""
response_simulator.py — reads data/final_messages.csv, and for every
payment that actually got a message, simulates a realistic CUSTOMER REPLY
using an LLM persona (based on their profile + the message they received),
then in the SAME call extracts structured info: did they pay, promise a
date, or ignore it — AND, if they promised, how firm/specific that
promise sounds (used later by promise_tracker.py to weight whether it
actually gets kept).

Writes data/simulated_responses.csv

Requires: GEMINI_API_KEY in .env

Run with: python response_simulator.py
"""

import os
import csv
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

MODEL_CANDIDATES = [
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]

INPUT_FILE = "data/final_messages.csv"
OUTPUT_FILE = "data/simulated_responses.csv"

MESSAGING_ACTIONS = {"send_soft_reminder", "send_update_reminder", "offer_payment_plan"}

OUTCOMES = ["paid_immediately", "promised_later", "ignored", "pushed_back"]

PERSONA_PROMPT = """You are simulating how a REAL Indian customer would react to receiving this payment recovery message. Be realistic and varied — not every customer responds well, and tone genuinely matters to how people react.

Customer profile:
- Past payment behavior: {behavior}
- Formality preference: {formality}

Message they received (tone: {tone}):
"{message}"

Simulate ONE realistic reply this customer might send back (in Hinglish, matching how a real person would text — can be short). Consider: a customer with "frequent failures" behavior might be more likely to ignore or push back on a formal/pushy tone but respond better to empathetic tone. A customer who "usually pays on time" is more likely to pay quickly regardless of tone.

Then classify the outcome into exactly one of: {outcomes}
- paid_immediately: they say they've paid or will pay right now
- promised_later: they commit to a specific future date/time
- ignored: reply doesn't commit to anything concrete, or is vague
- pushed_back: they express annoyance, confusion, or refuse

If promised_later, extract the promise as a short date/timeframe description, AND rate how firm/specific the commitment sounds:
- "high": specific date/trigger given confidently (e.g. "5 tareek ko salary aayegi tabhi kar dunga", "kal subah kar dunga")
- "medium": some commitment but a bit vague (e.g. "is week mein kar dunga")
- "low": vague, non-committal, likely to slip (e.g. "jald hi kar dunga", "dekhta hu")
If outcome is not promised_later, set commitment_strength to "".

Respond with ONLY valid JSON, no markdown, in this exact format:
{{"customer_reply": "the simulated reply text", "outcome": "one_of_the_outcomes", "promised_date": "date/timeframe if promised_later, else empty string", "commitment_strength": "high/medium/low if promised_later, else empty string"}}
"""


def pick_working_model():
    for candidate in MODEL_CANDIDATES:
        try:
            print(f"Trying model: {candidate} ...")
            client.models.generate_content(model=candidate, contents="hi")
            print(f"✅ Using model: {candidate}\n")
            return candidate
        except genai_errors.ClientError as e:
            if "NOT_FOUND" in str(e) or "404" in str(e):
                print(f"  ✗ {candidate} not available, trying next...")
                continue
            elif "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print(f"  ✗ {candidate} quota exhausted, trying next...")
                continue
            else:
                raise
    raise RuntimeError("No working Gemini model found.")


def simulate_response(model, behavior, formality, tone, message, max_retries=4):
    prompt = PERSONA_PROMPT.format(
        behavior=behavior, formality=formality, tone=tone,
        message=message, outcomes=", ".join(OUTCOMES)
    )
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = json.loads(text)
            if result.get("outcome") not in OUTCOMES:
                result["outcome"] = "ignored"
            result.setdefault("commitment_strength", "")
            return result
        except genai_errors.ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                wait = 20 * (attempt + 1)
                print(f"    ⏳ Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
        except (json.JSONDecodeError, KeyError):
            return {"customer_reply": "", "outcome": "EXCEPTION_PARSE_FAILED", "promised_date": "", "commitment_strength": ""}
    return {"customer_reply": "", "outcome": "EXCEPTION_RATE_LIMITED", "promised_date": "", "commitment_strength": ""}


def load_already_done():
    if not os.path.exists(OUTPUT_FILE):
        return set(), []
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    done_ids = {r["payment_id"] for r in rows}
    return done_ids, rows


def main():
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        all_messages = list(csv.DictReader(f))

    with open("data/customers.csv", newline="", encoding="utf-8") as f:
        customers = {c["customer_id"]: c for c in csv.DictReader(f)}

    needs_response = [r for r in all_messages if r["final_action"] in MESSAGING_ACTIONS]

    done_ids, _ = load_already_done()
    remaining = [r for r in needs_response if r["payment_id"] not in done_ids]

    if not remaining:
        print("✅ All responses already simulated. Nothing to do.")
        return

    print(f"{len(done_ids)} already done. Simulating responses for remaining {len(remaining)} of {len(needs_response)} messaged payments...\n")

    model = pick_working_model()
    file_exists = os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = None

        for i, row in enumerate(remaining, 1):
            cust = customers.get(row["customer_id"], {})
            sim = simulate_response(
                model=model,
                behavior=cust.get("past_payment_behavior", "unknown"),
                formality=cust.get("formality_preference", "neutral"),
                tone=row["chosen_tone"],
                message=row["message"],
            )

            out_row = {
                "payment_id": row["payment_id"],
                "customer_id": row["customer_id"],
                "amount": row["amount"],
                "predicted_category": row["predicted_category"],
                "final_action": row["final_action"],
                "chosen_tone": row["chosen_tone"],
                "customer_reply": sim["customer_reply"],
                "outcome": sim["outcome"],
                "promised_date": sim["promised_date"],
                "commitment_strength": sim.get("commitment_strength", ""),
            }

            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(out_row.keys()))
                if not file_exists:
                    writer.writeheader()

            writer.writerow(out_row)
            f.flush()

            print(f"[{i}/{len(remaining)}] {row['payment_id']} ({row['chosen_tone']}): {sim['outcome']} "
                  f"{'(' + sim['commitment_strength'] + ')' if sim.get('commitment_strength') else ''}")
            time.sleep(2)

    _, all_rows = load_already_done()
    from collections import Counter
    outcome_counts = Counter(r["outcome"] for r in all_rows)
    print(f"\n✅ Done. {len(all_rows)}/{len(needs_response)} responses simulated → {OUTPUT_FILE}")
    print("\nOutcome breakdown:")
    for outcome, count in outcome_counts.items():
        print(f"  {outcome}: {count}")


if __name__ == "__main__":
    main()