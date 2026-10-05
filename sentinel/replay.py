"""Counterfactual replay: estimate how much blame each untrusted (tier-2) memory
deserves for a risky planned action, by re-planning with that memory removed
from context and seeing whether the risky action persists.

This module only talks to the LLM backend's public `plan` interface (and plain
MemoryEntry/ToolCall objects) -- it never touches the ledger's SQL directly,
and it deliberately does not import sentinel.memory to avoid a circular import
(memory.py may eventually import things that touch blame/replay at the API
layer). The context formatting convention below is duplicated from
Memory.retrieve_for_turn: tier-2 entries are wrapped in
`<untrusted_data source="...">...</untrusted_data>` blocks, all other entries
are emitted as plain lines, joined with "\\n". Keep the two in sync if that
format ever changes.
"""
from __future__ import annotations

import logging
from collections import Counter

from sentinel.llm import LLMBackend
from sentinel.models import MemoryEntry, ToolCall

logger = logging.getLogger(__name__)

_BLAME_CAUSED = 1.0
_BLAME_WEAKENED = 0.5
_BLAME_NONE = 0.0

_MAX_CALLS_PER_MEMORY = 3


def _format_context(memories: list[MemoryEntry]) -> str:
    """Duplicate of Memory.retrieve_for_turn's formatting convention.

    Duplicated (rather than imported from sentinel.memory) to avoid a circular
    import risk between memory.py and replay.py, and because replay operates
    over an already-retrieved list of MemoryEntry objects rather than running
    its own search.
    """
    lines: list[str] = []
    for entry in memories:
        if entry.trust_tier == 2:
            lines.append(
                f'<untrusted_data source="{entry.source}">\n'
                f"{entry.content}\n"
                f"</untrusted_data>"
            )
        else:
            lines.append(entry.content)
    return "\n".join(lines)


def _tool_call_key(tool_call: dict | ToolCall) -> tuple[str, str]:
    """Identity for comparing "the same risky action": (tool, recipient/url).

    Looks at common target-ish arg names (to, url, recipient) so send_email and
    http_request style calls are compared sensibly; falls back to an empty
    string if none of those keys are present.
    """
    if isinstance(tool_call, ToolCall):
        tool = tool_call.tool
        args = tool_call.args
    else:
        tool = tool_call.get("tool", "")
        args = tool_call.get("args", {}) or {}

    target = ""
    for key in ("to", "url", "recipient"):
        if key in args and args[key]:
            target = str(args[key])
            break
    return tool, target


def _find_matching_call(target_key: tuple[str, str], tool_calls: list[dict]) -> dict | None:
    """Find a tool call in tool_calls matching target_key's (tool, target)."""
    for call in tool_calls:
        if _tool_call_key(call) == target_key:
            return call
    return None


def _score_replan(
    original_call: dict,
    target_key: tuple[str, str],
    replanned_tool_calls: list[dict],
) -> float:
    """Compare the original risky call to the replanned tool_calls list.

    The risky action's identity is (tool, recipient/url) via target_key:

    - That exact (tool, target) is gone from the replan -> the memory caused
      it -> 1.0 blame. This covers both "the tool call vanished entirely" and
      "the tool call is still there but now points somewhere else" (e.g. the
      poisoned recipient was replaced by a safe one) -- either way, the
      specific risky action no longer happens.
    - That exact (tool, target) is still present, but with other args changed
      (e.g. body/subject altered) -> weakened/altered form -> 0.5 blame.
    - That exact (tool, target) is still present with identical args -> the
      action persists unchanged -> 0.0 blame.
    """
    match = _find_matching_call(target_key, replanned_tool_calls)
    if match is None:
        return _BLAME_CAUSED

    original_args = original_call.get("args", {})
    match_args = match.get("args", {}) if isinstance(match, dict) else {}
    if match_args == original_args:
        return _BLAME_NONE
    return _BLAME_WEAKENED


def _majority_vote(scores: list[float]) -> float:
    """Return the most common score among scores; ties broken by the first-seen order."""
    counts = Counter(scores)
    best_score, _ = max(counts.items(), key=lambda item: (item[1], -scores.index(item[0])))
    return best_score


def _blame_for_memory(
    llm: LLMBackend,
    system_prompt: str,
    message: str,
    context_without_memory: str,
    original_call: dict,
    target_key: tuple[str, str],
) -> float:
    """Run the counterfactual replan for one memory, with nondeterminism handling.

    Calls llm.plan up to _MAX_CALLS_PER_MEMORY times total:
      1. First call -> score A.
      2. If a disagreement is possible (backend might be nondeterministic),
         rerun once -> score B.
      3. If A != B, one tiebreak call -> score C; majority vote of {A, B, C}.
    For a deterministic backend (e.g. ScriptedBackend) the second call will
    always agree with the first, so no third call ever happens.
    """
    first_plan = llm.plan(system_prompt, context_without_memory, message)
    score_a = _score_replan(original_call, target_key, first_plan.get("tool_calls", []))

    second_plan = llm.plan(system_prompt, context_without_memory, message)
    score_b = _score_replan(original_call, target_key, second_plan.get("tool_calls", []))

    if score_a == score_b:
        return score_a

    logger.info(
        "counterfactual replan disagreement (%.1f vs %.1f) for a memory; running tiebreak call",
        score_a,
        score_b,
    )
    third_plan = llm.plan(system_prompt, context_without_memory, message)
    score_c = _score_replan(original_call, target_key, third_plan.get("tool_calls", []))
    return _majority_vote([score_a, score_b, score_c])


def counterfactual_blame(
    llm: LLMBackend,
    system_prompt: str,
    message: str,
    retrieved_memories: list[MemoryEntry],
    planned_tool_calls: list[ToolCall],
) -> dict[str, float]:
    """Estimate blame for each tier-2 memory behind a risky planned action.

    For every untrusted (trust_tier == 2) memory in retrieved_memories, rebuild
    the turn's context without that one memory, re-plan via the LLM backend,
    and compare the resulting tool_calls against planned_tool_calls looking
    for the same risky action (same tool + same recipient/url):

    - action no longer present after removing the memory -> blame 1.0
    - action present but altered (same tool, different target) -> blame 0.5
    - action persists unchanged -> blame 0.0

    Returns a dict of memory_id -> blame_score, one entry per tier-2 memory in
    retrieved_memories. Memories at trust_tier 0/1 are not scored (they are
    trusted inputs, not candidates for blame).
    """
    untrusted_memories = [m for m in retrieved_memories if m.trust_tier == 2]
    if not untrusted_memories or not planned_tool_calls:
        return {}

    original_calls = [{"tool": tc.tool, "args": tc.args} for tc in planned_tool_calls]

    blame: dict[str, float] = {}
    for candidate in untrusted_memories:
        remaining = [m for m in retrieved_memories if m.id != candidate.id]
        context_without = _format_context(remaining)

        # Score blame per risky original tool call, then take the max across
        # them (a memory is "to blame" if it caused ANY of the risky actions).
        per_call_scores: list[float] = []
        for original_call in original_calls:
            target_key = _tool_call_key(original_call)
            score = _blame_for_memory(
                llm, system_prompt, message, context_without, original_call, target_key
            )
            per_call_scores.append(score)

        blame[candidate.id] = max(per_call_scores) if per_call_scores else _BLAME_NONE
        logger.info("counterfactual blame for memory %s: %.2f", candidate.id, blame[candidate.id])

    return blame
