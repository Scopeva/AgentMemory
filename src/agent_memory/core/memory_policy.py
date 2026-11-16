"""Memory lifecycle rules and evidence handling policy."""

from __future__ import annotations


EVIDENCE_LEVELS = {
    "E0": "Agent self-statement without external evidence; cannot be auto-accepted.",
    "E1": "File path, log, or tool output reference; default not auto-accepted.",
    "E2": "Verifiable Git change, test record, or current source; may enter auto-verification.",
    "E3": "Formal user approval or explicit confirmation; may be accepted per policy.",
}

STATE_MACHINE = {
    "candidate": ["accepted", "rejected", "archived"],
    "accepted": ["superseded", "archived"],
    "superseded": [],
    "rejected": [],
    "archived": [],
}


def can_transition(current: str, target: str) -> bool:
    return target in STATE_MACHINE.get(current, [])


def allowed_evidence_for_auto_accept(kinds: set[str]) -> bool:
    """E2 evidence alone may trigger auto-verification but not auto-acceptance
    for ADR/constraints."""
    return "git_commit" in kinds or "test_result" in kinds
