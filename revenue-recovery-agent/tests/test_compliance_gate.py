"""Tests for the deterministic compliance gate.

The project's central claim is that compliance is enforced by plain code, not
by a model — which is only worth something if the rules are actually pinned
down. These tests assert the rules AND their precedence directly against
pipeline.compliance_check, the single implementation that both the batch
script (compliance_gate.py) and the live path (live_processor.py) call.

No network, no Ollama, no Gemini — these run in milliseconds.
"""

import pytest

import pipeline

MESSAGING = sorted(pipeline.MESSAGING_ACTIONS)
BLOCKED_HOUR = 3


# --- Rule 1: opt-out ------------------------------------------------------

@pytest.mark.parametrize("action", MESSAGING)
def test_opted_out_customer_is_never_messaged(action):
    result = pipeline.compliance_check(action, opted_out=True, contact_count_so_far=0)
    assert result["status"] == "BLOCKED"
    assert result["final_action"] == "human_handoff"
    assert "opt-out" in result["reason"]


def test_opt_out_does_not_block_silent_auto_retry():
    """auto_retry contacts nobody, so an opt-out has no bearing on it."""
    result = pipeline.compliance_check("auto_retry", opted_out=True, contact_count_so_far=0)
    assert result["status"] == "ALLOWED"
    assert result["final_action"] == "auto_retry"


# --- Rule 2: messaging time window ---------------------------------------

@pytest.mark.parametrize("action", MESSAGING)
def test_messaging_outside_window_is_deferred(action):
    result = pipeline.compliance_check(
        action, opted_out=False, contact_count_so_far=0,
        within_window=False, attempt_hour=BLOCKED_HOUR,
    )
    assert result["status"] == "BLOCKED"
    assert result["final_action"] == "deferred"
    assert "03:00" in result["reason"]


def test_auto_retry_ignores_the_time_window():
    result = pipeline.compliance_check(
        "auto_retry", opted_out=False, contact_count_so_far=0, within_window=False)
    assert result["status"] == "ALLOWED"


@pytest.mark.parametrize("hour,expected", [
    (pipeline.WINDOW_START_HOUR - 1, False),
    (pipeline.WINDOW_START_HOUR, True),       # 09:00 is inside
    (pipeline.WINDOW_END_HOUR - 1, True),     # 19:00 is the last allowed hour
    (pipeline.WINDOW_END_HOUR, False),        # 20:00 is outside
    (0, False),
    (23, False),
])
def test_window_boundaries(hour, expected):
    assert pipeline.is_within_window(hour) is expected


# --- Rule 3: contact cap --------------------------------------------------

@pytest.mark.parametrize("prior", [0, 1, 2])
def test_contacts_within_cap_are_allowed(prior):
    result = pipeline.compliance_check(
        "send_soft_reminder", opted_out=False, contact_count_so_far=prior)
    assert result["status"] == "ALLOWED"
    assert result["reason"] == f"contact attempt {prior + 1}/{pipeline.MAX_CONTACT_ATTEMPTS}"


def test_attempt_beyond_cap_escalates_to_human():
    result = pipeline.compliance_check(
        "send_soft_reminder", opted_out=False,
        contact_count_so_far=pipeline.MAX_CONTACT_ATTEMPTS)
    assert result["status"] == "BLOCKED"
    assert result["final_action"] == "human_handoff"
    assert "max contact attempts" in result["reason"]


def test_cap_stays_closed_once_exceeded():
    """A customer at the cap must not become contactable again by accumulating
    further blocked attempts."""
    for prior in range(pipeline.MAX_CONTACT_ATTEMPTS, pipeline.MAX_CONTACT_ATTEMPTS + 5):
        result = pipeline.compliance_check(
            "offer_payment_plan", opted_out=False, contact_count_so_far=prior)
        assert result["status"] == "BLOCKED"


def test_auto_retry_is_not_counted_against_the_contact_cap():
    result = pipeline.compliance_check(
        "auto_retry", opted_out=False, contact_count_so_far=99)
    assert result["status"] == "ALLOWED"


# --- Rule precedence ------------------------------------------------------

def test_opt_out_outranks_the_time_window():
    """An opted-out customer is a permanent human_handoff, never a 'deferred'
    that a later retry could deliver."""
    result = pipeline.compliance_check(
        "send_soft_reminder", opted_out=True, contact_count_so_far=0,
        within_window=False, attempt_hour=BLOCKED_HOUR)
    assert result["final_action"] == "human_handoff"
    assert "opt-out" in result["reason"]


def test_opt_out_outranks_the_contact_cap():
    result = pipeline.compliance_check(
        "send_soft_reminder", opted_out=True,
        contact_count_so_far=pipeline.MAX_CONTACT_ATTEMPTS)
    assert "opt-out" in result["reason"]


def test_time_window_outranks_the_contact_cap():
    result = pipeline.compliance_check(
        "send_soft_reminder", opted_out=False,
        contact_count_so_far=pipeline.MAX_CONTACT_ATTEMPTS,
        within_window=False, attempt_hour=BLOCKED_HOUR)
    assert result["final_action"] == "deferred"


# --- Failed upstream stages ----------------------------------------------

@pytest.mark.parametrize("action", ["EXCEPTION_PARSE_FAILED", "EXCEPTION_REQUEST_FAILED"])
def test_failed_upstream_stage_is_never_silently_allowed(action):
    """An EXCEPTION_* action is not in MESSAGING_ACTIONS, so without an explicit
    rule it falls through to 'no compliance issues' and gets recorded as
    ALLOWED — an unresolved decision presented as a clean pass."""
    result = pipeline.compliance_check(action, opted_out=False, contact_count_so_far=0)
    assert result["status"] == "BLOCKED"
    assert result["final_action"] == "human_handoff"


# --- Attempt-hour assignment ---------------------------------------------

def test_attempt_hour_is_stable_for_the_same_payment():
    """Batch and live must gate a given payment identically, which requires the
    hour to depend only on the payment_id — not on row order or run order."""
    assert pipeline.simulated_attempt_hour("PAY_0042") == pipeline.simulated_attempt_hour("PAY_0042")


def test_attempt_hour_is_always_a_valid_hour():
    for i in range(500):
        assert 0 <= pipeline.simulated_attempt_hour(f"PAY_{i:04d}") <= 23


def test_attempt_hour_distribution_mostly_inside_the_window():
    """~85% inside the window: enough rows land outside for the rule to block on,
    without the demo looking like everything is blocked."""
    ids = [f"PAY_{i:04d}" for i in range(1000)]
    inside = sum(1 for pid in ids if pipeline.is_within_window(pipeline.simulated_attempt_hour(pid)))
    assert 0.78 < inside / len(ids) < 0.92


def test_different_payments_get_different_hours():
    hours = {pipeline.simulated_attempt_hour(f"PAY_{i:04d}") for i in range(200)}
    assert len(hours) > 10
