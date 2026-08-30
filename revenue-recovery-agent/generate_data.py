"""
generate_data.py — creates synthetic payments.csv and customers.csv
for the Revenue Recovery Agent project.

Run with: python3 generate_data.py
Outputs: data/payments.csv, data/customers.csv
"""

import csv
import os
import random
from datetime import datetime, timedelta

random.seed(99)

os.makedirs("data", exist_ok=True)

# ---------- CONFIG ----------
NUM_CUSTOMERS = 60
NUM_PAYMENTS = 150

FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan",
               "Neha", "Karan", "Divya", "Arjun", "Pooja", "Suresh", "Meera",
               "Aditya", "Kavita", "Manish", "Ritu", "Sanjay", "Nisha"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Gupta", "Reddy", "Iyer", "Nair",
              "Singh", "Kumar", "Joshi", "Rao", "Mehta", "Das", "Kapoor"]

# messy, realistic-looking raw failure reasons an LLM will have to interpret
FAILURE_REASONS_RAW = {
    "transient": [
        "gateway timeout - please retry",
        "issuing bank not responding, error 91",
        "network error during authorization",
        "temporary decline, code 96 - system malfunction",
    ],
    "customer_action_needed": [
        "card expired",
        "invalid CVV entered",
        "card reported as expired by issuer",
        "authentication failed - OTP not entered in time",
    ],
    "risk_flag": [
        "declined by issuing bank - do not honor, code 05",
        "insufficient funds - code 51",
        "insufficient funds, repeated attempt",
        "transaction flagged for suspected fraud",
    ],
}

FORMALITY = ["formal", "casual", "neutral"]
BEHAVIOR = ["usually pays on time", "usually pays late", "first-time failure", "frequent failures"]

# ---------- CUSTOMERS ----------
customers = []
for i in range(1, NUM_CUSTOMERS + 1):
    cust_id = f"CUST{i:04d}"
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    customers.append({
        "customer_id": cust_id,
        "name": name,
        "formality_preference": random.choice(FORMALITY),
        "past_payment_behavior": random.choices(
            BEHAVIOR, weights=[0.4, 0.25, 0.2, 0.15]
        )[0],
        "contact_preference": random.choice(["sms", "email", "sms"]),  # sms weighted more common
    })

with open("data/customers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=customers[0].keys())
    writer.writeheader()
    writer.writerows(customers)

# ---------- PAYMENTS ----------
base_date = datetime(2026, 8, 1)
payments = []

for i in range(1, NUM_PAYMENTS + 1):
    pay_id = f"PAY{i:05d}"
    cust = random.choice(customers)

    # weighted category so it's not evenly split — mirrors real-world skew
    category = random.choices(
        ["transient", "customer_action_needed", "risk_flag"],
        weights=[0.45, 0.30, 0.25]
    )[0]
    raw_reason = random.choice(FAILURE_REASONS_RAW[category])

    amount = round(random.uniform(199, 4999), 2)
    retry_count = random.choices([0, 1, 2, 3], weights=[0.4, 0.3, 0.2, 0.1])[0]
    days_ago = random.randint(0, 20)
    timestamp = (base_date + timedelta(days=days_ago)).strftime("%Y-%m-%d")

    is_subscription = random.random() < 0.4
    sub_id = f"SUB{random.randint(1, 30):04d}" if is_subscription else ""

    payments.append({
        "payment_id": pay_id,
        "customer_id": cust["customer_id"],
        "amount": amount,
        "status": "failed",
        "failure_reason_raw": raw_reason,
        "true_category": category,  # kept for OUR evaluation later, not shown to the LLM
        "retry_count": retry_count,
        "timestamp": timestamp,
        "subscription_id": sub_id,
    })

with open("data/payments.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=payments[0].keys())
    writer.writeheader()
    writer.writerows(payments)

print(f"✅ Generated {len(customers)} customers → data/customers.csv")
print(f"✅ Generated {len(payments)} payments → data/payments.csv")
print("\nCategory breakdown:")
from collections import Counter
counts = Counter(p["true_category"] for p in payments)
for cat, count in counts.items():
    print(f"  {cat}: {count} ({count/len(payments)*100:.0f}%)")