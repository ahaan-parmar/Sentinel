"""Pure taint/drift risk logic for risky tool calls. No LLM calls, no IO beyond
the data passed in by the caller (ToolExecutor is responsible for any ledger/memory
lookups needed to build tier2_memory_contents).
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Demo placeholder: recipients/domains considered "known good" absent any other signal.
KNOWN_GOOD_RECIPIENTS: set[str] = {"alice@company.com", "company.com"}

_TAINT_RISK = 0.8
_DRIFT_RISK = 0.3


def _extract_target(tool_name: str, args: dict) -> str:
    """Pull the recipient/url string the taint check cares about for this tool."""
    if tool_name == "send_email":
        return str(args.get("to", ""))
    if tool_name == "http_request":
        return str(args.get("url", ""))
    return ""


def _domain_of(value: str) -> str:
    """Best-effort domain extraction: works for emails and URLs alike."""
    if "@" in value:
        return value.rsplit("@", 1)[-1].lower()
    parsed = urlparse(value if "//" in value else f"//{value}")
    return (parsed.netloc or value).lower()


def check_taint(
    tool_name: str,
    args: dict,
    retrieved_memory_ids: list[str],
    tier2_memory_contents: dict[str, str],
) -> tuple[bool, list[str], float]:
    """Does the recipient/url in args trace back to untrusted (tier 2) memory content?

    tier2_memory_contents maps memory_id -> content, pre-filtered by the caller to only
    the tier-2 ids among retrieved_memory_ids (caller has ledger access, this module
    does not). A match means the target string appears verbatim inside a tier-2
    memory's content, i.e. an attacker-controlled fact likely planted that address.
    """
    target = _extract_target(tool_name, args)
    tainted_ids: list[str] = []
    if target:
        for memory_id in retrieved_memory_ids:
            content = tier2_memory_contents.get(memory_id)
            if content and target.lower() in content.lower():
                tainted_ids.append(memory_id)

    taint_risk = _TAINT_RISK if tainted_ids else 0.0
    drift_risk = drift_score(target, KNOWN_GOOD_RECIPIENTS) if target else 0.0
    risk_score = min(taint_risk + drift_risk, 1.0)

    # Hard requirement: only tier-2 taint forces a pause. Drift alone just raises the
    # risk score for visibility/logging — it does not block execution by itself.
    should_pause = bool(tainted_ids)

    if should_pause:
        logger.info(
            "taint detected for %s target=%s tainted_ids=%s risk=%.2f",
            tool_name, target, tainted_ids, risk_score,
        )
    return should_pause, tainted_ids, risk_score


def drift_score(value: str, known_values: set[str]) -> float:
    """Baseline anomaly signal: unrecognized recipient/domain contributes risk."""
    domain = _domain_of(value)
    if value in known_values or domain in known_values:
        return 0.0
    return _DRIFT_RISK
