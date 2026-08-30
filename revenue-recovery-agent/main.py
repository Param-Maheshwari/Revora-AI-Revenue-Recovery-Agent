"""
main.py — FastAPI backend serving the Revenue Recovery Agent's pipeline
output to the frontend dashboard.

Reads all the CSV/JSON files produced by the pipeline scripts (Days 1-2)
into memory at startup, and exposes them via a clean REST API.

Run with: uvicorn main:app --reload
Then visit http://localhost:8000/docs for interactive API docs (FastAPI
auto-generates this — genuinely useful for testing endpoints by hand).
"""

import csv
import os
import json
from collections import defaultdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import pipeline
from live_processor import router as live_router

app = FastAPI(title="Revora — AI Revenue Recovery Agent API")

# Defaults to the local Next.js dev server; set ALLOWED_ORIGINS to a
# comma-separated list to point at a deployed frontend. "*" is deliberately not
# the default — with credentials-free GETs it is still an invitation for any
# page on the internet to read this API from a visitor's browser.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(live_router)


def load_csv(filename):
    """Missing pipeline output degrades to an empty dataset instead of raising.

    These loads run at import time, so a FileNotFoundError here stopped
    `uvicorn main:app` from starting at all — including /docs and the live
    endpoint, neither of which needs batch data.
    """
    try:
        with open(pipeline.data_path(filename), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"⚠️  data/{filename} not found — run the batch pipeline to populate it.")
        return []


def load_csv_dict(filename, key="payment_id"):
    return {row[key]: row for row in load_csv(filename) if row.get(key)}


def load_metrics_summary():
    try:
        with open(pipeline.data_path("metrics_summary.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("⚠️  data/metrics_summary.json not found — run metrics_engine.py to populate it.")
        return {}


# --- Load everything once at startup (data is small, no need for a real DB) ---
payments = load_csv("payments.csv")
diagnosed = load_csv_dict("diagnosed_payments.csv")
interventions = load_csv_dict("interventions.csv")
gated = load_csv_dict("gated_actions.csv")
messages = load_csv_dict("final_messages.csv")
responses = load_csv_dict("simulated_responses.csv")
tracked = load_csv_dict("tracked_promises.csv")
metrics_rows = load_csv_dict("metrics_by_payment.csv")
customers = load_csv_dict("customers.csv", key="customer_id")

metrics_summary = load_metrics_summary()


def build_full_trace(payment_id: str):
    """Assembles the complete agent journey for one payment, stage by
    stage — this is what powers the live agent-trace view."""
    base = next((p for p in payments if p["payment_id"] == payment_id), None)
    if not base:
        return None

    cust = customers.get(base["customer_id"], {})
    diag = diagnosed.get(payment_id, {})
    interv = interventions.get(payment_id, {})
    gate = gated.get(payment_id, {})
    msg = messages.get(payment_id, {})
    resp = responses.get(payment_id, {})
    track = tracked.get(payment_id, {})
    metric = metrics_rows.get(payment_id, {})

    return {
        "payment_id": payment_id,
        "customer": {
            "name": cust.get("name"),
            "customer_id": base["customer_id"],
            "past_payment_behavior": cust.get("past_payment_behavior"),
            "formality_preference": cust.get("formality_preference"),
            "opted_out": cust.get("opted_out"),
        },
        "payment": {
            "amount": pipeline.parse_amount(base.get("amount")),
            "failure_reason_raw": base["failure_reason_raw"],
            "retry_count": base["retry_count"],
            "timestamp": base["timestamp"],
        },
        "stages": {
            "1_detect": {"status": "failed payment detected", "raw_reason": base["failure_reason_raw"]},
            "2_diagnose": {
                "predicted_category": diag.get("predicted_category"),
                "reasoning": diag.get("diagnosis_reasoning"),
            },
            "3_choose_intervention": {
                "action": interv.get("chosen_action"),
                "tone": interv.get("chosen_tone"),
                "reasoning": interv.get("chooser_reasoning"),
            },
            "4_compliance_gate": {
                "final_action": gate.get("final_action"),
                "status": gate.get("gate_status"),
                "reason": gate.get("gate_reason"),
            },
            "5_message": {
                "text": msg.get("message"),
            },
            "6_customer_response": {
                "reply": resp.get("customer_reply"),
                "outcome": resp.get("outcome"),
                "promised_date": resp.get("promised_date"),
            } if resp else None,
            "7_promise_tracking": {
                "promise_kept": track.get("promise_kept"),
                "escalation_step": track.get("escalation_step"),
            } if track and track.get("promise_kept") != "N/A" else None,
        },
        "final_outcome": {
            "recovered": metric.get("recovered") == "True",
            "recovery_path": metric.get("recovery_path"),
        },
    }


@app.get("/")
def root():
    return {"message": "Revenue Recovery Agent API is running. See /docs for endpoints."}


@app.get("/api/metrics")
def get_metrics():
    """Headline numbers: total at risk, total recovered, recovery rate by tone."""
    return metrics_summary


@app.get("/api/payments")
def list_payments():
    """Summary list of all payments — for the main dashboard table/funnel view."""
    result = []
    for p in payments:
        pid = p["payment_id"]
        gate = gated.get(pid, {})
        metric = metrics_rows.get(pid, {})
        result.append({
            "payment_id": pid,
            "customer_id": p["customer_id"],
            "amount": pipeline.parse_amount(p.get("amount")),
            "predicted_category": diagnosed.get(pid, {}).get("predicted_category"),
            "final_action": gate.get("final_action"),
            "chosen_tone": gate.get("chosen_tone"),
            "gate_status": gate.get("gate_status"),
            "recovered": metric.get("recovered") == "True",
        })
    return result


@app.get("/api/payments/{payment_id}")
def get_payment_trace(payment_id: str):
    """Full stage-by-stage agent trace for one payment — powers the
    live agent-trace view when a user clicks a payment in the dashboard."""
    trace = build_full_trace(payment_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Payment not found")
    return trace


@app.get("/api/tone-comparison")
def get_tone_comparison():
    """A/B-style comparison: groups payments by category, shows how
    different tones performed for similar underlying problems."""
    groups = defaultdict(lambda: defaultdict(list))

    for p in payments:
        pid = p["payment_id"]
        gate = gated.get(pid, {})
        metric = metrics_rows.get(pid, {})
        category = diagnosed.get(pid, {}).get("predicted_category")
        tone = gate.get("chosen_tone")

        if not tone or gate.get("final_action") not in pipeline.MESSAGING_ACTIONS:
            continue

        groups[category][tone].append({
            "payment_id": pid,
            "amount": pipeline.parse_amount(p.get("amount")),
            "recovered": metric.get("recovered") == "True",
        })

    comparison = {}
    for category, tones in groups.items():
        comparison[category] = {}
        for tone, items in tones.items():
            recovered_count = sum(1 for i in items if i["recovered"])
            comparison[category][tone] = {
                "sample_size": len(items),
                "recovered": recovered_count,
                "recovery_rate_pct": round(recovered_count / len(items) * 100, 1) if items else 0,
                "example_payment_ids": [i["payment_id"] for i in items[:3]],
            }

    return comparison


@app.get("/api/audit-log")
def get_audit_log():
    """Everything the compliance gate blocked or flagged — the honest
    exceptions list judges specifically asked for."""
    blocked = [
        {
            "payment_id": pid,
            "customer_id": row.get("customer_id"),
            "chosen_action": row.get("chosen_action"),
            "final_action": row.get("final_action"),
            "reason": row.get("gate_reason"),
        }
        for pid, row in gated.items()
        if row.get("gate_status") == "BLOCKED"
    ]
    return {"total_blocked": len(blocked), "entries": blocked}