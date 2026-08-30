"""
message_generator.py — reads data/gated_actions.csv, finds unique
(action, tone) combinations that need a customer-facing message,
generates a natural Hinglish message for EACH COMBO ONCE using Gemini
(not per-payment — keeps API calls low), then maps every payment to its
matching message.

Writes data/final_messages.csv — the final output: one row per payment
with the actual message text (or a note on why none was sent).

Requires: GEMINI_API_KEY in .env (same as your earlier test.py setup)

Run with: python message_generator.py
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

GATED_FILE = "data/gated_actions.csv"
OUTPUT_FILE = "data/final_messages.csv"

# Only these actions produce a customer-facing message
MESSAGING_ACTIONS = {"send_soft_reminder", "send_update_reminder", "offer_payment_plan"}

ACTION_DESCRIPTIONS = {
    "send_soft_reminder": "a gentle, low-pressure reminder that their payment failed — no urgency, no pressure",
    "send_update_reminder": "a reminder asking them to update their card/payment details since the failure needs their action",
    "offer_payment_plan": "an offer to split the payment into a more flexible plan, since they've had repeated failures — be understanding, not pushy",
}

MESSAGE_PROMPT = """Write a short payment recovery message for an Indian customer, in natural Hinglish (Roman script — casual code-mixed Hindi-English, like a real Indian would text, NOT pure Hindi or pure English).

Context: {action_description}
Tone to use: {tone} (formal = respectful and professional; casual = friendly and relaxed; empathetic = warm and understanding, especially for someone who may be struggling)

Keep it to 1-2 sentences, suitable for an SMS. Use placeholder {{amount}} for the payment amount and {{name}} for the customer's name where natural.

Respond with ONLY valid JSON, no markdown, in this exact format:
{{"message": "the message text here"}}
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
    raise RuntimeError("No working Gemini model found. Check your quota or model list.")


def generate_message(model, action, tone, max_retries=3):
    prompt = MESSAGE_PROMPT.format(
        action_description=ACTION_DESCRIPTIONS[action], tone=tone
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
            return result["message"]
        except genai_errors.ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                wait = 20 * (attempt + 1)
                print(f"    ⏳ Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def main():
    with open(GATED_FILE, newline="", encoding="utf-8") as f:
        gated = list(csv.DictReader(f))

    with open("data/customers.csv", newline="", encoding="utf-8") as f:
        customers = {c["customer_id"]: c for c in csv.DictReader(f)}

    # find unique (action, tone) combos that actually need a message
    unique_combos = set()
    for row in gated:
        if row["final_action"] in MESSAGING_ACTIONS:
            unique_combos.add((row["final_action"], row["chosen_tone"]))

    print(f"Found {len(unique_combos)} unique action+tone combos needing messages.\n")

    model = pick_working_model()

    # generate one template message per combo
    templates = {}
    for i, (action, tone) in enumerate(sorted(unique_combos), 1):
        print(f"[{i}/{len(unique_combos)}] Generating: {action} / {tone} ...")
        message = generate_message(model, action, tone)
        if message is None:
            message = "[EXCEPTION: message generation failed for this combo]"
        templates[(action, tone)] = message
        print(f"    → {message}")
        time.sleep(2)

    # map every payment to its message, filling in name/amount
    results = []
    for row in gated:
        cust = customers.get(row["customer_id"], {})
        name = cust.get("name", "Customer")
        amount = row["amount"]

        if row["final_action"] in MESSAGING_ACTIONS:
            template = templates.get((row["final_action"], row["chosen_tone"]), "")
            message = template.replace("{name}", name).replace("{amount}", f"₹{amount}")
        else:
            message = f"[no message sent — final_action = {row['final_action']}]"

        results.append({
            "payment_id": row["payment_id"],
            "customer_id": row["customer_id"],
            "customer_name": name,
            "amount": amount,
            "predicted_category": row["predicted_category"],
            "final_action": row["final_action"],
            "chosen_tone": row["chosen_tone"],
            "gate_status": row["gate_status"],
            "gate_reason": row["gate_reason"],
            "message": message,
        })

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✅ Done. {len(results)} payments processed → {OUTPUT_FILE}")
    print(f"Unique messages generated: {len(templates)} (instead of {len(results)} — saved API calls)")


if __name__ == "__main__":
    main()