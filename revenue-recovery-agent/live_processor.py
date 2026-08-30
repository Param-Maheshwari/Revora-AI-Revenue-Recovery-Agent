"""
live_processor.py — add-on to your FastAPI backend (main.py) that accepts
a CSV upload and streams each payment's agent journey to the browser in
real time using Server-Sent Events (SSE), using the SAME logic as your
batch pipeline (imported from pipeline.py).

HOW TO WIRE THIS INTO main.py:
  from live_processor import router as live_router
  app.include_router(live_router)

Then restart your backend (uvicorn main:app --reload picks this up
automatically on save).

Endpoints added:
  POST /api/live/upload   — upload a CSV, returns a job_id
  GET  /api/live/stream/{job_id} — SSE stream of live processing events

LIVE PROCESSING IS CAPPED to LIVE_ROW_LIMIT rows by default so a demo
finishes in a few minutes instead of 20+ (local Mistral calls are the
slow part). The full uploaded file is still saved — only the LIVE
on-screen run is capped.

The live path runs the SAME compliance rules as the batch script,
including the messaging time window: both call pipeline.compliance_check
with an attempt hour derived from pipeline.simulated_attempt_hour, so a
given payment_id is gated identically whichever path processes it.
"""

import csv
import io
import json
import uuid
import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

import pipeline

router = APIRouter()

LIVE_ROW_LIMIT = 25  # cap for the ON-SCREEN live run — keeps demos fast

# --- Upload guardrails ---
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB — a 150-row CSV is a few KB, this is generous
REQUIRED_COLUMNS = {"payment_id", "failure_reason_raw", "amount", "customer_id"}
# Free-text sanitization lives in pipeline.sanitize_text so the batch path and
# this path clean untrusted input exactly the same way.

# in-memory job store — fine for a hackathon demo, not for production
JOBS: dict[str, dict] = {}
JOB_TTL = timedelta(hours=1)


def _prune_jobs():
    """Bound the in-memory job store. Without this, every upload leaks its rows
    for the lifetime of the process."""
    cutoff = datetime.now() - JOB_TTL
    for job_id in [jid for jid, j in JOBS.items() if j["created_at"] < cutoff]:
        JOBS.pop(job_id, None)


def _default_customer():
    """Fallback ONLY when a customer_id in the uploaded CSV has no match
    in data/customers.csv — keeps the demo working even with a bare
    upload, but real customer profiles are always preferred."""
    return {
        "name": "Customer",
        "past_payment_behavior": "unknown",
        "formality_preference": "neutral",
        "opted_out": "False",
    }


def _load_customers():
    try:
        with open(pipeline.data_path("customers.csv"), newline="", encoding="utf-8") as f:
            return {row["customer_id"]: row for row in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


@router.post("/api/live/upload")
async def upload_csv(file: UploadFile = File(...)):
    _prune_jobs()

    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content) / 1024:.0f} KB). Max allowed is {MAX_UPLOAD_BYTES / 1024:.0f} KB.",
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read file as UTF-8 text. Please upload a plain CSV.")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise HTTPException(status_code=400, detail="CSV appears to be empty.")

    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                   f"Expected at least: {', '.join(sorted(REQUIRED_COLUMNS))}.",
        )

    # sanitize every free-text field before it can ever reach a prompt
    for row in rows:
        for key in ("failure_reason_raw", "customer_name"):
            if key in row:
                row[key] = pipeline.sanitize_text(row[key])

    # Surfaced back to the uploader rather than failing the run: amounts that
    # don't parse are treated as 0 downstream, and silently reporting ₹0
    # recovered on a malformed column would look like a product bug.
    invalid_amounts = sum(1 for r in rows if pipeline.parse_amount(r.get("amount"), None) is None)

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "rows": rows[:LIVE_ROW_LIMIT],
        "total_uploaded": len(rows),
        "status": "queued",
        "created_at": datetime.now(),
    }

    return {
        "job_id": job_id,
        "rows_to_process_live": min(len(rows), LIVE_ROW_LIMIT),
        "total_rows_in_file": len(rows),
        "rows_with_unparseable_amount": invalid_amounts,
        "note": (
            f"Live demo run capped at {LIVE_ROW_LIMIT} rows for speed. "
            f"Full-batch processing of all {len(rows)} rows uses the same "
            f"logic and can be run separately."
        ),
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _process_row(index: int, row: dict, total: int, customers: dict, contact_counts: dict):
    """One payment through all seven stages, yielding an SSE frame per stage.

    Every model call goes through asyncio.to_thread. That is not a style
    choice: pipeline's Ollama and Gemini calls are blocking, and awaiting them
    directly on the event loop would stall the entire server — this SSE
    response included — for the full duration of every model call.
    """
    payment_id = pipeline.sanitize_text(row.get("payment_id") or f"ROW{index}", 64)

    def stage(name, data):
        return _sse({"type": "stage", "payment_id": payment_id, "index": index,
                     "total": total, "stage": name, "data": data})

    raw_reason = pipeline.sanitize_text(
        row.get("failure_reason_raw") or row.get("failure_reason") or "unknown failure")
    retry_count = row.get("retry_count", "0")
    amount = pipeline.parse_amount(row.get("amount"))
    customer_id = pipeline.sanitize_text(row.get("customer_id") or f"CUST_{index}", 64)

    cust = customers.get(customer_id) or _default_customer()
    behavior = cust.get("past_payment_behavior", "unknown")
    formality = cust.get("formality_preference", "neutral")
    cust_name = pipeline.sanitize_text(row.get("customer_name") or cust.get("name") or "Customer", 80)

    yield stage("detect", {"raw_reason": raw_reason, "amount": amount})
    await asyncio.sleep(0.05)

    # Stage 2: Diagnose (local Mistral)
    diagnosis = await asyncio.to_thread(pipeline.diagnose_payment, raw_reason, retry_count, amount)
    yield stage("diagnose", diagnosis)
    await asyncio.sleep(0.05)

    # Stage 3: Choose intervention (local Mistral)
    decision = await asyncio.to_thread(
        pipeline.choose_intervention,
        diagnosis["category"], diagnosis["reasoning"], behavior, formality, retry_count, amount,
    )
    yield stage("choose_intervention", decision)
    await asyncio.sleep(0.05)

    # Stage 4: Compliance gate — same function the batch script calls, including
    # the time-window rule, so a payment is gated identically in both paths.
    attempt_hour = pipeline.simulated_attempt_hour(payment_id)
    gate = pipeline.compliance_check(
        action=decision["action"],
        opted_out=str(cust.get("opted_out")) == "True",
        contact_count_so_far=contact_counts.get(customer_id, 0),
        within_window=pipeline.is_within_window(attempt_hour),
        attempt_hour=attempt_hour,
    )
    if gate["status"] == "ALLOWED" and decision["action"] in pipeline.MESSAGING_ACTIONS:
        contact_counts[customer_id] = contact_counts.get(customer_id, 0) + 1

    yield stage("compliance_gate", {**gate, "simulated_attempt_hour": attempt_hour})
    await asyncio.sleep(0.05)

    recovered = False

    if gate["final_action"] in pipeline.MESSAGING_ACTIONS:
        # Stage 5: Message (Gemini)
        message = await asyncio.to_thread(
            pipeline.generate_message, gate["final_action"], decision["tone"], cust_name, amount)
        yield stage("message", {"text": message, "tone": decision["tone"]})
        await asyncio.sleep(0.05)

        # Stage 6: Simulated response (Gemini)
        response = await asyncio.to_thread(
            pipeline.simulate_response, behavior, formality, decision["tone"], message)
        yield stage("customer_response", response)
        await asyncio.sleep(0.05)

        if response["outcome"] == "paid_immediately":
            recovered = True
        elif response["outcome"] == "promised_later":
            track = pipeline.track_promise(
                behavior, commitment_strength=response.get("commitment_strength", ""))
            yield stage("promise_tracking", track)
            recovered = track["promise_kept"]
            await asyncio.sleep(0.05)

    yield _sse({
        "type": "payment_complete", "payment_id": payment_id, "index": index, "total": total,
        "recovered": recovered, "amount": amount,
        "auto_retry": gate["final_action"] == "auto_retry",
    })


async def _process_stream(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        yield _sse({"type": "error", "message": "job not found or expired"})
        return

    # A job is single-use. Without this guard, a page refresh (or any second GET
    # on the stream URL) silently re-runs every model call in the job again —
    # real Gemini quota spent, and a duplicated on-screen run.
    if job["status"] != "queued":
        yield _sse({"type": "error",
                    "message": f"job already {job['status']} — upload the file again to start a new run"})
        return

    job["status"] = "running"
    rows = job["rows"]
    total = len(rows)
    contact_counts: dict[str, int] = {}
    customers = await asyncio.to_thread(_load_customers)

    yield _sse({"type": "job_started", "total_rows": total})
    await asyncio.sleep(0.1)

    try:
        for i, row in enumerate(rows, 1):
            try:
                async for event in _process_row(i, row, total, customers, contact_counts):
                    yield event
            except Exception as exc:
                # One bad row must not abort the remaining rows and leave the
                # browser waiting on a stream that never completes.
                yield _sse({
                    "type": "row_error", "index": i, "total": total,
                    "payment_id": row.get("payment_id", f"ROW{i}"),
                    "message": f"{type(exc).__name__}: {exc}",
                })
            await asyncio.sleep(0.1)
    finally:
        job["status"] = "done"
        job["rows"] = []  # run is not replayable, so release the rows

    yield _sse({"type": "job_complete", "total_processed": total})


@router.get("/api/live/stream/{job_id}")
async def stream_job(job_id: str):
    return StreamingResponse(
        _process_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )