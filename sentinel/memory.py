"""Memory facade: wraps a Ledger with the write gate and retrieval formatting
that implements the prompt-injection defense (tier-2 content is fenced off)."""
from __future__ import annotations

import logging
import re

_STOPWORDS = {
    "a", "an", "the", "my", "me", "i", "please", "to", "for", "of", "is",
    "are", "do", "you", "can", "send", "and", "it", "in", "on", "with",
}

from sentinel.gate import check_write
from sentinel.ledger import Ledger
from sentinel.models import MemoryEntry, MemoryKind, MemoryStatus

logger = logging.getLogger(__name__)


class WriteBlocked(Exception):
    """Raised when the gate refuses a write. Caller should route it to the review queue."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Memory:
    """Application-facing entry point for reading/writing memories via the Ledger."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def add(
        self,
        content: str,
        kind: MemoryKind,
        source: str,
        trust_tier: int,
        parent_ids: list[str] = [],
    ) -> MemoryEntry:
        """Gate the write, then append to the ledger. Raises WriteBlocked if disallowed."""
        allowed, reason = check_write(content, kind, source, trust_tier)
        if not allowed:
            raise WriteBlocked(reason or "write blocked")
        return self._ledger.append(
            content, kind, source, trust_tier, parent_ids=parent_ids
        )

    def search(
        self,
        query: str,
        trust_tier: int | None = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> list[MemoryEntry]:
        """Keyword-overlap match over ledger content, hackathon-grade.

        A literal full-phrase substring match would miss realistic phrasing (e.g.
        "please send my invoice" never appears verbatim in stored content), so we
        tokenize the query and match content containing any non-stopword token.
        """
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOPWORDS]
        results: list[MemoryEntry] = []
        for entry in self._ledger.list_all():
            if entry.status != status:
                continue
            if trust_tier is not None and entry.trust_tier != trust_tier:
                continue
            content_lower = entry.content.lower()
            if tokens and not any(tok in content_lower for tok in tokens):
                continue
            results.append(entry)
        return results

    def retrieve_for_turn(self, query: str) -> tuple[str, list[str]]:
        """Build the LLM-facing context string for one turn.

        Tier-2 (untrusted) memories are wrapped in <untrusted_data> blocks so the
        downstream LLM/prompt layer can treat their contents as data, not instructions.
        Returns (formatted_context, all_retrieved_memory_ids) so the taint rule can
        track every memory id that touched this turn, regardless of tier.
        """
        matches = self.search(query)
        lines: list[str] = []
        retrieved_ids: list[str] = []
        for entry in matches:
            retrieved_ids.append(entry.id)
            if entry.trust_tier == 2:
                lines.append(
                    f'<untrusted_data source="{entry.source}">\n'
                    f"{entry.content}\n"
                    f"</untrusted_data>"
                )
            else:
                lines.append(entry.content)
        return "\n".join(lines), retrieved_ids
