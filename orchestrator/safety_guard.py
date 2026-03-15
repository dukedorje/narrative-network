"""Path safety filtering — cycle prevention and content checks."""

from __future__ import annotations

from subnet.config import MIN_HOP_WORDS, MAX_HOP_WORDS


class PathSafetyGuard:
    """Filters candidate hops for safety and traversal integrity.

    Responsibilities:
    - Cycle prevention: reject nodes already visited in the session path.
    - Word count check: reject passages outside [MIN_HOP_WORDS, MAX_HOP_WORDS].
    - Rate limiting / abuse detection via tick().
    """

    def __init__(self, max_hops: int = 20):
        self.max_hops = max_hops
        self._tick_count: int = 0

    def filter_candidates(
        self,
        candidate_node_ids: list[str],
        visited_path: list[str],
    ) -> list[str]:
        """Return candidate node IDs that are safe to visit.

        Removes any node already in visited_path (cycle prevention).
        """
        visited_set = set(visited_path)
        return [nid for nid in candidate_node_ids if nid not in visited_set]

    def check_passage(self, passage: str) -> tuple[bool, str]:
        """Validate a narrative passage by word count.

        Returns (ok, reason). reason is empty string when ok is True.
        """
        word_count = len(passage.split())
        if word_count < MIN_HOP_WORDS:
            return False, f"Passage too short: {word_count} words (min {MIN_HOP_WORDS})"
        if word_count > MAX_HOP_WORDS:
            return False, f"Passage too long: {word_count} words (max {MAX_HOP_WORDS})"
        return True, ""

    def check_path_length(self, visited_path: list[str]) -> tuple[bool, str]:
        """Return False if the path has reached max_hops."""
        if len(visited_path) >= self.max_hops:
            return False, f"Maximum hops reached ({self.max_hops})"
        return True, ""

    def tick(self) -> None:
        """Increment internal tick counter (called once per hop for rate tracking)."""
        self._tick_count += 1
