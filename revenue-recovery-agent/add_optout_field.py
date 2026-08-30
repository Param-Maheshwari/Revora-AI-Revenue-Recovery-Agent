"""
add_optout_field.py — one-time script that adds an 'opted_out' column to
data/customers.csv, marking ~10% of customers as opted out of messaging.
This gives the compliance gate a real condition to enforce and demonstrate.

Run with: python add_optout_field.py
"""

import csv
import random

random.seed(7)

with open("data/customers.csv", newline="", encoding="utf-8") as f:
    customers = list(csv.DictReader(f))

for c in customers:
    c["opted_out"] = "True" if random.random() < 0.10 else "False"

fieldnames = list(customers[0].keys())
with open("data/customers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(customers)

opted_out_count = sum(1 for c in customers if c["opted_out"] == "True")
print(f"✅ Updated data/customers.csv — {opted_out_count}/{len(customers)} customers marked opted_out")